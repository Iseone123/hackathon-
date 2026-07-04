"""Тесты бизнес-кейса, ML-модели, SQL-импорта, ISA-Tab."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app.hypotheses.business_case import build_business_case
from app.hypotheses.predictive_model import ExperimentPredictor
from app.hypotheses.research_analysis import build_research_analysis
from app.ingest.metadata_extract import enrich_metadata_from_content
from app.ingest.sql_import import fetch_sql_rows, rows_to_text, validate_readonly_query
from app.models import Hypothesis, RiskScores, SourceRef


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        id="h1",
        text="Добавка 0,3 кг/т КМЦ при pH 9 повысит извлечение меди на 4%",
        mechanism="КМЦ подавляет пустую породу",
        novelty_score=7,
        feasibility_score=8,
        expected_value_score=9,
        risk=RiskScores(technical=4, economic=3),
        sources=[SourceRef(doc_id="doc1", snippet="КМЦ 0,3 кг/т при pH 9 извлечение 85%")],
        verification_roadmap=["Лабораторный тест 7 дней", "Сравнение с контролем 14 дней"],
        reasoning="Согласно источнику doc1 применение КМЦ повышает извлечение",
    )


class TestBusinessCase:
    def test_builds_roi_fields(self):
        h = _hypothesis()
        chunks = [{"doc_id": "doc1", "text": "извлечение 82% при pH 8.5"}]
        bc = build_business_case(h, "Повышение извлечения меди", "без капитальных вложений", chunks)
        assert bc.target_kpi
        assert bc.expected_delta_pct is not None
        assert bc.annual_revenue_impact_rub is not None
        assert bc.roi_ratio is not None
        assert "KPI" in bc.narrative or "извлечение" in bc.narrative.lower()


class TestPredictiveModel:
    def test_fits_on_synthetic_processed(self, tmp_path):
        processed = tmp_path / "processed"
        processed.mkdir()
        record = {
            "text": "pH 9 0.3 кг/т извлечение 85%",
            "metadata": {
                "process_parameters": {"pH": 9, "reagent_dosage": 0.3},
                "measurement_results": {"recovery_pct": 85},
            },
        }
        for i, rec in enumerate([78, 80, 82, 84, 86, 88]):
            data = dict(record)
            data["metadata"]["measurement_results"] = {"recovery_pct": rec}
            data["metadata"]["process_parameters"]["pH"] = 8 + i * 0.2
            (processed / f"exp_{i}.json").write_text(json.dumps(data), encoding="utf-8")

        predictor = ExperimentPredictor()
        assert predictor.fit_from_corpus(processed)
        h = _hypothesis()
        pred, delta, patterns, notes, score = predictor.predict_for_hypothesis(h)
        assert pred is not None
        assert score > 0


class TestResearchAnalysisML:
    def test_includes_model_metadata(self, tmp_path):
        processed = tmp_path / "processed"
        processed.mkdir()
        for i in range(6):
            (processed / f"e{i}.json").write_text(
                json.dumps({
                    "text": f"pH {8+i*0.2} 0.3 кг/т извлечение {75+i*2}%",
                    "metadata": {
                        "process_parameters": {"pH": 8 + i * 0.2, "reagent_dosage": 0.3},
                        "measurement_results": {"recovery_pct": 75 + i * 2},
                    },
                }),
                encoding="utf-8",
            )

        predictor = ExperimentPredictor()
        assert predictor.fit_from_corpus(processed)

        h = _hypothesis()
        chunks = [
            {"doc_id": "geokniga_flot", "text": "золотоизвлечение сорбция 90%"},
            {"doc_id": "doc1", "text": "КМЦ 0,3 кг/т при pH 9 извлечение 85%"},
        ]
        ra = build_research_analysis(h, "извлечение меди", chunks, [])
        assert ra.analogy_domains
        assert ra.counterfactual_baseline
        assert ra.predictive_notes


class TestSqlImport:
    def test_readonly_guard(self):
        with pytest.raises(ValueError):
            validate_readonly_query("DELETE FROM t")

    def test_fetch_sqlite(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE t (pH REAL, recovery_pct REAL)")
        conn.execute("INSERT INTO t VALUES (9, 85)")
        conn.commit()
        conn.close()
        rows = fetch_sql_rows(f"sqlite:///{db}", "SELECT * FROM t")
        text = rows_to_text(rows, "demo")
        assert "pH=9" in text or "9" in text


class TestIsaTabMetadata:
    def test_isa_tab_from_text(self, tmp_path):
        p = tmp_path / "report.docx"
        p.write_text("unused")
        meta = enrich_metadata_from_content(
            p,
            "pH 9 | извлечение 85% | 0,3 кг/т | шаг 1: подготовка проб",
        )
        assert meta.isa_tab is not None
        assert meta.allotrope_process_uri

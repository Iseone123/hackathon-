"""Тесты расширенных модулей ТЗ."""

from __future__ import annotations

from app.hypotheses.research_analysis import build_research_analysis
from app.hypotheses.roadmap_builder import build_structured_roadmap, text_step_to_structured
from app.ingest.metadata_extract import enrich_metadata_from_content
from app.models import Hypothesis, RiskScores, SourceRef
from app.rag.knowledge_gaps import analyze_knowledge_gaps


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        id="h1",
        text="Добавка 0,3 кг/т КМЦ при pH 9 повысит извлечение меди",
        mechanism="КМЦ подавляет пустую породу",
        novelty_score=7,
        feasibility_score=8,
        expected_value_score=9,
        risk=RiskScores(technical=4, economic=3),
        sources=[SourceRef(doc_id="doc1", snippet="КМЦ 0,3 кг/т при pH 9")],
        verification_roadmap=["Лабораторный тест 7 дней", "Сравнение с контролем 14 дней"],
        reasoning="Согласно источнику doc1 применение КМЦ повышает извлечение в отличие от типовых схем",
    )


class TestMetadataExtract:
    def test_xlsx_params(self, tmp_path):
        p = tmp_path / "test.xlsx"
        p.write_text("not used")
        meta = enrich_metadata_from_content(
            p,
            "pH 9 | извлечение 85% | 0,3 кг/т КМЦ | проба A1",
        )
        assert "pH" in meta.process_parameters or meta.process_parameters


class TestKnowledgeGaps:
    def test_detects_missing_topic(self):
        chunks = [{"text": "общие сведения о металлургии", "doc_id": "d1"}]
        gaps = analyze_knowledge_gaps(
            "Повышение извлечения меди при флотации pH 8-10",
            "pH 8-10",
            chunks,
        )
        assert any(g.topic == "флотация" or g.severity == "high" for g in gaps)

    def test_skips_task_boilerplate_keywords(self):
        chunks = [{"text": "флотация меди pH 9 извлечение 85%", "doc_id": "d1"}] * 6
        gaps = analyze_knowledge_gaps(
            "Повышение извлечения меди из хвостов КГМК при оптимизации режима флотации",
            "pH 8-10, без капитальных вложений",
            chunks,
        )
        topics = {g.topic for g in gaps}
        assert "повышение" not in topics
        assert "капитальных" not in topics


class TestRoadmapBuilder:
    def test_structured_from_text(self):
        steps = build_structured_roadmap(_hypothesis())
        assert len(steps) >= 2
        assert steps[0].duration_days >= 1
        assert steps[0].resources

    def test_parses_duration(self):
        step = text_step_to_structured("Пилот 14 дней на пробах", 1, "гипотеза")
        assert step.duration_days == 14

    def test_success_not_whole_step_with_percent(self):
        raw = (
            "step 1: провести испытания с плотностью 30%, 35% при pH 9, "
            "успех - увеличение на 3%"
        )
        step = text_step_to_structured(raw, 1, "гипотеза")
        assert step.success_criteria == "увеличение на 3%"
        assert "30%" not in step.success_criteria


class TestResearchAnalysis:
    def test_builds_all_fields(self):
        h = _hypothesis()
        chunks = [{"doc_id": "doc1", "text": "КМЦ 0,3 кг/т при pH 9 извлечение 85%"}]
        ra = build_research_analysis(h, "извлечение меди", chunks, [])
        assert ra.analogy
        assert ra.counterfactual
        assert ra.counterfactual_baseline
        assert 0 <= ra.predictive_score <= 1

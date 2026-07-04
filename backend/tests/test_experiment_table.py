"""Тесты таблицы лабораторных экспериментов (одна строка = одна запись)."""

from __future__ import annotations

import json
from pathlib import Path

from app.ingest.experiment_table import (
    build_experiment_row_metadata,
    is_experiment_table,
    map_experiment_columns,
    parse_experiment_table,
)

HEADERS = (
    "sample_id",
    "pH",
    "reagent_dosage_kg_t",
    "temperature_C",
    "recovery_pct",
)
ROWS = [
    ("A1", 8.0, 0.5, 22, 78.2),
    ("A2", 8.5, 0.4, 23, 80.1),
    ("A3", 9.0, 0.3, 24, 84.5),
    ("A4", 9.5, 0.35, 25, 83.0),
    ("B1", 8.0, 0.6, 22, 76.5),
    ("B2", 9.0, 0.25, 24, 86.2),
    ("B3", 10.0, 0.3, 25, 81.0),
    ("C1", 8.5, 0.45, 23, 79.8),
]


def _write_lab_xlsx(path: Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(list(HEADERS))
    for row in ROWS:
        ws.append(list(row))
    wb.save(path)


class TestExperimentTableParse:
    def test_detects_experiment_headers(self):
        assert is_experiment_table(HEADERS)
        mapped = map_experiment_columns(HEADERS)
        assert mapped["pH"] == 1
        assert mapped["reagent_dosage"] == 2
        assert mapped["recovery_pct"] == 4

    def test_ignores_tailings_layout(self):
        headers = ["", "Отвальные хвосты", "5824591", "0.17"]
        assert not is_experiment_table(headers)

    def test_parse_all_rows(self, tmp_path):
        xlsx = tmp_path / "Лабораторные опыты.xlsx"
        _write_lab_xlsx(xlsx)
        records = parse_experiment_table(xlsx)
        assert records is not None
        assert len(records) == 8
        assert records[0]["sample_id"] == "A1"
        assert records[0]["pH"] == 8.0
        assert records[2]["recovery_pct"] == 84.5

    def test_row_metadata_for_ml(self, tmp_path):
        xlsx = tmp_path / "lab.xlsx"
        _write_lab_xlsx(xlsx)
        row = parse_experiment_table(xlsx)[0]
        meta = build_experiment_row_metadata(xlsx, row)
        assert meta.process_parameters["pH"] == 8.0
        assert meta.process_parameters["reagent_dosage"] == 0.5
        assert meta.measurement_results["recovery_pct"] == 78.2
        assert meta.isa_tab is not None
        assert meta.isa_tab.assay_id.endswith("_A1")


class TestExperimentTableIngest:
    def test_index_status_marks_parent_file(self, tmp_path, monkeypatch):
        from app.config import settings
        from app.ingest import index_status

        data_dir = tmp_path / "data"
        processed = data_dir / "processed"
        processed.mkdir(parents=True)
        xlsx = data_dir / "Лабораторные опыты.xlsx"
        xlsx.touch()

        doc = {
            "id": "lab_A1_abc",
            "metadata": {"source": "Лабораторные опыты.xlsx#A1", "title": "t"},
        }
        (processed / "lab_A1_abc.json").write_text(json.dumps(doc), encoding="utf-8")

        class _FakeSettings:
            processed_dir = processed
            data_dir_path = data_dir

        monkeypatch.setattr(index_status, "settings", _FakeSettings())
        monkeypatch.setattr(settings, "data_dir", str(data_dir))

        assert index_status.is_file_indexed(xlsx)

    def test_predictor_reads_row_records(self, tmp_path):
        from app.hypotheses.predictive_model import ExperimentPredictor

        processed = tmp_path / "processed"
        processed.mkdir()
        for i, (sample, ph, rec) in enumerate(
            [("A1", 8.0, 78.2), ("A2", 8.5, 80.1), ("A3", 9.0, 84.5), ("A4", 9.5, 83.0)]
        ):
            xlsx = tmp_path / "lab.xlsx"
            _write_lab_xlsx(xlsx)
            row = parse_experiment_table(xlsx)[i]
            meta = build_experiment_row_metadata(xlsx, row)
            doc = {
                "text": f"pH {ph} извлечение {rec}%",
                "metadata": meta.model_dump(),
            }
            (processed / f"{sample}.json").write_text(
                json.dumps(doc, ensure_ascii=False),
                encoding="utf-8",
            )

        predictor = ExperimentPredictor()
        assert predictor.fit_from_corpus(processed)
        assert predictor._sample_count == 4

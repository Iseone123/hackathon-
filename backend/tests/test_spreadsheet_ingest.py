"""Тест ingest xlsx: KPI-чанк первым для отчётов по хвостам."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.models import DocumentMetadata


def _tailings_rows():
    return [
        ["", "Отвальные хвосты", "1000000", "0.2"],
        ["", "Класс крупности, мкм", "Доля класса, %", "Доля Элемент 28, %"],
        ["", "+71", "20.5", "25.8"],
        ["", "Итого извлекаемый металл", "", "55.5"],
    ]


def test_spreadsheet_ingest_puts_kpi_chunk_first(tmp_path, monkeypatch):
    from openpyxl import Workbook

    from app.config import settings
    from app.ingest.pipeline import IngestPipeline

    data_dir = tmp_path / "data"
    processed = data_dir / "processed"
    data_dir.mkdir()
    processed.mkdir()
    xlsx = data_dir / "Хвосты тест.xlsx"
    wb = Workbook()
    ws = wb.active
    for row in _tailings_rows():
        ws.append(row)
    wb.save(xlsx)

    monkeypatch.setattr(settings, "data_dir", str(data_dir))

    llm = MagicMock()
    captured_chunks: list[list[str]] = []

    def fake_embed(chunks, model=None):
        captured_chunks.append(chunks)
        return [[0.1] * 8 for _ in chunks]

    llm.embed_documents.side_effect = lambda texts: fake_embed(texts)

    qdrant = MagicMock()
    qdrant.upsert_chunks.return_value = 1

    pipeline = IngestPipeline(llm=llm, qdrant=qdrant, neo4j=MagicMock())
    with patch("app.ingest.pipeline.extract_entities", return_value=([], [])):
        result = pipeline.ingest_file(
            xlsx,
            DocumentMetadata(source="Хвосты тест.xlsx", title=xlsx.name),
        )

    assert result["xlsx_type"] == "tailings_kpi"
    assert result["kpi_chunk"] is True
    assert captured_chunks
    first_chunk = captured_chunks[0][0]
    assert first_chunk.startswith("# KPI-сводка")
    assert "55.5" in first_chunk or "извлекаемый металл" in first_chunk.lower()

    json_files = list(processed.glob("*.json"))
    assert len(json_files) == 1
    import json

    doc = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert "enterprise_kpi" in doc["metadata"]["tags"]
    assert "xlsx_type:tailings_kpi" in doc["metadata"]["tags"]

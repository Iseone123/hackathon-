"""Тесты mandatory KPI/brainstorm retrieval."""

from __future__ import annotations

from app.ingest.kpi import kpi_summary_from_doc
from app.ingest.processed_store import load_docs_for_dirs
from app.rag.example_retrieval import build_mandatory_chunks, merge_example_chunks


def test_load_kgmk_processed_docs(kgmk_processed):
    docs = load_docs_for_dirs(["Пример 1"])
    ids = {d.get("id", "") for d in docs}
    assert any("КГМК" in i for i in ids)


def test_mandatory_chunks_include_brainstorm_and_kpi(kgmk_processed):
    topics, chunks = build_mandatory_chunks(["Пример 1"])
    assert len(topics) >= 3
    assert any("магнит" in t.lower() for t in topics)
    kinds = {c.get("mandatory") for c in chunks}
    assert "brainstorm" in kinds
    assert "kpi" in kinds
    assert all(c.get("doc_id") for c in chunks)


def test_kpi_summary_from_processed_xlsx(kgmk_processed):
    docs = load_docs_for_dirs(["Пример 1"])
    xlsx = next(d for d in docs if "Хвосты" in d.get("id", ""))
    summary = kpi_summary_from_doc(xlsx)
    assert summary
    assert "KPI-сводка" in summary
    assert "72" in summary or "извлекаем" in summary.lower()


def test_merge_puts_mandatory_first():
    vector = [{"doc_id": "book", "chunk_index": 0, "text": "учебник"}]
    mandatory = [
        {"doc_id": "kpi", "chunk_index": 0, "text": "# KPI-сводка", "mandatory": "kpi"},
        {
            "doc_id": "brain",
            "chunk_index": 0,
            "text": "1. Магнитная сепарация",
            "mandatory": "brainstorm",
        },
    ]
    merged = merge_example_chunks(vector, mandatory, max_inject=2)
    assert merged[0]["doc_id"] == "kpi"
    assert merged[1]["doc_id"] == "brain"


def test_retrieve_includes_excel_doc_id(kgmk_processed):
    topics, mandatory = build_mandatory_chunks(["Пример 1"])
    assert topics
    kpi_doc = next(c["doc_id"] for c in mandatory if c.get("mandatory") == "kpi")
    assert "Хвосты" in kpi_doc or "КГМК" in kpi_doc

"""Тесты ingest helpers."""

from __future__ import annotations

from app.ingest.helpers import summarize_ingest_results


def test_summarize_ingest_results():
    results = [
        {"chunks_indexed": 5, "doc_id": "a"},
        {"skipped": True, "reason": "already_indexed"},
        {"error": "parse failed", "path": "/x"},
    ]
    summary = summarize_ingest_results(results)
    assert summary["processed"] == 3
    assert summary["ingested"] == 1
    assert summary["skipped"] == 1
    assert summary["errors"] == 1

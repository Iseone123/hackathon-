"""Тесты example-aware retrieval."""

from __future__ import annotations

from app.rag.example_registry import infer_example_dirs
from app.rag.example_retrieval import (
    example_source_boost,
    merge_example_chunks,
    score_example_chunk,
)


def test_infer_example_dirs_kgmk():
    dirs = infer_example_dirs(
        "Повышение извлечения меди из хвостов КГМК",
        "pH 8-10",
    )
    assert "Пример 1" in dirs


def test_infer_example_dirs_nof_vkr():
    dirs = infer_example_dirs(
        "Извлечение вкраплённой меди из хвостов НОФ",
        "",
    )
    assert "Пример 2" in dirs


def test_example_source_boost_xlsx():
    boost = example_source_boost(
        "Пример 1/Хвосты КГМК.xlsx",
        ["Пример 1"],
    )
    assert boost >= 0.35


def test_merge_example_chunks_prepends():
    vector = [{"doc_id": "book", "chunk_index": 0, "text": "учебник"}]
    example = [
        {"doc_id": "xlsx", "chunk_index": 0, "text": "хвосты", "example_score": 0.9},
        {"doc_id": "book", "chunk_index": 0, "text": "дубль"},
    ]
    merged = merge_example_chunks(vector, example, max_inject=2)
    assert merged[0]["doc_id"] == "xlsx"
    assert len(merged) == 2


def test_score_example_chunk_prefers_kpi():
    high = score_example_chunk(
        "Итого изvлекаемый металл в хвостах: 72.8%",
        ["хвост", "извлечение", "меди"],
    )
    low = score_example_chunk("общая теория флотации", ["хвост", "извлечение", "меди"])
    assert high > low

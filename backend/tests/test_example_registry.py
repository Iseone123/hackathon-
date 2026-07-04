"""Тесты example registry и KPI-чанков."""

from __future__ import annotations

from pathlib import Path

from app.ingest.tabular import (
    build_kpi_priority_chunk,
    extract_workbook_kpi,
    summarize_sheet_domain,
)
from app.rag.example_registry import get_example_registry, infer_example_dirs
from app.rag.example_context import kpi_chunk_boost, score_example_chunk


def test_infer_all_examples_on_generic_tailings():
    dirs = infer_example_dirs("Повышение извлечения из хвостов обогащения", "")
    registry = get_example_registry()
    assert len(dirs) == len(registry.all_dirs)
    assert "Пример 3" in dirs
    assert "Пример 4" in dirs


def test_infer_kgmk_only():
    dirs = infer_example_dirs("Повышение извлечения меди из хвостов КГМК", "")
    assert dirs == ["Пример 1"]


def test_kpi_chunk_boost():
    text = build_kpi_priority_chunk(
        "Хвосты.xlsx",
        ["- Итого извлекаемый металл в хвостах: 72.78%"],
    )
    assert kpi_chunk_boost(text) > 0.2
    assert score_example_chunk(text, ["извлечение", "хвост"]) > 0.75


def test_extract_workbook_kpi_from_fixture_rows():
    rows = [
        ["", "Отвальные хвосты", "5824591", "0.17"],
        ["", "Класс крупности, мкм", "Доля класса, %", "Доля Элемент 28, %"],
        ["", "+71", "20.5", "25.8"],
        ["", "Итого извлекаемый металл", "", "72.78", "7564"],
    ]
    summary = summarize_sheet_domain(rows)
    assert any("72.78" in line for line in summary)


def test_extract_workbook_kpi_real_file():
    base = Path(__file__).resolve().parents[2] / "data" / "Пример 1" / "Хвосты КГМК.xlsx"
    if not base.exists():
        return
    result = extract_workbook_kpi(base)
    assert result is not None
    kpi, lines = result
    assert kpi.get("recoverable_metal_pct") or lines

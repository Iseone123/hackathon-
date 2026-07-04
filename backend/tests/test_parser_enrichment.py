"""Тесты универсального парсера таблиц и docx."""

from __future__ import annotations

from pathlib import Path

from app.ingest.docx_parse import enrich_structured_docx
from app.ingest.parser import parse_file
from app.ingest.tabular import (
    build_workbook_summary,
    parse_xlsx_summary,
    summarize_sheet_domain,
    summarize_sheet_generic,
)


def test_parse_xlsx_summary_kgmk_layout():
    """Колонка A пустая — метки в B (типичный отчёт по хвостам)."""
    rows = [
        ["", "Отвальные хвосты", "5824591", "0.17"],
        ["", "Класс крупности, мкм", "Доля класса, %", "Доля Элемент 28, %"],
        ["", "+71", "20.5", "25.8"],
        ["", "-10", "30.3", "28.7"],
        ["", "Итого извлекаемый металл", "", "72.78", "7564"],
    ]
    summary = parse_xlsx_summary(rows)
    text = "\n".join(summary)
    assert "Отвальные хвосты" in text
    assert "72.78" in text
    assert "+71" in text


def test_parse_xlsx_summary_label_in_column_a():
    """Метка в колонке A — другой шаблон Excel."""
    rows = [
        ["Отвальные хвосты", "1000000", "0.2"],
        ["Итого извлекаемый металл", "", "55.5"],
    ]
    summary = summarize_sheet_domain(rows)
    text = "\n".join(summary)
    assert "1000000" in text
    assert "55.5" in text


def test_generic_spreadsheet_fallback():
    """Произвольная таблица без доменных KPI — generic-обзор."""
    rows = [
        ["Дата", "Показатель", "Значение", "Единица"],
        ["2024-01", "Выход", "85.2", "%"],
        ["2024-02", "Расход", "1200", "кг"],
    ]
    summary = summarize_sheet_generic("Данные", rows)
    text = "\n".join(summary)
    assert "Данные" in text
    assert "Показатель" in text or "Колонки" in text
    assert "85.2" in text or "Выход" in text


def test_build_workbook_summary_mixed_sheets():
    sheets = {
        "Метрики": [
            ["Показатель", "Значение"],
            ["Тоннаж", "5000"],
        ],
    }
    summary = build_workbook_summary(sheets, filename="report.xlsx")
    text = "\n".join(summary)
    assert "report.xlsx" in text
    assert "Метрики" in text or "Тоннаж" in text


def test_enrich_docx_any_numbered_list():
    raw = (
        "Рекомендации:\n"
        "1. Увеличить дозировку собирателя\n"
        "2. Снизить pH до 9\n"
        "3. Провести контрольный опыт"
    )
    enriched = enrich_structured_docx(raw, Path("рекомендации.docx"))
    assert "Пункт 1:" in enriched
    assert "собирателя" in enriched
    assert "Ключевые темы" in enriched


def test_enrich_docx_hypotheses_table_row():
    raw = (
        "Гипотезы по результатам мозгового штурма:\n"
        "## Table 1\n"
        "1. Магнитная сепарация над целевого класса\n"
        "2. Изменение геометрии футеровки шаровых мельниц"
    )
    enriched = enrich_structured_docx(raw, Path("Гипотезы КГМК.docx"))
    assert "Гипотеза 1:" in enriched
    assert "мельниц" in enriched.lower()


def test_parse_all_example_xlsx_files():
    base = Path(__file__).resolve().parents[2] / "data"
    files = [
        base / "Пример 1" / "Хвосты КГМК.xlsx",
        base / "Пример 2" / "Хвосты НОФ Вкр.xlsx",
        base / "Пример 3" / "Хвосты НОФ мед.xlsx",
        base / "Пример 4" / "Хвосты ТОФ_2.xlsx",
    ]
    for path in files:
        if not path.exists():
            continue
        text = parse_file(path)
        assert len(text) > 500, path.name
        assert "Сводка для RAG" in text, path.name
        assert "извлекаемый металл" in text.lower(), path.name

"""Тесты парсера brainstorm topics."""

from __future__ import annotations

from app.ingest.brainstorm_topics import extract_brainstorm_topics, parse_numbered_line


def test_parse_numbered_line_plain():
    assert parse_numbered_line("1. Магнитная сепарация") == ("1", "Магнитная сепарация")


def test_parse_numbered_line_enriched_header():
    assert parse_numbered_line("## Гипотеза 2: Изменение футеровки") == (
        "2",
        "Изменение футеровки",
    )


def test_extract_topics_from_table_and_headers():
    text = (
        "Гипотезы по результатам мозгового штурма:\n"
        "## Table 1\n"
        "1. Магнитная сепарация над целевого класса\n"
        "## Гипотеза 2: Замена насадок гидроциклонов\n"
    )
    topics = extract_brainstorm_topics(text)
    assert len(topics) >= 2
    assert any("магнит" in t.lower() for t in topics)
    assert any("гидроциклон" in t.lower() for t in topics)

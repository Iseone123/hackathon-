"""Тесты модульных промптов."""

from __future__ import annotations

from app.hypotheses.prompt_sections import (
    build_case_hints,
    build_generation_system,
    build_generation_user_footer,
    build_source_strategy_hint,
)
from app.hypotheses.prompts import GENERATION_SYSTEM


def test_generation_system_includes_dual_source_strategy():
    assert "[ПРИМЕР]" in GENERATION_SYSTEM
    assert "GOOD example — enterprise" in GENERATION_SYSTEM
    assert "BAD example" in GENERATION_SYSTEM
    assert "КМЦ" in GENERATION_SYSTEM


def test_build_case_hints_kgmk_covers_both_sources():
    hints = build_case_hints(
        "Повышение извлечения меди из хвостов КГМК",
        "pH 8-10, без капитальных вложений",
    )
    assert "магнитная" in hints.lower() or "мозгового" in hints.lower()
    assert "КМЦ" in hints


def test_source_strategy_hint_when_examples_present():
    hint = build_source_strategy_hint(
        ["Пример 1"],
        [{"source": "Пример 1/Гипотезы КГМК.docx", "from_example": True}],
    )
    assert "hypothesis 1" in hint.lower()
    assert "Пример 1" in hint


def test_source_strategy_hint_empty_without_examples():
    assert build_source_strategy_hint([], []) == ""


def test_user_footer_is_compact():
    footer = build_generation_user_footer()
    assert "CITATION:" in footer
    assert len(footer) < 600


def test_build_generation_system_stable():
    assert build_generation_system() == GENERATION_SYSTEM

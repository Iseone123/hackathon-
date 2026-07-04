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
    assert "кг/т" in GENERATION_SYSTEM
    assert "КГМК" not in GENERATION_SYSTEM


def test_build_case_hints_kgmk_from_yaml():
    hints = build_case_hints(
        "Повышение извлечения меди из хвостов КГМК",
        "pH 8-10, без капитальных вложений",
    )
    assert "КГМК" in hints
    assert "магнитная" in hints.lower() or "мозгового" in hints.lower() or "Excel" in hints


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
    assert build_generation_system("ru") == GENERATION_SYSTEM


def test_multilingual_translate_to_russian():
    assert "MULTILINGUAL INPUT" in GENERATION_SYSTEM
    assert "TRANSLATE" in GENERATION_SYSTEM or "translate" in GENERATION_SYSTEM
    assert "GOOD example — English source" in GENERATION_SYSTEM
    assert "do NOT translate the snippet" in GENERATION_SYSTEM or "verbatim" in GENERATION_SYSTEM


def test_build_language_rule_in_system():
    assert "OUTPUT LANGUAGE" in GENERATION_SYSTEM
    assert "русский" in GENERATION_SYSTEM or "Russian" in GENERATION_SYSTEM

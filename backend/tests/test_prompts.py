"""Тесты модульных промптов."""

from __future__ import annotations

from app.hypotheses.options import clamp_hypothesis_count
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
    assert "measurable" in GENERATION_SYSTEM.lower() or "units" in GENERATION_SYSTEM.lower()
    assert "КГМК" not in GENERATION_SYSTEM


def test_build_case_hints_kgmk_from_yaml():
    hints = build_case_hints(
        "Повышение извлечения меди из хвостов КГМК",
        "pH 8-10, без капитальных вложений",
    )
    assert "КГМК" in hints
    assert "brainstorm" in hints.lower() or "equipment" in hints.lower() or "Excel" in hints


def test_source_strategy_hint_when_examples_present():
    hint = build_source_strategy_hint(
        ["Пример 1"],
        [{"source": "Пример 1/Гипотезы КГМК.docx", "from_example": True}],
        hypothesis_count=5,
    )
    assert "distinct" in hint.lower() or "hypotheses" in hint.lower()
    assert "Пример 1" in hint


def test_source_strategy_hint_empty_without_examples():
    assert build_source_strategy_hint([], []) == ""


def test_user_footer_is_compact():
    footer = build_generation_user_footer(hypothesis_count=5)
    assert "CITATION:" in footer
    assert "exactly 5" in footer
    assert len(footer) < 750


def test_chinese_source_example_in_system():
    sys = build_generation_system()
    assert "Chinese source, Russian hypothesis" in sys


def test_hypothesis_count_clamped():
    assert clamp_hypothesis_count(None) >= 1
    assert clamp_hypothesis_count(99) <= 12
    sys = build_generation_system(hypothesis_count=7)
    assert "exactly 7 diverse" in sys


def test_build_generation_system_varies_by_count():
    assert "exactly 3" not in build_generation_system(hypothesis_count=5)
    assert "exactly 5 diverse" in build_generation_system(hypothesis_count=5)


def test_multilingual_translate_to_russian():
    assert "MULTILINGUAL INPUT" in GENERATION_SYSTEM
    assert "RUSSIAN OUTPUT" in GENERATION_SYSTEM
    assert "GOOD example — English source" in GENERATION_SYSTEM
    assert "Chinese source, Russian hypothesis" in GENERATION_SYSTEM


def test_build_language_rule_in_system():
    assert "OUTPUT LANGUAGE" in GENERATION_SYSTEM
    assert "русский" in GENERATION_SYSTEM or "Russian" in GENERATION_SYSTEM

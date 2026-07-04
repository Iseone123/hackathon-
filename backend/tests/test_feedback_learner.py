"""Тесты обучения на фидбэке."""

from __future__ import annotations

import json

from app.feedback.learner import get_generation_hints, record_hypothesis_feedback
from app.feedback.store import load_patterns
from app.models import FeedbackStatus


def test_feedback_records_patterns(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "data_dir", str(tmp_path))
    record_hypothesis_feedback(
        "h1",
        FeedbackStatus.CONFIRMED,
        {
            "text": "КМЦ при флотации меди повысит извлечение на 3%",
            "mechanism": "подавление",
            "novelty_score": 8,
            "feasibility_score": 7,
            "expected_value_score": 9,
            "risk": {"technical": 4, "economic": 3},
        },
    )
    patterns = load_patterns()
    assert patterns["confirmed_count"] == 1
    assert patterns["confirmed_keywords"].get("флотации", 0) >= 1
    assert patterns.get("exemplars")
    hints = get_generation_hints()
    assert "флотации" in hints or "Эксперт" in hints or "одобренной" in hints


def test_feedback_rejected_anti_pattern(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "data_dir", str(tmp_path))
    record_hypothesis_feedback(
        "h2",
        FeedbackStatus.REJECTED,
        {"text": "Размытая гипотеза без параметров", "mechanism": "неясно"},
        comment="Нет измеримых параметров",
    )
    patterns = load_patterns()
    assert patterns["rejected_count"] == 1
    assert patterns.get("anti_patterns")
    hints = get_generation_hints()
    assert "Анти-паттерн" in hints or "Избегайте" in hints


def test_feedback_updates_score_profiles(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "data_dir", str(tmp_path))
    record_hypothesis_feedback(
        "h3",
        FeedbackStatus.CONFIRMED,
        {
            "text": "Добавка модификатора повысит прочность на 5%",
            "mechanism": "фазовые превращения",
            "novelty_score": 9,
            "feasibility_score": 8,
            "expected_value_score": 8,
            "risk": {"technical": 3, "economic": 2},
        },
    )
    patterns = load_patterns()
    profile = patterns["score_profiles"]["confirmed"]["novelty"]
    assert profile["count"] == 1
    assert profile["sum"] == 9

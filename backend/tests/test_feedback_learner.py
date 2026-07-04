"""Тесты обучения на фидбэке."""

from __future__ import annotations

import json

from app.feedback.learner import get_generation_hints, load_patterns, record_hypothesis_feedback
from app.models import FeedbackStatus


def test_feedback_records_patterns(tmp_path, monkeypatch):
    from app import config

    monkeypatch.setattr(config.settings, "data_dir", str(tmp_path))
    record_hypothesis_feedback(
        "h1",
        FeedbackStatus.CONFIRMED,
        {"text": "КМЦ при флотации меди", "mechanism": "подавление"},
    )
    patterns = load_patterns()
    assert patterns["confirmed_count"] == 1
    assert patterns["confirmed_keywords"].get("флотации", 0) >= 1
    hints = get_generation_hints()
    assert "флотации" in hints or "Эксперт" in hints

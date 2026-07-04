"""Хранение паттернов и лога фидбэка."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import settings
from app.feedback.scores import RANKING_CRITERIA, empty_score_profile

PATTERNS_FILE = "feedback_patterns.json"
LOG_FILE = "feedback_log.jsonl"


def patterns_path() -> Path:
    return settings.data_dir_path / PATTERNS_FILE


def log_path() -> Path:
    return settings.data_dir_path / LOG_FILE


def empty_patterns() -> dict[str, Any]:
    return {
        "confirmed_keywords": {},
        "rejected_keywords": {},
        "confirmed_count": 0,
        "rejected_count": 0,
        "score_profiles": {
            "confirmed": empty_score_profile(),
            "rejected": empty_score_profile(),
        },
        "exemplars": [],
        "anti_patterns": [],
        "hints": [],
    }


def load_patterns() -> dict[str, Any]:
    path = patterns_path()
    if not path.exists():
        return empty_patterns()
    data = json.loads(path.read_text(encoding="utf-8"))
    defaults = empty_patterns()
    for key, val in defaults.items():
        data.setdefault(key, val)
    return data


def save_patterns(data: dict[str, Any]) -> None:
    patterns_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_log_entry(entry: dict[str, Any]) -> None:
    with log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

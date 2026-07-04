"""Обучение на фидбэке: веса + паттерны подтверждённых/отклонённых гипотез."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.config import settings
from app.feedback.bandit import load_adjusted_weights, update_weights_from_feedback
from app.models import FeedbackStatus

PATTERNS_FILE = "feedback_patterns.json"
LOG_FILE = "feedback_log.jsonl"


def _patterns_path() -> Path:
    return settings.data_dir_path / PATTERNS_FILE


def _log_path() -> Path:
    return settings.data_dir_path / LOG_FILE


def load_patterns() -> dict[str, Any]:
    path = _patterns_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "confirmed_keywords": {},
        "rejected_keywords": {},
        "confirmed_count": 0,
        "rejected_count": 0,
        "hints": [],
    }


def save_patterns(data: dict[str, Any]) -> None:
    _patterns_path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _extract_keywords(text: str) -> list[str]:
    return re.findall(r"[а-яёa-z]{5,}", text.lower())[:20]


def record_hypothesis_feedback(
    hypothesis_id: str,
    status: FeedbackStatus,
    hypothesis: dict[str, Any] | None = None,
    comment: str = "",
    expert_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Сохраняет фидбэк и обновляет веса + паттерны."""
    weights = update_weights_from_feedback(status, expert_scores)
    patterns = load_patterns()

    entry = {
        "hypothesis_id": hypothesis_id,
        "status": status.value,
        "comment": comment,
        "text": (hypothesis or {}).get("text", "")[:200],
    }
    with _log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    if hypothesis:
        text = f"{hypothesis.get('text', '')} {hypothesis.get('mechanism', '')}"
        bucket = (
            patterns["confirmed_keywords"]
            if status == FeedbackStatus.CONFIRMED
            else patterns["rejected_keywords"]
        )
        for kw in _extract_keywords(text):
            bucket[kw] = bucket.get(kw, 0) + 1
        if status == FeedbackStatus.CONFIRMED:
            patterns["confirmed_count"] += 1
        elif status == FeedbackStatus.REJECTED:
            patterns["rejected_count"] += 1

    patterns["hints"] = _build_hints(patterns)
    save_patterns(patterns)
    return {"weights": weights, "patterns": patterns}


def _build_hints(patterns: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    confirmed = patterns.get("confirmed_keywords", {})
    rejected = patterns.get("rejected_keywords", {})
    if confirmed:
        top = sorted(confirmed.items(), key=lambda x: -x[1])[:5]
        hints.append(
            "Эксперт чаще подтверждает гипотезы с темами: "
            + ", ".join(k for k, _ in top)
        )
    if rejected:
        top = sorted(rejected.items(), key=lambda x: -x[1])[:5]
        hints.append(
            "Избегайте акцентов на: " + ", ".join(k for k, _ in top)
        )
    return hints


def get_generation_hints() -> str:
    patterns = load_patterns()
    hints = patterns.get("hints") or _build_hints(patterns)
    if not hints:
        return ""
    return "Expert feedback hints:\n" + "\n".join(f"- {h}" for h in hints)


def get_learned_weights() -> dict[str, float]:
    return load_adjusted_weights()

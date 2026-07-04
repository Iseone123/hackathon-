"""Online learning весов ранжирования по фидбэку эксперта."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.models import FeedbackStatus

FEEDBACK_FILE = "feedback_weights.json"
LEARNING_RATE = 0.05


def _feedback_path() -> Path:
    return settings.data_dir_path / FEEDBACK_FILE


def load_adjusted_weights() -> dict[str, float]:
    path = _feedback_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return settings.ranking_weights()


def save_weights(weights: dict[str, float]) -> None:
    path = _feedback_path()
    path.write_text(json.dumps(weights, indent=2), encoding="utf-8")


def update_weights_from_feedback(
    status: FeedbackStatus,
    expert_scores: dict[str, float] | None = None,
) -> dict[str, float]:
    """Bandit-подход: сдвиг весов к критериям, которые эксперт подтвердил."""
    weights = load_adjusted_weights()
    if status == FeedbackStatus.CONFIRMED and expert_scores:
        for key, score in expert_scores.items():
            if key in weights and score >= 7:
                weights[key] = min(weights[key] + LEARNING_RATE, 0.5)
    elif status == FeedbackStatus.REJECTED and expert_scores:
        for key, score in expert_scores.items():
            if key in weights and score <= 3:
                weights[key] = max(weights[key] - LEARNING_RATE, 0.05)

    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    save_weights(weights)
    return weights

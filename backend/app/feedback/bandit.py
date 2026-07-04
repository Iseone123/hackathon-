"""Online learning весов ранжирования по фидбэку эксперта."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.feedback.scores import RANKING_CRITERIA, criterion_scores_from_hypothesis
from app.models import FeedbackStatus

FEEDBACK_FILE = "feedback_weights.json"
LEARNING_RATE = 0.05
STATUS_LEARNING_RATE = 0.02


def _feedback_path() -> Path:
    return settings.data_dir_path / FEEDBACK_FILE


def load_adjusted_weights() -> dict[str, float]:
    path = _feedback_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return settings.ranking_weights()


def save_weights(weights: dict[str, float]) -> None:
    _feedback_path().write_text(json.dumps(weights, indent=2), encoding="utf-8")


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        return settings.ranking_weights()
    return {k: v / total for k, v in weights.items()}


def _apply_expert_scores(
    weights: dict[str, float],
    expert_scores: dict[str, float],
    *,
    confirmed: bool,
    lr: float,
) -> None:
    for key, score in expert_scores.items():
        if key not in weights:
            continue
        if confirmed and score >= 7:
            weights[key] = min(weights[key] + lr, 0.5)
        elif not confirmed and score <= 3:
            weights[key] = max(weights[key] - lr, 0.05)


def _apply_hypothesis_scores(
    weights: dict[str, float],
    hyp_scores: dict[str, float],
    *,
    confirmed: bool,
) -> None:
    for key in RANKING_CRITERIA:
        if key not in weights or key not in hyp_scores:
            continue
        val = hyp_scores[key]
        if confirmed and val >= 7:
            weights[key] = min(weights[key] + STATUS_LEARNING_RATE, 0.5)
        elif not confirmed and val >= 7:
            weights[key] = max(weights[key] - STATUS_LEARNING_RATE * 0.5, 0.05)


def update_weights_from_feedback(
    status: FeedbackStatus,
    expert_scores: dict[str, float] | None = None,
    hypothesis: dict | None = None,
) -> dict[str, float]:
    weights = load_adjusted_weights()
    confirmed = status == FeedbackStatus.CONFIRMED

    if expert_scores:
        _apply_expert_scores(weights, expert_scores, confirmed=confirmed, lr=LEARNING_RATE)
    else:
        _apply_hypothesis_scores(weights, criterion_scores_from_hypothesis(hypothesis), confirmed=confirmed)

    weights = _normalize_weights(weights)
    save_weights(weights)
    return weights


def update_weights_from_profiles(
    confirmed_avg: dict[str, float],
    rejected_avg: dict[str, float],
) -> dict[str, float]:
    weights = load_adjusted_weights()
    for key in RANKING_CRITERIA:
        if key not in weights:
            continue
        c, r = confirmed_avg.get(key), rejected_avg.get(key)
        if c is None or r is None:
            continue
        delta = (c - r) / 10.0
        if abs(delta) > 0.15:
            weights[key] = max(0.05, min(0.5, weights[key] + LEARNING_RATE * delta))
    weights = _normalize_weights(weights)
    save_weights(weights)
    return weights

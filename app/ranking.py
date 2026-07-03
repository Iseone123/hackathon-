"""Ранжирование гипотез по фиксированным весам."""

from __future__ import annotations

from app.config import RANKING_WEIGHTS
from app.generate import Hypothesis


def _normalize_score(value: float, max_value: float = 10.0) -> float:
    return max(0.0, min(value / max_value, 1.0))


def compute_composite_score(hypothesis: Hypothesis) -> float:
    """Считает итоговый балл: новизна + ценность + (10 − риск)."""
    novelty = _normalize_score(hypothesis.novelty_score)
    value = _normalize_score(hypothesis.expected_value_score)
    # Меньше риск — лучше
    risk_inverted = _normalize_score(10.0 - hypothesis.risk_score)

    return (
        RANKING_WEIGHTS["novelty"] * novelty
        + RANKING_WEIGHTS["expected_value"] * value
        + RANKING_WEIGHTS["risk"] * risk_inverted
    )


def rank_hypotheses(hypotheses: list[Hypothesis]) -> list[Hypothesis]:
    """Присваивает composite_score и сортирует по убыванию."""
    for h in hypotheses:
        h.composite_score = compute_composite_score(h)
    return sorted(hypotheses, key=lambda h: h.composite_score, reverse=True)

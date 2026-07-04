"""Извлечение оценок гипотезы для обучения на фидбэке."""

from __future__ import annotations

from typing import Any

RANKING_CRITERIA = ("novelty", "feasibility", "expected_value", "risk")

_SCORE_FIELDS = {
    "novelty": "novelty_score",
    "feasibility": "feasibility_score",
    "expected_value": "expected_value_score",
}


def criterion_scores_from_hypothesis(hypothesis: dict[str, Any] | None) -> dict[str, float]:
    """Нормализованные оценки критериев ранжирования из dict гипотезы."""
    if not hypothesis:
        return {}

    scores: dict[str, float] = {}
    for key, field in _SCORE_FIELDS.items():
        val = hypothesis.get(field)
        if val is not None:
            scores[key] = float(val)

    risk = hypothesis.get("risk") or {}
    if isinstance(risk, dict):
        tech, econ = risk.get("technical"), risk.get("economic")
        if tech is not None and econ is not None:
            scores["risk"] = (float(tech) + float(econ)) / 2

    return scores


def empty_score_profile() -> dict[str, dict[str, float | int]]:
    return {k: {"sum": 0.0, "count": 0} for k in RANKING_CRITERIA}


def profile_averages(profile: dict[str, dict[str, float | int]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in RANKING_CRITERIA:
        entry = profile.get(key) or {}
        count = int(entry.get("count", 0))
        if count:
            out[key] = float(entry["sum"]) / count
    return out

"""Целевые метрики качества по вердиктам судьи."""

from __future__ import annotations

from app.config import settings
from app.models import JudgeVerdict


def hypothesis_objective_score(
    verdict: JudgeVerdict,
    *,
    approval_weight: float | None = None,
    score_weight: float | None = None,
) -> float:
    """Балл одной гипотезы в [0, 1] — чем выше, тем лучше вердикт судьи."""
    w_approval = (
        approval_weight
        if approval_weight is not None
        else settings.judge_objective_approval_weight
    )
    w_score = (
        score_weight if score_weight is not None else settings.judge_objective_score_weight
    )
    approval_bonus = 1.0 if verdict.approved else 0.0
    score_norm = verdict.overall_score / 10.0
    return round(w_approval * approval_bonus + w_score * score_norm, 4)


def generation_judge_quality_index(verdicts: list[JudgeVerdict]) -> dict[str, float]:
    """
    JQI (Judge Quality Index) — главная метрика прогона, шкала 0–100.
    Максимизируем долю одобрений, средний балл судьи и привязку к источникам.
    """
    if not verdicts:
        return {
            "jqi": 0.0,
            "approval_rate": 0.0,
            "avg_objective": 0.0,
            "grounding_rate": 0.0,
        }

    total = len(verdicts)
    approved = sum(1 for v in verdicts if v.approved)
    approval_rate = approved / total
    avg_score_norm = sum(v.overall_score for v in verdicts) / total / 10.0
    grounded_rate = sum(1 for v in verdicts if v.source_grounded) / total
    objectives = [hypothesis_objective_score(v) for v in verdicts]
    avg_objective = sum(objectives) / total

    jqi = 100 * (
        settings.judge_jqi_approval_weight * approval_rate
        + settings.judge_jqi_score_weight * avg_score_norm
        + settings.judge_jqi_grounding_weight * grounded_rate
    )
    return {
        "jqi": round(jqi, 2),
        "approval_rate": round(approval_rate, 4),
        "avg_objective": round(avg_objective, 4),
        "grounding_rate": round(grounded_rate, 4),
    }

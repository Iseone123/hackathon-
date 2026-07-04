"""API: экспертные настройки (веса ранжирования)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import settings
from app.feedback.bandit import load_adjusted_weights, save_weights
from app.models import RankingWeightsUpdate
from app.security.auth import require_role

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/ranking-weights")
def get_ranking_weights(_role: str = Depends(require_role("viewer"))) -> dict[str, float]:
    learned = load_adjusted_weights()
    if learned:
        return learned
    return settings.ranking_weights()


@router.patch("/ranking-weights")
def patch_ranking_weights(
    body: RankingWeightsUpdate,
    _role: str = Depends(require_role("admin")),
) -> dict[str, float]:
    current = load_adjusted_weights() or settings.ranking_weights()
    updated = {
        "novelty": body.novelty if body.novelty is not None else current["novelty"],
        "feasibility": body.feasibility if body.feasibility is not None else current["feasibility"],
        "expected_value": (
            body.expected_value if body.expected_value is not None else current["expected_value"]
        ),
        "risk": body.risk if body.risk is not None else current["risk"],
    }
    total = sum(updated.values())
    if total <= 0:
        updated = settings.ranking_weights()
    else:
        updated = {k: v / total for k, v in updated.items()}
    save_weights(updated)
    return updated

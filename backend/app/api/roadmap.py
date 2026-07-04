"""API: шаблоны и сводка дорожной карты."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.hypotheses.roadmap_builder import (
    RESOURCE_TEMPLATES,
    build_structured_roadmap,
    summarize_roadmap,
)
from app.hypotheses.store import load_hypothesis
from app.models import RoadmapStep

router = APIRouter(prefix="/roadmap", tags=["roadmap"])


@router.get("/templates")
def list_templates() -> dict[str, Any]:
    return {
        "templates": [
            {
                "id": t["id"],
                "label": t["label"],
                "duration_days": t["duration_days"],
                "resources": t["resources"],
                "cost_rub": t.get("cost_rub"),
            }
            for t in RESOURCE_TEMPLATES
        ]
    }


@router.get("/{hypothesis_id}/summary")
def roadmap_summary(hypothesis_id: str) -> dict[str, Any]:
    hypothesis = load_hypothesis(hypothesis_id)
    if not hypothesis:
        raise HTTPException(status_code=404, detail="Гипотеза не найдена")
    steps = build_structured_roadmap(hypothesis)
    summary = summarize_roadmap(steps)
    return {
        "hypothesis_id": hypothesis_id,
        "steps": [RoadmapStep.model_validate(s).model_dump() for s in steps],
        **summary,
    }

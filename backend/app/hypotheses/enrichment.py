"""Обогащение гипотез: roadmap, analysis, business case, scoring."""

from __future__ import annotations

from typing import Any

from app.hypotheses.business_case import build_business_case
from app.hypotheses.research_analysis import build_research_analysis
from app.hypotheses.roadmap_builder import build_structured_roadmap, roadmap_to_text
from app.models import Hypothesis
from app.scoring.ranker import Ranker


def enrich_hypothesis(
    hypothesis: Hypothesis,
    *,
    problem: str,
    constraints: str,
    chunks: list[dict[str, Any]],
    knowledge_gaps: list[Any] | None,
    ranker: Ranker,
    weights: dict[str, float] | None,
) -> Hypothesis:
    """Roadmap → research analysis → business case → ranker score."""
    hypothesis.structured_roadmap = build_structured_roadmap(hypothesis)
    hypothesis.verification_roadmap = roadmap_to_text(hypothesis.structured_roadmap)
    hypothesis.research_analysis = build_research_analysis(
        hypothesis, problem, chunks, knowledge_gaps or []
    )
    ra = hypothesis.research_analysis
    hypothesis.business_case = build_business_case(
        hypothesis,
        problem,
        constraints,
        chunks,
        predicted_delta_pct=ra.predicted_kpi_delta_pct if ra else None,
        model_confidence=(
            "high" if ra and ra.model_r2 and ra.model_r2 > 0.3 else "medium"
        ),
    )
    return ranker.score_hypothesis(hypothesis, weights=weights)

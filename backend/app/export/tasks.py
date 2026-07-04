"""Экспорт задач CSV/JSON для Jira/YouTrack."""

from __future__ import annotations

import csv
import json
from io import StringIO
from typing import Any

from app.models import Hypothesis


def export_tasks_json(hypotheses: list[Hypothesis], generation_id: str) -> dict[str, Any]:
    tasks = []
    for h in hypotheses:
        tasks.append(
            {
                "summary": h.text[:120],
                "description": (
                    f"Механизм: {h.mechanism}\n\n"
                    f"Обоснование: {h.reasoning}\n\n"
                    f"Score: {h.score_breakdown.composite if h.score_breakdown else 0}"
                ),
                "labels": ["hypothesis", generation_id[:8]],
                "custom_fields": {
                    "novelty": h.novelty_score,
                    "feasibility": h.feasibility_score,
                    "expected_value": h.expected_value_score,
                    "risk_technical": h.risk.technical,
                    "risk_economic": h.risk.economic,
                },
                "verification_roadmap": h.verification_roadmap or [],
                "structured_roadmap": [
                    s.model_dump() if hasattr(s, "model_dump") else s
                    for s in (h.structured_roadmap or [])
                ],
                "research_analysis": (
                    h.research_analysis.model_dump()
                    if h.research_analysis
                    else None
                ),
                "business_case": (
                    h.business_case.model_dump() if h.business_case else None
                ),
                "sources": [s.model_dump() for s in h.sources],
            }
        )
    return {"generation_id": generation_id, "tasks": tasks}


def export_tasks_csv(hypotheses: list[Hypothesis], generation_id: str) -> str:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "summary",
            "mechanism",
            "novelty",
            "feasibility",
            "expected_value",
            "risk_technical",
            "risk_economic",
            "composite_score",
            "sources",
        ]
    )
    for h in hypotheses:
        score = h.score_breakdown.composite if h.score_breakdown else 0
        sources = "; ".join(s.doc_id for s in h.sources)
        writer.writerow(
            [
                h.id,
                h.text,
                h.mechanism,
                h.novelty_score,
                h.feasibility_score,
                h.expected_value_score,
                h.risk.technical,
                h.risk.economic,
                score,
                sources,
            ]
        )
    return output.getvalue()

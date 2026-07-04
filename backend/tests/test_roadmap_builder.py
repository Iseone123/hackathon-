"""Тесты конструктора roadmap."""

from __future__ import annotations

from app.hypotheses.roadmap_builder import (
    RESOURCE_TEMPLATES,
    reorder_steps,
    step_from_template,
    summarize_roadmap,
)
from app.models import RoadmapStep


def test_resource_templates_not_empty():
    assert len(RESOURCE_TEMPLATES) >= 3
    assert all("id" in t and "resources" in t for t in RESOURCE_TEMPLATES)


def test_summarize_roadmap_totals():
    steps = [
        RoadmapStep(step_order=1, title="A", duration_days=7, resources=["пробы"]),
        RoadmapStep(step_order=2, title="B", duration_days=14, resources=["реагент", "анализ"]),
    ]
    summary = summarize_roadmap(steps)
    assert summary["total_days"] == 21
    assert summary["step_count"] == 2
    assert summary["estimated_cost_rub"] > 0
    assert "пробы" in summary["resources_unique"]


def test_step_from_template():
    step = step_from_template("lab_baseline", 1)
    assert step is not None
    assert step.duration_days == 7
    assert step.resources


def test_reorder_steps():
    steps = [
        RoadmapStep(step_order=1, title="First"),
        RoadmapStep(step_order=2, title="Second"),
    ]
    reordered = reorder_steps(steps, [2, 1])
    assert reordered[0].title == "Second"
    assert reordered[0].step_order == 1
    assert reordered[1].title == "First"

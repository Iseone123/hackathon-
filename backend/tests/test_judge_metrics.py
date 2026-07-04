"""Тесты целевых метрик судьи."""

from __future__ import annotations

from app.judge.metrics import generation_judge_quality_index, hypothesis_objective_score
from app.models import JudgeVerdict


class TestJudgeMetrics:
    def test_objective_score_approved_higher_than_rejected(self):
        approved = JudgeVerdict(approved=True, overall_score=8.0, source_grounded=True)
        rejected = JudgeVerdict(approved=False, overall_score=8.0, source_grounded=True)
        assert hypothesis_objective_score(approved) > hypothesis_objective_score(rejected)

    def test_objective_score_in_range(self):
        verdict = JudgeVerdict(approved=True, overall_score=10.0)
        score = hypothesis_objective_score(verdict)
        assert 0 <= score <= 1

    def test_jqi_perfect_run(self):
        verdicts = [
            JudgeVerdict(approved=True, overall_score=10.0, source_grounded=True),
            JudgeVerdict(approved=True, overall_score=10.0, source_grounded=True),
        ]
        metrics = generation_judge_quality_index(verdicts)
        assert metrics["jqi"] == 100.0
        assert metrics["approval_rate"] == 1.0
        assert metrics["grounding_rate"] == 1.0

    def test_jqi_empty(self):
        metrics = generation_judge_quality_index([])
        assert metrics["jqi"] == 0.0

"""Тесты бизнес-кейса: корректный парсинг прироста KPI."""

from __future__ import annotations

from app.hypotheses.business_case import build_business_case
from app.models import Hypothesis, RiskScores, SourceRef


def test_delta_not_from_pulp_density():
    h = Hypothesis(
        id="h1",
        text="Повышение плотности пульпы с 30% до 35% при pH 9 увеличит извлечение меди на 3%",
        mechanism="механизм",
        novelty_score=7,
        feasibility_score=8,
        expected_value_score=8,
        risk=RiskScores(technical=4, economic=3),
        sources=[SourceRef(doc_id="d1", snippet="текст")],
        reasoning="обоснование",
    )
    bc = build_business_case(h, "извлечение меди", "без капитальных вложений", [])
    assert bc.expected_delta_pct == 3.0
    assert bc.annual_revenue_impact_rub == 24375000

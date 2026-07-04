"""Тесты decision_rationale."""

from __future__ import annotations

from app.judge.rationale import build_decision_rationale
from app.models import (
    CaseCheckItem,
    CaseCompliance,
    Hypothesis,
    JudgeVerdict,
    RiskScores,
    SourceRef,
)


def _hypothesis() -> Hypothesis:
    return Hypothesis(
        id="h1",
        text="Добавление 0,4 кг/т КМЦ при pH 9 повысит извлечение меди на ≥3%",
        mechanism="Подавление пустой породы",
        novelty_score=7,
        feasibility_score=6,
        expected_value_score=8,
        risk=RiskScores(technical=4, economic=3),
        sources=[
            SourceRef(
                doc_id="book_123",
                snippet="КМЦ 0,3—0,5 кг/т для подавления пустой породы",
            )
        ],
        reasoning="Источник указывает дозировку КМЦ",
    )


def test_approval_rationale_lists_checks():
    compliance = CaseCompliance(
        items=[
            CaseCheckItem(
                key="sources",
                label="Ссылки на источники",
                required=True,
                passed=True,
            ),
        ],
        mandatory_passed=1,
        mandatory_total=1,
        compliance_pct=100,
        all_mandatory_met=True,
    )
    verdict = JudgeVerdict(
        approved=True,
        overall_score=8.2,
        testability=8,
        evidence_quality=7.5,
        relevance=8,
        source_grounded=True,
        case_compliance=compliance,
    )
    lines = build_decision_rationale(verdict, _hypothesis(), llm_summary="Сильная привязка к источнику")
    text = "\n".join(lines)
    assert "Сильная привязка" in text
    assert "✓ Ссылки на источники" in text
    assert "book_123" in text


def test_rejection_rationale_lists_blocking_issues():
    verdict = JudgeVerdict(
        approved=False,
        issues=["Ограничения: pH вне диапазона 8-10", "Источники: цитата совпала только на 10%"],
    )
    lines = build_decision_rationale(verdict, _hypothesis())
    assert any("Ограничения" in l for l in lines)
    assert any("Источники" in l for l in lines)

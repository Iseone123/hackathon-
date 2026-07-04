"""Тесты чеклиста ТЗ кейса."""

from __future__ import annotations

from app.judge.checklist import evaluate_case_compliance
from app.models import Hypothesis, RiskScores, SourceRef


def _good_hypothesis() -> Hypothesis:
    return Hypothesis(
        id="h1",
        text="Добавка 0,3% КМЦ при pH 8-9 повысит извлечение меди из хвостов КГМК",
        mechanism="КМЦ подавляет минералы пустой породы и улучшает селективность флотации",
        novelty_score=7,
        feasibility_score=8,
        expected_value_score=9,
        risk=RiskScores(technical=4, economic=3),
        sources=[
            SourceRef(
                doc_id="doc1",
                snippet="КМЦ 0,3—0,5 кг/т подавляет минералы пустой породы при флотации",
            )
        ],
        verification_roadmap=[
            "Лабораторная флотация на пробах 1 кг с реагентом КМЦ",
            "Критерий успеха: извлечение меди +5% vs контроль, провал: <2%",
        ],
        reasoning=(
            "В отличие от типовых схем, добавка КМЦ в слабощелочной среде "
            "по doc1 повысит извлечение меди — целевой KPI задачи."
        ),
    )


class TestCaseChecklist:
    def test_good_hypothesis_passes_mandatory(self):
        c = evaluate_case_compliance(_good_hypothesis(), "извлечение меди из хвостов КГМК")
        assert c.all_mandatory_met
        assert c.mandatory_passed == c.mandatory_total

    def test_missing_mechanism_fails(self):
        h = _good_hypothesis()
        h.mechanism = ""
        c = evaluate_case_compliance(h, "извлечение меди")
        assert not c.all_mandatory_met

    def test_roadmap_optional_not_blocking_mandatory(self):
        h = _good_hypothesis()
        h.verification_roadmap = None
        c = evaluate_case_compliance(h, "извлечение меди")
        assert c.all_mandatory_met
        assert c.optional_passed < c.optional_total

    def test_noun_formulation_passes(self):
        h = _good_hypothesis()
        h.text = (
            "Повышение извлечения меди из хвостов КГМК возможно "
            "при оптимизации pH 8-10 и дозировке КМЦ 0,3 кг/т"
        )
        c = evaluate_case_compliance(h, "извлечение меди из хвостов КГМК")
        item = next(i for i in c.items if i.key == "testable_formulation")
        assert item.passed

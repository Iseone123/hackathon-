"""Тесты модуля Судья."""

from __future__ import annotations

from app.judge.validator import HypothesisJudge
from app.models import Hypothesis, RiskScores, SourceRef


def _hypothesis(**kwargs) -> Hypothesis:
    defaults = {
        "id": "h1",
        "text": "Добавка 0.3% ксантогената повысит извлечение меди из хвостов при pH 9",
        "mechanism": "Селективная адсорбция на сульфидах меди улучшает флотируемость",
        "novelty_score": 7,
        "feasibility_score": 8,
        "expected_value_score": 8,
        "risk": RiskScores(technical=4, economic=3),
        "sources": [SourceRef(doc_id="doc1", snippet="флотация медных сульфидов")],
        "verification_roadmap": ["Лабораторная флотация", "Пилот на хвостах"],
        "reasoning": "Согласно doc1, ксантогенаты эффективны для меди",
    }
    defaults.update(kwargs)
    return Hypothesis(**defaults)


class TestJudge:
    def test_structure_check_fails_short_text(self):
        from app.judge.checklist import evaluate_case_compliance

        compliance = evaluate_case_compliance(_hypothesis(text="коротко"), "извлечение меди")
        assert not compliance.all_mandatory_met
        assert compliance.mandatory_passed < compliance.mandatory_total

    def test_source_grounding_with_matching_snippet(self):
        judge = HypothesisJudge.__new__(HypothesisJudge)
        snippet = (
            "флотация медных сульфидов с ксантогенатами при pH девять "
            "повышает извлечение меди"
        )
        h = _hypothesis(sources=[SourceRef(doc_id="doc1", snippet=snippet)])
        chunks_text = (
            "флотация медных сульфидов с ксантогенатами при pH девять "
            "повышает извлечение меди из хвостов"
        )
        grounded, issues = judge._check_sources(
            h, {"doc1"}, chunks_text, {"doc1": chunks_text}
        )
        assert grounded is True

    def test_evaluate_all_without_llm_mock(self):
        judge = HypothesisJudge.__new__(HypothesisJudge)
        judge.llm = None  # type: ignore
        judge.MIN_APPROVE_SCORE = 0

        def fake_review(h, problem, constraints, chunk_text, compliance):
            return {
                "approved": True,
                "testability": 8,
                "evidence_quality": 7,
                "relevance": 8,
                "novelty_assessment": 7,
                "kpi_link": 7,
                "issues": [],
                "recommendations": ["Провести лабораторный тест"],
            }

        judge._llm_review = fake_review  # type: ignore

        snippet = (
            "флотация медных сульфидов с ксантогенатами при pH девять "
            "повышает извлечение меди"
        )
        hyps = [_hypothesis(
            text="Добавка 0.3 кг/т ксантогената повысит извлечение меди на 3% при pH 9",
            reasoning="Согласно doc1, ксантогенаты эффективны для меди в отличие от типовых схем",
            sources=[SourceRef(doc_id="doc1", snippet=snippet)],
        )]
        chunks = [{
            "doc_id": "doc1",
            "text": (
                "флотация медных сульфидов с ксантогенатами при pH девять "
                "повышает извлечение меди из хвостов"
            ),
        }]
        result, summary = judge.evaluate_all(hyps, "извлечение меди", "pH 9", chunks)
        assert len(result) == 1
        assert result[0].judge_verdict is not None
        assert summary.approved >= 1

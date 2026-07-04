"""Тесты строгого режима судьи."""

from __future__ import annotations

from app.judge.validator import HypothesisJudge, _snippet_word_overlap
from app.models import Hypothesis, RiskScores, SourceRef


def _hypothesis(**kwargs) -> Hypothesis:
    snippet = (
        "флотация медных сульфидов с ксантогенатами при pH девять "
        "повышает извлечение меди из хвостов"
    )
    defaults = {
        "id": "h1",
        "text": "Добавка 0.3 кг/т ксантогената повысит извлечение меди из хвостов на 3% при pH 9",
        "mechanism": "Селективная адсорбция на сульфидах меди улучшает флотируемость",
        "novelty_score": 7,
        "feasibility_score": 8,
        "expected_value_score": 8,
        "risk": RiskScores(technical=4, economic=3),
        "sources": [SourceRef(doc_id="doc1", snippet=snippet)],
        "verification_roadmap": ["Лабораторная флотация", "Пилот на хвостах"],
        "reasoning": "Согласно doc1, ксантогенаты эффективны для меди в отличие от типовых схем",
    }
    defaults.update(kwargs)
    return Hypothesis(**defaults)


class TestStrictJudge:
    def test_snippet_overlap_requires_substantial_match(self):
        snippet = "флотация медных сульфидов ксантогенатами извлечение"
        corpus = "флотация медных сульфидов с ксантогенатами при pH"
        assert _snippet_word_overlap(snippet, corpus) >= 0.5
        assert _snippet_word_overlap("совсем другой текст про бары", corpus) < 0.3

    def test_unknown_doc_id_not_grounded(self):
        judge = HypothesisJudge.__new__(HypothesisJudge)
        h = _hypothesis(sources=[SourceRef(doc_id="unknown_doc", snippet="флотация медных сульфидов")])
        grounded, issues = judge._check_sources(h, {"doc1"}, "", {"doc1": "флотация"})
        assert grounded is False
        assert any("не найден" in i for i in issues)

    def test_llm_fallback_rejects(self):
        judge = HypothesisJudge.__new__(HypothesisJudge)

        class BrokenLLM:
            def complete_lite(self, *_a, **_k):
                raise RuntimeError("rate limit")

            def _parse_json(self, _r):
                return {}

        judge.llm = BrokenLLM()  # type: ignore
        from app.judge.checklist import evaluate_case_compliance

        h = _hypothesis()
        compliance = evaluate_case_compliance(h, "извлечение меди")
        raw = judge._llm_review(h, "извлечение меди", "pH 8-10", "ctx", compliance)
        assert raw["approved"] is False
        assert raw["testability"] == 0

    def test_select_for_output_returns_all_sorted(self):
        judge = HypothesisJudge.__new__(HypothesisJudge)
        good = _hypothesis(id="ok")
        bad = _hypothesis(id="bad")
        good.judge_verdict = type("V", (), {"approved": True, "objective_score": 0.9})()
        bad.judge_verdict = type("V", (), {"approved": False, "objective_score": 0.8})()
        out = judge.select_for_output([bad, good], min_output=3)
        assert len(out) == 2
        assert out[0].id == "ok"
        assert out[1].id == "bad"

    def test_low_llm_scores_block_approval_even_if_llm_says_yes(self):
        judge = HypothesisJudge.__new__(HypothesisJudge)
        judge.llm = None  # type: ignore

        def weak_review(*_args, **_kwargs):
            return {
                "approved": True,
                "testability": 5,
                "evidence_quality": 4,
                "relevance": 5,
                "novelty_assessment": 5,
                "kpi_link": 4,
                "issues": [],
                "recommendations": [],
            }

        judge._llm_review = weak_review  # type: ignore
        verdict = judge._evaluate_one(
            _hypothesis(),
            "извлечение меди из хвостов",
            "pH 8-10",
            "флотация медных сульфидов ксантогенатами извлечение",
            {"doc1"},
            {
                "doc1": (
                    "флотация медных сульфидов с ксантогенатами при pH девять "
                    "повышает извлечение меди из хвостов"
                )
            },
        )
        assert verdict.approved is False

"""Тесты многоязычного overlap и чеклиста."""

from __future__ import annotations

from app.judge.checklist import _check_reasoning
from app.models import Hypothesis, RiskScores, SourceRef
from app.rag.text_overlap import citation_overlap


def test_chinese_snippet_overlap():
    snippet = "提高铜的回收率"
    corpus = "在pH=9条件下，提高铜的回收率可达85%"
    assert citation_overlap(snippet, corpus) >= 0.5


def test_brainstorm_rejected_even_with_soglasno():
    h = Hypothesis(
        id="h1",
        text="Добавка реагента повысит извлечение меди на 3%",
        mechanism="механизм",
        novelty_score=7,
        feasibility_score=8,
        expected_value_score=8,
        risk=RiskScores(technical=4, economic=3),
        sources=[SourceRef(doc_id="d1", snippet="цитата из источника")],
        reasoning="Согласно мозговому штурму по флотации, реагент может помочь",
    )
    ok, note = _check_reasoning(h)
    assert ok is False
    assert "мозговой штурм" in note

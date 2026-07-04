"""Прозрачное ранжирование гипотез с настраиваемыми весами."""

from __future__ import annotations

from app.config import settings
from app.db.qdrant_store import QdrantStore
from app.llm_client import YandexLLMClient
from app.models import Hypothesis, ScoreBreakdown


class Ranker:
    def __init__(
        self,
        llm: YandexLLMClient | None = None,
        qdrant: QdrantStore | None = None,
    ) -> None:
        self.llm = llm
        self.qdrant = qdrant

    def _normalize(self, value: float, max_val: float = 10.0) -> float:
        return max(0.0, min(value / max_val, 1.0))

    def _vector_novelty(self, hypothesis: Hypothesis) -> float | None:
        if not self.llm or not self.qdrant:
            return None
        try:
            vector = self.llm.embed_query(hypothesis.text)
            distance = self.qdrant.nearest_novelty_distance(vector)
            return min(distance, 1.0)
        except Exception:
            return None

    def score_hypothesis(
        self,
        hypothesis: Hypothesis,
        weights: dict[str, float] | None = None,
    ) -> Hypothesis:
        w = weights or settings.ranking_weights()
        novelty_llm = self._normalize(hypothesis.novelty_score)
        novelty_vec = self._vector_novelty(hypothesis)
        if novelty_vec is not None:
            novelty = 0.6 * novelty_vec + 0.4 * novelty_llm
        else:
            novelty = novelty_llm

        feasibility = self._normalize(hypothesis.feasibility_score)
        expected_value = self._normalize(hypothesis.expected_value_score)
        avg_risk = (hypothesis.risk.technical + hypothesis.risk.economic) / 2
        risk_inverted = self._normalize(10.0 - avg_risk)

        composite = (
            w.get("novelty", 0.3) * novelty
            + w.get("feasibility", 0.25) * feasibility
            + w.get("expected_value", 0.3) * expected_value
            + w.get("risk", 0.15) * risk_inverted
        )

        hypothesis.score_breakdown = ScoreBreakdown(
            novelty=round(novelty, 4),
            feasibility=round(feasibility, 4),
            expected_value=round(expected_value, 4),
            risk_inverted=round(risk_inverted, 4),
            novelty_vector=round(novelty_vec, 4) if novelty_vec is not None else None,
            novelty_llm=round(novelty_llm, 4),
            weights=w,
            composite=round(composite, 4),
        )
        return hypothesis

    def rank(
        self,
        hypotheses: list[Hypothesis],
        weights: dict[str, float] | None = None,
    ) -> list[Hypothesis]:
        scored = [self.score_hypothesis(h, weights) for h in hypotheses]
        return sorted(
            scored,
            key=lambda h: h.score_breakdown.composite if h.score_breakdown else 0,
            reverse=True,
        )

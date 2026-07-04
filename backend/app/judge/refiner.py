"""Доработка отклонённых гипотез для повышения JQI."""

from __future__ import annotations

import logging
from typing import Any

from app.hypotheses.prompt_sections import build_repair_system
from app.hypotheses.sanitize import sanitize_raw_hypothesis
from app.llm_client import YandexLLMClient
from app.models import Hypothesis

logger = logging.getLogger(__name__)

REPAIR_SYSTEM = build_repair_system()


class HypothesisRefiner:
    def __init__(self, llm: YandexLLMClient | None = None) -> None:
        self.llm = llm or YandexLLMClient()

    def repair(
        self,
        h: Hypothesis,
        problem: str,
        constraints: str,
        chunks: list[dict[str, Any]],
        issues: list[str],
    ) -> dict[str, Any] | None:
        context = "\n".join(
            f"doc_id={c['doc_id']}\n{c['text'][:900]}" for c in chunks[:8]
        )
        user = (
            f"Problem: {problem}\n"
            f"Constraints: {constraints or 'none'}\n\n"
            f"Current hypothesis: {h.text}\n"
            f"Mechanism: {h.mechanism}\n"
            f"Reasoning: {h.reasoning}\n"
            f"Roadmap: {h.verification_roadmap}\n"
            f"Sources: {[s.doc_id for s in h.sources]}\n\n"
            f"Judge issues to fix:\n"
            + "\n".join(f"- {i}" for i in issues)
            + f"\n\nAllowed sources:\n{context}"
        )
        try:
            raw = self.llm.complete_lite(REPAIR_SYSTEM, user)
            data = self.llm._parse_json(raw)
            if not isinstance(data, dict):
                return None
            if "hypotheses" in data and data["hypotheses"]:
                data = data["hypotheses"][0]
            return sanitize_raw_hypothesis(data, chunks)
        except Exception as exc:
            logger.warning("Hypothesis repair failed: %s", exc)
            return None

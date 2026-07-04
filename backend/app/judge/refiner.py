"""Доработка отклонённых гипотез для повышения JQI."""

from __future__ import annotations

import logging
from typing import Any

from app.hypotheses.prompt_sections import CITATION_RULES_SHORT, FORMULATION_RULES_SHORT
from app.hypotheses.sanitize import sanitize_raw_hypothesis
from app.llm_client import YandexLLMClient
from app.models import Hypothesis

logger = logging.getLogger(__name__)

REPAIR_SYSTEM = (
    """You fix research hypotheses so they pass strict quality review.
Respond ONLY with JSON for ONE hypothesis:
{
  "text": "...",
  "mechanism": "...",
  "reasoning": "...",
  "verification_roadmap": ["step1", "step2", "step3"],
  "sources": [{"doc_id": "exact_id_from_context", "snippet": "verbatim quote from context"}],
  "novelty_score": 0-10,
  "feasibility_score": 0-10,
  "expected_value_score": 0-10,
  "risk": {"technical": 0-10, "economic": 0-10},
  "influence_graph": {
    "nodes": [
      {"id": "reagent", "type": "Material", "source_doc_id": "exact_id_from_context"},
      {"id": "flotation", "type": "Process", "source_doc_id": "exact_id_from_context"},
      {"id": "Cu recovery", "type": "Property", "source_doc_id": "exact_id_from_context"}
    ],
    "links": [
      {"source": "reagent", "target": "flotation", "type": "USED_IN"},
      {"source": "flotation", "target": "Cu recovery", "type": "AFFECTS"}
    ],
    "states": [{"id": "lab phase", "type": "State", "phase_order": 1}],
    "transitions": []
  }
}
Rules:
- obey ALL constraints
- use ONLY doc_id values from context
- output text/mechanism/reasoning/roadmap in Russian; translate facts from EN/CN sources
- snippet stays verbatim in the source language (do NOT translate snippet)
- """
    + CITATION_RULES_SHORT
    + "\n- "
    + FORMULATION_RULES_SHORT
    + """
- min 2 roadmap steps with resources and success/failure criteria
- if enterprise brainstorm list in prompt: hypotheses 1–2 MUST be equipment/process from that list, cite [ПРИМЕР] doc_id
- reasoning must explain the snippet (translate foreign snippets into Russian)
"""
)


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

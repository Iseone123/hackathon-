"""Сборка промптов генерации и repair из констант."""

from __future__ import annotations

from app.hypotheses.options import clamp_hypothesis_count
from app.hypotheses.prompt_constants import (
    BAD_EXAMPLE,
    CITATION_RULES,
    CITATION_RULES_SHORT,
    FORMULATION_RULES,
    FORMULATION_RULES_SHORT,
    GOOD_EXAMPLE_CHINESE,
    GOOD_EXAMPLE_ENTERPRISE,
    GOOD_EXAMPLE_FOREIGN,
    GOOD_EXAMPLE_PROCESS,
    HYPOTHESIS_JSON_SCHEMA,
    INFLUENCE_GRAPH_RULES,
    ROLE_PREAMBLE,
    SCORING_GUIDE,
    SOURCE_STRATEGY,
)
from app.rag.example_registry import build_example_hints, infer_example_dirs

# Обратная совместимость для импортов из prompt_sections / prompts
__all__ = [
    "BAD_EXAMPLE",
    "CITATION_RULES",
    "CITATION_RULES_SHORT",
    "FORMULATION_RULES",
    "FORMULATION_RULES_SHORT",
    "build_brainstorm_mandate",
    "build_case_hints",
    "build_generation_system",
    "build_generation_user_footer",
    "build_language_rule",
    "build_repair_system",
    "build_source_strategy_hint",
    "clamp_hypothesis_count",
]

_SYSTEM_SECTIONS = (
    ROLE_PREAMBLE,
    HYPOTHESIS_JSON_SCHEMA,
    CITATION_RULES,
    FORMULATION_RULES,
    SOURCE_STRATEGY,
    INFLUENCE_GRAPH_RULES,
    GOOD_EXAMPLE_PROCESS,
    GOOD_EXAMPLE_ENTERPRISE,
    GOOD_EXAMPLE_FOREIGN,
    GOOD_EXAMPLE_CHINESE,
    BAD_EXAMPLE,
    SCORING_GUIDE,
)


def build_language_rule(language: str = "ru", hypothesis_count: int | None = None) -> str:
    _ = language
    n = clamp_hypothesis_count(hypothesis_count)
    return (
        "OUTPUT LANGUAGE: Russian (русский) — ALWAYS.\n"
        "- text, mechanism, reasoning, verification_roadmap, influence_graph labels — ONLY Russian.\n"
        "- Sources may be EN/CN/other: READ them, EXTRACT facts, TRANSLATE into Russian in hypothesis fields.\n"
        "- sources[].snippet — verbatim from chunk (original language); do NOT translate the snippet.\n"
        f"Generate exactly {n} diverse hypotheses, each with a different intervention/mechanism when possible."
    )


def build_case_hints(problem: str, constraints: str) -> str:
    dirs = infer_example_dirs(problem, constraints)
    hints = build_example_hints(problem, constraints, dirs)
    if not hints:
        return ""
    return "\nCase hints (ground every claim in snippet):\n" + "\n".join(f"- {h}" for h in hints)


def build_brainstorm_mandate(topics: list[str], hypothesis_count: int | None = None) -> str:
    if not topics:
        return ""
    n = clamp_hypothesis_count(hypothesis_count)
    lines = "\n".join(f"  {i + 1}. {t}" for i, t in enumerate(topics[:12]))
    slots = min(n, len(topics))
    return (
        f"\nEnterprise brainstorm directions (from [ПРИМЕР] docx — distribute across {n} hypotheses):\n"
        f"{lines}\n"
        f"- Use up to {slots} distinct directions from this list (round-robin: hypothesis i → direction i mod list size).\n"
        "- Each assigned direction MUST cite the matching [ПРИМЕР] doc_id with a verbatim snippet.\n"
        "- Remaining hypotheses: textbook/patent mechanisms or cross-domain analogies from context.\n"
        "- Do NOT repeat the same direction in multiple hypotheses."
    )


def _has_example_chunks(example_dirs: list[str], chunks: list[dict]) -> bool:
    return bool(example_dirs) and any(
        c.get("from_example") or any(d in (c.get("source") or "") for d in example_dirs)
        for c in chunks
    )


def build_source_strategy_hint(
    example_dirs: list[str],
    chunks: list[dict],
    hypothesis_count: int | None = None,
) -> str:
    if not _has_example_chunks(example_dirs, chunks):
        return ""
    n = clamp_hypothesis_count(hypothesis_count)
    dirs = ", ".join(example_dirs)
    return (
        f"\nSource strategy: blocks [ПРИМЕР] from {dirs} — use for distinct process/equipment directions "
        f"across up to {n} hypotheses. KPI-сводка blocks supply baseline metrics for reasoning."
    )


def build_generation_system(language: str = "ru", hypothesis_count: int | None = None) -> str:
    return "\n\n".join([*_SYSTEM_SECTIONS, build_language_rule(language, hypothesis_count)])


def build_generation_user_footer(
    language: str = "ru",
    hypothesis_count: int | None = None,
) -> str:
    _ = language
    n = clamp_hypothesis_count(hypothesis_count)
    return (
        f"Generate exactly {n} diverse testable hypotheses grounded in the sources above.\n"
        "Each hypothesis: different intervention/mechanism; foreign sources → Russian hypothesis, verbatim snippet.\n\n"
        f"{CITATION_RULES_SHORT}\n"
        f"{FORMULATION_RULES_SHORT}\n"
        "- If [ПРИМЕР] or KPI-сводка blocks exist: spread distinct enterprise directions across hypotheses."
    )


def build_repair_system() -> str:
    return (
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
      {"id": "intervention", "type": "Material|Parameter", "source_doc_id": "exact_id_from_context"},
      {"id": "process", "type": "Process", "source_doc_id": "exact_id_from_context"},
      {"id": "target KPI", "type": "Property", "source_doc_id": "exact_id_from_context"}
    ],
    "links": [
      {"source": "intervention", "target": "process", "type": "MODIFIES"},
      {"source": "process", "target": "target KPI", "type": "AFFECTS"}
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
- if enterprise [ПРИМЕР] blocks exist: ground intervention in matching doc_id with verbatim snippet
- reasoning must explain the snippet (translate foreign snippets into Russian)
"""
    )

"""Сборка RAG-контекста и user prompt для генерации."""

from __future__ import annotations

from typing import Any

from app.feedback.learner import get_generation_hints
from app.hypotheses.prompt_sections import (
    build_case_hints,
    build_generation_user_footer,
    build_source_strategy_hint,
)
from app.models import KnowledgeGap


def build_rag_context(
    retrieval: dict[str, Any],
    knowledge_gaps: list[KnowledgeGap] | None = None,
    *,
    chunk_chars: int = 900,
) -> str:
    example_dirs = retrieval.get("example_dirs", [])
    parts: list[str] = []
    for i, chunk in enumerate(retrieval["chunks"], 1):
        source = chunk.get("source", "")
        is_example = chunk.get("from_example") or any(
            d in source for d in example_dirs
        )
        tag = " [ПРИМЕР]" if is_example else ""
        parts.append(
            f"[{i}]{tag} doc_id={chunk['doc_id']} source={source} score={chunk['score']:.3f}\n"
            f"{chunk['text'][:chunk_chars]}"
        )
    subgraph = retrieval["subgraph"]
    if subgraph.get("nodes"):
        parts.append("\nKnowledge graph excerpt:")
        for node in subgraph["nodes"][:10]:
            src = node.get("properties", {}).get("source") or node.get("source_doc_id") or ""
            suffix = f" [{src}]" if src else ""
            parts.append(f"  - {node['type']}: {node['id']}{suffix}")
        for link in (subgraph.get("links") or [])[:8]:
            parts.append(
                f"  → {link.get('source')} --{link.get('type', '?')}--> {link.get('target')}"
            )
    if knowledge_gaps:
        parts.append("\nKnowledge gaps (address in hypotheses where possible):")
        for g in knowledge_gaps[:5]:
            parts.append(f"  - [{g.severity}] {g.topic}: {g.suggested_action}")
    trace = retrieval.get("agentic_trace") or {}
    if trace.get("enabled"):
        parts.append("\nAgentic RAG trace:")
        coverage = trace.get("coverage") or {}
        if coverage:
            parts.append(
                "  - coverage: "
                f"{coverage.get('chunks', 0)} chunks, "
                f"{coverage.get('documents', 0)} docs, "
                f"steps={', '.join(coverage.get('covered_steps') or [])}"
            )
        for step in (trace.get("steps") or [])[:6]:
            status = step.get("error") or f"{step.get('chunks', 0)} chunks"
            parts.append(
                f"  - {step.get('name')}: {step.get('intent')} -> {status}"
            )
    return "\n\n".join(parts)


def build_generation_user_prompt(
    problem: str,
    constraints: str,
    context: str,
    conflicts: list[str],
    *,
    example_dirs: list[str] | None = None,
    chunks: list[dict[str, Any]] | None = None,
) -> str:
    conflict_text = ""
    if conflicts:
        conflict_text = "\n\nDetected conflicts in sources:\n" + "\n".join(
            f"- {c}" for c in conflicts
        )
    constraint_block = constraints or "none"
    feedback_hints = get_generation_hints()
    hints_block = f"\n\n{feedback_hints}" if feedback_hints else ""
    case_block = build_case_hints(problem, constraints)
    strategy_block = build_source_strategy_hint(
        example_dirs or [],
        chunks or [],
    )
    return (
        f"Target problem:\n{problem}\n\n"
        f"Constraints (MUST obey — violations = automatic rejection):\n{constraint_block}"
        f"{case_block}{strategy_block}\n\n"
        f"Relevant sources and knowledge graph:\n{context}"
        f"{conflict_text}{hints_block}\n\n"
        "Note: sources may be in RU/EN/CN — extract facts and write hypotheses in Russian; "
        "keep sources[].snippet verbatim from the chunk.\n\n"
        f"{build_generation_user_footer()}"
    )

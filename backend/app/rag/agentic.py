"""Agentic RAG orchestration.

The base retriever answers one query. This layer plans several focused retrieval
steps, executes them, merges evidence, and returns a trace that explains why a
chunk entered the generation context.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from app.config import settings
from app.rag.corpus_graph import merge_subgraphs


class SupportsRetrieve(Protocol):
    def retrieve(
        self,
        problem: str,
        constraints: str = "",
        top_k: int | None = None,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class RAGPlanStep:
    name: str
    intent: str
    query: str
    priority: float = 1.0


class AgenticRAGRetriever:
    """Multi-step retrieval planner around an existing retriever.

    It is deterministic by default, so it works before LLM/tool API keys are
    available. Later, the planning method can be replaced by an LLM planner
    without changing the generation pipeline contract.
    """

    def __init__(self, base: SupportsRetrieve) -> None:
        self.base = base

    def retrieve(
        self,
        problem: str,
        constraints: str = "",
        top_k: int | None = None,
    ) -> dict[str, Any]:
        if not settings.agentic_rag_enabled:
            result = self.base.retrieve(problem, constraints, top_k)
            result["agentic_trace"] = {"enabled": False}
            return result

        target_k = top_k or settings.retrieval_top_k
        step_k = max(3, min(settings.agentic_rag_step_top_k, target_k))
        plan = self.build_plan(problem, constraints)[: settings.agentic_rag_max_steps]

        all_chunks: list[dict[str, Any]] = []
        subgraphs: list[dict[str, Any]] = []
        conflicts: list[str] = []
        keywords: list[str] = []
        example_dirs: list[str] = []
        brainstorm_topics: list[str] = []
        qdrant_total = 0
        step_traces: list[dict[str, Any]] = []

        for step in plan:
            focused_constraints = self._focused_constraints(problem, constraints, step)
            try:
                result = self.base.retrieve(step.query, focused_constraints, step_k)
            except Exception as exc:  # retrieval should be best-effort per step
                step_traces.append(
                    {
                        "name": step.name,
                        "intent": step.intent,
                        "query": step.query,
                        "chunks": 0,
                        "documents": [],
                        "error": str(exc),
                    }
                )
                continue

            chunks = [self._annotate_chunk(c, step) for c in result.get("chunks", [])]
            all_chunks.extend(chunks)
            subgraphs.append(result.get("subgraph") or {"nodes": [], "links": []})
            conflicts.extend(result.get("conflicts") or [])
            keywords.extend(result.get("keywords") or [])
            example_dirs.extend(result.get("example_dirs") or [])
            brainstorm_topics.extend(result.get("brainstorm_topics") or [])
            qdrant_total = max(qdrant_total, int(result.get("qdrant_total") or 0))
            step_traces.append(
                {
                    "name": step.name,
                    "intent": step.intent,
                    "query": step.query,
                    "chunks": len(chunks),
                    "documents": sorted({c.get("doc_id", "") for c in chunks if c.get("doc_id")}),
                }
            )

        if not all_chunks:
            fallback = self.base.retrieve(problem, constraints, top_k)
            fallback["agentic_trace"] = {
                "enabled": True,
                "fallback": True,
                "plan": [asdict(s) for s in plan],
                "steps": step_traces,
            }
            return fallback

        chunks = self._select_evidence(all_chunks, target_k)
        subgraph = merge_subgraphs(*subgraphs)
        trace = {
            "enabled": True,
            "fallback": False,
            "plan": [asdict(s) for s in plan],
            "steps": step_traces,
            "coverage": {
                "chunks": len(chunks),
                "documents": len({c.get("doc_id", "") for c in chunks if c.get("doc_id")}),
                "covered_steps": sorted(
                    {
                        step
                        for c in chunks
                        for step in c.get("agent_steps", [c.get("agent_step", "")])
                        if step
                    }
                ),
            },
        }

        return {
            "chunks": chunks,
            "subgraph": subgraph,
            "conflicts": self._dedupe_strings(conflicts)[:5],
            "keywords": self._dedupe_strings(keywords)[:20],
            "example_dirs": self._dedupe_strings(example_dirs),
            "brainstorm_topics": self._dedupe_strings(brainstorm_topics)[:20],
            "qdrant_total": qdrant_total,
            "agentic_trace": trace,
        }

    def build_plan(self, problem: str, constraints: str = "") -> list[RAGPlanStep]:
        topic = self._compact_topic(problem)
        plan = [
            RAGPlanStep(
                name="core_evidence",
                intent="Find directly relevant facts and prior results.",
                query=f"{problem}\n{constraints}".strip(),
                priority=1.0,
            ),
            RAGPlanStep(
                name="mechanism",
                intent="Find mechanistic explanations that can ground hypotheses.",
                query=f"механизм влияния {topic} минералы процесс параметры извлечение",
                priority=0.95,
            ),
            RAGPlanStep(
                name="verification",
                intent="Find lab verification methods and success criteria.",
                query=f"лабораторная проверка гипотезы {topic} критерии успеха опыт",
                priority=0.85,
            ),
            RAGPlanStep(
                name="risks_constraints",
                intent="Find risks, limitations, constraints, and side effects.",
                query=f"риски ограничения побочные эффекты {topic} оборудование экономика",
                priority=0.8,
            ),
            RAGPlanStep(
                name="analogs",
                intent="Find analogous experiments, expert examples, and reusable patterns.",
                query=f"аналогичные эксперименты экспертные гипотезы примеры {topic}",
                priority=0.75,
            ),
        ]
        if constraints:
            plan.insert(
                2,
                RAGPlanStep(
                    name="constraint_fit",
                    intent="Check that retrieved options fit explicit user constraints.",
                    query=f"{constraints}\nподбор решений под ограничения {topic}",
                    priority=0.9,
                ),
            )
        return plan

    def _focused_constraints(
        self,
        problem: str,
        constraints: str,
        step: RAGPlanStep,
    ) -> str:
        parts = [
            f"Original problem: {problem}",
            f"Retrieval intent: {step.intent}",
        ]
        if constraints:
            parts.append(f"Original constraints: {constraints}")
        return "\n".join(parts)

    def _annotate_chunk(self, chunk: dict[str, Any], step: RAGPlanStep) -> dict[str, Any]:
        annotated = dict(chunk)
        annotated["agent_step"] = step.name
        annotated["agent_intent"] = step.intent
        annotated["score"] = float(annotated.get("score") or 0.0) + 0.03 * step.priority
        return annotated

    def _select_evidence(
        self,
        chunks: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        by_key: dict[tuple[str, int, str], dict[str, Any]] = {}
        support: dict[tuple[str, int, str], set[str]] = {}

        for chunk in chunks:
            key = (
                str(chunk.get("doc_id") or chunk.get("source") or ""),
                int(chunk.get("chunk_index") or 0),
                str(chunk.get("text", ""))[:160],
            )
            current = by_key.get(key)
            if current is None or float(chunk.get("score") or 0) > float(current.get("score") or 0):
                by_key[key] = dict(chunk)
            support.setdefault(key, set()).add(str(chunk.get("agent_step") or "unknown"))

        merged: list[dict[str, Any]] = []
        for key, chunk in by_key.items():
            steps = sorted(support.get(key) or set())
            chunk["agent_steps"] = steps
            chunk["agent_support_count"] = len(steps)
            chunk["score"] = float(chunk.get("score") or 0.0) + 0.04 * (len(steps) - 1)
            merged.append(chunk)

        merged.sort(
            key=lambda c: (
                int(c.get("agent_support_count") or 1),
                float(c.get("score") or 0.0),
            ),
            reverse=True,
        )
        return merged[:limit]

    def _compact_topic(self, text: str) -> str:
        words = re.findall(r"[а-яёa-zA-Z0-9%+\-.]{3,}", text.lower())
        stop = {
            "для",
            "при",
            "или",
            "and",
            "the",
            "что",
            "как",
            "без",
            "повысить",
            "снизить",
            "улучшить",
        }
        result: list[str] = []
        for word in words:
            if word in stop or word in result:
                continue
            result.append(word)
            if len(result) >= 10:
                break
        return " ".join(result) or text[:120]

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                out.append(value)
        return out

"""Генерация гипотез с structured JSON и self-consistency."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.feedback.learner import get_learned_weights
from app.hypotheses.context_builder import build_generation_user_prompt, build_rag_context
from app.hypotheses.enrichment import enrich_hypothesis
from app.hypotheses.hypothesis_factory import build_hypothesis_from_raw
from app.hypotheses.problem_input import normalize_problem_constraints
from app.hypotheses.options import clamp_hypothesis_count
from app.hypotheses.prompt_sections import build_generation_system
from app.hypotheses.sanitize import dedupe_key, relax_raw_hypothesis, sanitize_raw_hypothesis
from app.judge.refiner import HypothesisRefiner
from app.judge.validator import HypothesisJudge
from app.llm_client import YandexLLMClient
from app.models import Hypothesis
from app.rag.agentic import AgenticRAGRetriever
from app.rag.knowledge_gaps import analyze_knowledge_gaps
from app.rag.retrieval import RAGRetriever
from app.rag.source_info import build_retrieval_sources
from app.scoring.ranker import Ranker
from app.security.encryption import write_secure_json


class HypothesisGenerator:
    def __init__(
        self,
        llm: YandexLLMClient | None = None,
        retriever: RAGRetriever | None = None,
        ranker: Ranker | None = None,
        judge: HypothesisJudge | None = None,
        refiner: HypothesisRefiner | None = None,
    ) -> None:
        self.llm = llm or YandexLLMClient()
        self.retriever = retriever or RAGRetriever(llm=self.llm)
        self.ranker = ranker or Ranker(llm=self.llm)
        self.judge = judge or HypothesisJudge(llm=self.llm)
        self.refiner = refiner or HypothesisRefiner(llm=self.llm)
        self.agentic_retriever = AgenticRAGRetriever(self.retriever)

    def generate(
        self,
        problem: str,
        constraints: str = "",
        language: str = "ru",
        top_k: int | None = None,
        weights: dict[str, float] | None = None,
        hypothesis_count: int | None = None,
    ) -> dict[str, Any]:
        problem, constraints = normalize_problem_constraints(problem, constraints)
        n = clamp_hypothesis_count(hypothesis_count)
        retrieval = self.agentic_retriever.retrieve(problem, constraints, top_k)
        knowledge_gaps = analyze_knowledge_gaps(
            problem, constraints, retrieval["chunks"], retrieval.get("keywords")
        )
        context = build_rag_context(retrieval, knowledge_gaps)
        user_prompt = build_generation_user_prompt(
            problem,
            constraints,
            context,
            retrieval["conflicts"],
            example_dirs=retrieval.get("example_dirs"),
            chunks=retrieval["chunks"],
            brainstorm_topics=retrieval.get("brainstorm_topics"),
            hypothesis_count=n,
        )

        if weights is None:
            weights = get_learned_weights()

        system_prompt = build_generation_system(language, hypothesis_count=n)
        samples = self.llm.complete_json(
            system_prompt,
            user_prompt,
            samples=settings.generation_samples,
        )
        merged = self._merge_samples(samples, retrieval["chunks"])
        if not merged:
            raise ValueError(
                "LLM не вернул гипотез в требуемом формате. "
                "Повторите запрос через 1–2 минуты или упростите формулировку задачи."
            )
        generation_id = str(uuid.uuid4())

        hypotheses = self._build_hypotheses(
            merged, generation_id, retrieval["chunks"], weights, problem, constraints, knowledge_gaps
        )
        if not hypotheses:
            raise ValueError("Не удалось собрать ни одной гипотезы из ответа LLM.")
        hypotheses, judge_summary = self._judge_and_optimize(
            hypotheses, problem, constraints, retrieval, weights
        )

        result = {
            "generation_id": generation_id,
            "problem": problem,
            "constraints": constraints,
            "hypotheses": hypotheses,
            "conflicts_detected": retrieval["conflicts"],
            "retrieval_doc_ids": list({c["doc_id"] for c in retrieval["chunks"]}),
            "retrieval_sources": build_retrieval_sources(retrieval["chunks"]),
            "knowledge_gaps": knowledge_gaps,
            "agentic_trace": retrieval.get("agentic_trace"),
            "judge_summary": judge_summary,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._persist(result)
        return result

    def _judge_and_optimize(
        self,
        hypotheses: list[Hypothesis],
        problem: str,
        constraints: str,
        retrieval: dict[str, Any],
        weights: dict[str, float] | None,
    ) -> tuple[list[Hypothesis], Any]:
        chunks = retrieval["chunks"]

        hypotheses, judge_summary = self.judge.evaluate_all(
            hypotheses, problem, constraints, chunks
        )

        for _ in range(settings.judge_repair_passes):
            if judge_summary.jqi >= settings.judge_quality_target:
                break
            repaired = self._repair_rejected(
                hypotheses, problem, constraints, chunks, weights
            )
            if not repaired:
                break
            hypotheses, judge_summary = self.judge.evaluate_all(
                repaired, problem, constraints, chunks
            )

        output = self.judge.select_for_output(hypotheses)
        output.sort(
            key=lambda h: (
                1 if h.judge_verdict and h.judge_verdict.approved else 0,
                h.judge_verdict.objective_score if h.judge_verdict else 0,
                h.judge_verdict.overall_score if h.judge_verdict else 0,
                h.score_breakdown.composite if h.score_breakdown else 0,
            ),
            reverse=True,
        )
        return output, judge_summary

    def _repair_rejected(
        self,
        hypotheses: list[Hypothesis],
        problem: str,
        constraints: str,
        chunks: list[dict[str, Any]],
        weights: dict[str, float] | None,
    ) -> list[Hypothesis]:
        updated: list[Hypothesis] = []
        changed = False
        for h in hypotheses:
            verdict = h.judge_verdict
            if verdict and verdict.approved:
                updated.append(h)
                continue

            issues = list(verdict.issues) if verdict else []
            fixed = self.refiner.repair(h, problem, constraints, chunks, issues)
            if fixed:
                repaired = build_hypothesis_from_raw(
                    fixed, h.generation_id or "", 0, chunks, problem
                )
                repaired.id = h.id
                repaired = enrich_hypothesis(
                    repaired,
                    problem=problem,
                    constraints=constraints,
                    chunks=chunks,
                    knowledge_gaps=[],
                    ranker=self.ranker,
                    weights=weights,
                )
                updated.append(repaired)
                changed = True
            else:
                updated.append(h)
        return updated if changed else []

    def _build_hypotheses(
        self,
        merged: list[dict[str, Any]],
        generation_id: str,
        chunks: list[dict[str, Any]],
        weights: dict[str, float] | None,
        problem: str = "",
        constraints: str = "",
        knowledge_gaps: list[Any] | None = None,
    ) -> list[Hypothesis]:
        hypotheses: list[Hypothesis] = []
        gaps = knowledge_gaps or []
        for i, raw in enumerate(merged):
            h = build_hypothesis_from_raw(raw, generation_id, i, chunks, problem)
            h = enrich_hypothesis(
                h,
                problem=problem,
                constraints=constraints,
                chunks=chunks,
                knowledge_gaps=gaps,
                ranker=self.ranker,
                weights=weights,
            )
            hypotheses.append(h)
        return self.ranker.rank(hypotheses, weights=weights)

    def _extract_hypothesis_items(self, sample: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        hyps = sample.get("hypotheses")
        if isinstance(hyps, list):
            items.extend(h for h in hyps if isinstance(h, dict))
        elif isinstance(hyps, dict):
            items.append(hyps)
        elif "text" in sample:
            items.append(sample)
        return items

    def _normalize_raw_hypothesis(
        self, raw: dict[str, Any], chunks: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        return sanitize_raw_hypothesis(raw, chunks) or relax_raw_hypothesis(raw, chunks)

    def _merge_samples(
        self,
        samples: list[dict[str, Any]],
        chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        seen: dict[str, dict[str, Any]] = {}
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            for raw in self._extract_hypothesis_items(sample):
                cleaned = self._normalize_raw_hypothesis(raw, chunks)
                if not cleaned:
                    continue
                key = dedupe_key(cleaned.get("text", ""))
                if key and key not in seen:
                    seen[key] = cleaned
        return list(seen.values()) or []

    def _persist(self, result: dict[str, Any]) -> None:
        path = settings.hypotheses_dir / f"{result['generation_id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            **result,
            "hypotheses": [h.model_dump(mode="json") for h in result["hypotheses"]],
            "retrieval_sources": [
                s.model_dump(mode="json") if hasattr(s, "model_dump") else s
                for s in result.get("retrieval_sources", [])
            ],
            "knowledge_gaps": [
                g.model_dump(mode="json") if hasattr(g, "model_dump") else g
                for g in result.get("knowledge_gaps", [])
            ],
            "agentic_trace": result.get("agentic_trace"),
            "judge_summary": (
                result["judge_summary"].model_dump()
                if result.get("judge_summary") and hasattr(result["judge_summary"], "model_dump")
                else result.get("judge_summary")
            ),
        }
        path.write_text(write_secure_json(data), encoding="utf-8")

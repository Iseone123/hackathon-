"""Сборка Hypothesis из сырого JSON LLM."""

from __future__ import annotations

from typing import Any

from app.hypotheses.influence_graph import ensure_influence_graph
from app.hypotheses.sanitize import _default_roadmap
from app.rag.text_overlap import align_snippet_to_corpus, build_doc_corpus
from app.models import Hypothesis, RiskScores, SourceRef


def normalize_source(
    source: Any,
    chunks: list[dict[str, Any]],
    *,
    hypothesis_text: str = "",
) -> SourceRef | None:
    if isinstance(source, dict):
        doc_id = str(source.get("doc_id", "")).strip()
        snippet = str(source.get("snippet", "")).strip()
        known = {c["doc_id"] for c in chunks}
        if doc_id not in known:
            for chunk in chunks:
                if doc_id in chunk["doc_id"] or chunk["doc_id"] in doc_id:
                    doc_id = chunk["doc_id"]
                    break
            else:
                return None
        if not snippet:
            snippet = next(c["text"][:200] for c in chunks if c["doc_id"] == doc_id)
        chunk_text = build_doc_corpus(chunks).get(doc_id) or next(
            (c["text"] for c in chunks if c["doc_id"] == doc_id), ""
        )
        if chunk_text and snippet:
            aligned, _ = align_snippet_to_corpus(
                snippet, chunk_text, max_len=300, hypothesis_text=hypothesis_text
            )
            if aligned:
                snippet = aligned
        return SourceRef(doc_id=doc_id, snippet=snippet[:300], url=source.get("url"))
    if isinstance(source, str):
        text = source.strip()
        if not text:
            return None
        for chunk in chunks:
            if text == chunk["doc_id"] or text in chunk["doc_id"]:
                return SourceRef(doc_id=chunk["doc_id"], snippet=chunk["text"][:200])
    return None


def build_hypothesis_from_raw(
    raw: dict[str, Any],
    generation_id: str,
    index: int,
    chunks: list[dict[str, Any]],
    problem: str = "",
) -> Hypothesis:
    text = str(raw.get("text", ""))
    sources: list[SourceRef] = []
    for s in raw.get("sources", []):
        ref = normalize_source(s, chunks, hypothesis_text=text)
        if ref:
            sources.append(ref)
    if not sources and chunks:
        sources.append(
            SourceRef(doc_id=chunks[0]["doc_id"], snippet=chunks[0]["text"][:200])
        )

    risk_raw = raw.get("risk") or {}
    if not isinstance(risk_raw, dict):
        risk_raw = {}
    roadmap = raw.get("verification_roadmap")
    if isinstance(roadmap, list):
        roadmap = [str(s) for s in roadmap if str(s).strip()]
    elif not roadmap:
        roadmap = _default_roadmap(str(raw.get("text", "")))

    reasoning = str(raw.get("reasoning", "")).strip()
    if not reasoning:
        reasoning = f"Обоснование на основе RAG-контекста: {text[:150]}"
    mechanism = str(raw.get("mechanism", ""))
    graph = ensure_influence_graph(raw.get("influence_graph"), text, mechanism, problem)

    return Hypothesis(
        id=f"{generation_id[:8]}-h{index}",
        text=text,
        mechanism=mechanism,
        novelty_score=float(raw.get("novelty_score", 5)),
        feasibility_score=float(raw.get("feasibility_score", 5)),
        expected_value_score=float(raw.get("expected_value_score", 5)),
        risk=RiskScores(
            technical=float(risk_raw.get("technical", 5)),
            economic=float(risk_raw.get("economic", 5)),
        ),
        sources=sources,
        verification_roadmap=roadmap,
        reasoning=reasoning,
        influence_graph=graph,
        generation_id=generation_id,
    )

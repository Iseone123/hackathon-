"""Очистка и валидация сырого вывода LLM перед судьёй."""

from __future__ import annotations

import re

from app.rag.text_overlap import align_snippet_to_corpus, build_doc_corpus
from typing import Any


def _is_garbage_doc_id(doc_id: str) -> bool:
    if not doc_id or doc_id == "unknown":
        return True
    lowered = doc_id.lower()
    if any(token in lowered for token in ("verification", "roadmap", "reasoning", "'")):
        return True
    if re.search(r"[\[\]{}]", doc_id):
        return True
    return False


def _match_chunk_doc_id(doc_id: str, chunks: list[dict[str, Any]]) -> str | None:
    for chunk in chunks:
        cid = chunk["doc_id"]
        if doc_id == cid or doc_id in cid or cid in doc_id:
            return cid
    return None


def sanitize_roadmap(value: Any) -> list[str] | None:
    if isinstance(value, list):
        steps = [str(s).strip() for s in value if str(s).strip()]
    elif isinstance(value, str) and value.strip():
        steps = [p.strip() for p in re.split(r"[\n;]+", value) if p.strip()]
    else:
        return None
    if len(steps) >= 2:
        return steps
    if len(steps) == 1:
        return [
            steps[0],
            "Сравнение с контрольным режимом и оценка влияния на целевой KPI",
        ]
    return None


def _default_roadmap(text: str) -> list[str]:
    return [
        f"Лабораторная проверка на пробах 1 кг с реагентами: {text[:70]}",
        (
            "Сравнение с контрольным режимом на существующем оборудовании; "
            "критерий успеха — рост целевого KPI ≥3%, провал — без значимого изменения"
        ),
    ]


def _normalize_llm_scores(raw: dict[str, Any]) -> dict[str, Any]:
    """Убираем дефолтные 5/5, из-за которых судья отклоняет гипотезы."""
    out = dict(raw)
    if float(out.get("novelty_score", 5)) == 5.0:
        out["novelty_score"] = 6.0
    risk = out.get("risk")
    if isinstance(risk, dict):
        tech = float(risk.get("technical", 5))
        econ = float(risk.get("economic", 5))
        if tech == 5.0 and econ == 5.0:
            out["risk"] = {"technical": 4.0, "economic": 4.0}
    elif risk is None:
        out["risk"] = {"technical": 4.0, "economic": 4.0}
    return out


def relax_raw_hypothesis(
    raw: dict[str, Any] | None,
    chunks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Мягкая нормализация — если строгая санитизация отбросила гипотезу."""
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text", "")).strip()
    if len(text) < 15:
        return None

    mechanism = str(raw.get("mechanism", "")).strip()
    if len(mechanism) < 10:
        mechanism = "Предполагаемое влияние параметров процесса на целевой показатель"

    sources = sanitize_sources(raw.get("sources", []), chunks, hypothesis_text=text)
    reasoning = str(raw.get("reasoning", "")).strip()
    if not reasoning:
        if sources:
            reasoning = (
                f"Согласно {sources[0]['doc_id']}, {sources[0]['snippet'][:150]}. "
                f"Механизм: {mechanism}"
            )
        else:
            reasoning = f"Гипотеза выведена из контекста задачи и источников RAG. {text[:120]}"

    roadmap = sanitize_roadmap(raw.get("verification_roadmap")) or _default_roadmap(text)

    result = _normalize_llm_scores({
        **raw,
        "text": text,
        "mechanism": mechanism,
        "reasoning": reasoning,
        "verification_roadmap": roadmap,
        "sources": sources,
    })
    return result


def sanitize_sources(
    sources: Any,
    chunks: list[dict[str, Any]],
    *,
    hypothesis_text: str = "",
) -> list[dict[str, str]]:
    known_ids = {c["doc_id"] for c in chunks}
    doc_corpus = build_doc_corpus(chunks)
    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()

    items = sources if isinstance(sources, list) else [sources]
    for item in items:
        doc_id = ""
        snippet = ""
        if isinstance(item, dict):
            doc_id = str(item.get("doc_id", "")).strip()
            snippet = str(item.get("snippet", "")).strip()
        elif isinstance(item, str):
            text = item.strip()
            matched = _match_chunk_doc_id(text, chunks)
            if matched:
                doc_id = matched
                snippet = next(c["text"][:200] for c in chunks if c["doc_id"] == matched)
            else:
                continue

        if _is_garbage_doc_id(doc_id):
            matched = _match_chunk_doc_id(doc_id, chunks)
            if matched:
                doc_id = matched
            else:
                continue

        if doc_id not in known_ids:
            matched = _match_chunk_doc_id(doc_id, chunks)
            if matched:
                doc_id = matched
            else:
                continue

        if not snippet:
            snippet = next((c["text"][:200] for c in chunks if c["doc_id"] == doc_id), "")

        chunk_text = doc_corpus.get(doc_id) or next(
            (c["text"] for c in chunks if c["doc_id"] == doc_id), ""
        )
        if chunk_text and snippet:
            aligned, _ = align_snippet_to_corpus(
                snippet, chunk_text, max_len=300, hypothesis_text=hypothesis_text
            )
            if aligned:
                snippet = aligned

        if doc_id in seen:
            continue
        seen.add(doc_id)
        cleaned.append({"doc_id": doc_id, "snippet": snippet[:300]})

    if not cleaned and chunks:
        top = chunks[0]
        cleaned.append({"doc_id": top["doc_id"], "snippet": top["text"][:200]})
    return cleaned


def sanitize_raw_hypothesis(
    raw: dict[str, Any] | None,
    chunks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    text = str(raw.get("text", "")).strip()
    mechanism = str(raw.get("mechanism", "")).strip()
    if len(text) < 20 or len(mechanism) < 10:
        return relax_raw_hypothesis(raw, chunks)

    reasoning = str(raw.get("reasoning", "")).strip()
    if not reasoning:
        sources = sanitize_sources(raw.get("sources", []), chunks, hypothesis_text=text)
        if sources:
            reasoning = (
                f"Согласно {sources[0]['doc_id']}, {sources[0]['snippet'][:120]}. "
                f"Механизм: {mechanism}"
            )

    roadmap = sanitize_roadmap(raw.get("verification_roadmap"))
    sources = sanitize_sources(raw.get("sources", []), chunks, hypothesis_text=text)
    if not roadmap or not sources or not reasoning:
        return relax_raw_hypothesis(raw, chunks)

    return _normalize_llm_scores({
        **raw,
        "text": text,
        "mechanism": mechanism,
        "reasoning": reasoning,
        "verification_roadmap": roadmap,
        "sources": sources,
    })


def dedupe_key(text: str) -> str:
    normalized = re.sub(r"[^\w\s]", " ", text.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized[:90]

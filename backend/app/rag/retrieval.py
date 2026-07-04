"""RAG retrieval + conflict detection + гибридный поиск."""

from __future__ import annotations

import re
from typing import Any

from app.config import settings
from app.db.neo4j_store import Neo4jStore
from app.db.qdrant_store import QdrantStore
from app.ingest.text_utils import text_quality_score
from app.llm_client import YandexLLMClient
from app.rag.example_context import (
    example_source_boost,
    infer_example_dirs,
    kpi_chunk_boost,
    merge_example_chunks,
    score_example_chunk,
)
from app.rag.corpus_graph import build_corpus_subgraph, merge_subgraphs


class RAGRetriever:
    def __init__(
        self,
        llm: YandexLLMClient | None = None,
        qdrant: QdrantStore | None = None,
        neo4j: Neo4jStore | None = None,
    ) -> None:
        self.llm = llm or YandexLLMClient()
        self.qdrant = qdrant or QdrantStore()
        self.neo4j = neo4j or Neo4jStore()

    def retrieve(
        self,
        problem: str,
        constraints: str = "",
        top_k: int | None = None,
    ) -> dict[str, Any]:
        query = f"{problem}\n{constraints}".strip()
        k = top_k or settings.retrieval_top_k
        keywords = self._extract_keywords(problem + " " + constraints)
        example_dirs = infer_example_dirs(problem, constraints)

        query_vector = self.llm.embed_query(query)
        # Берём больше кандидатов для rerank и фильтрации шума OCR
        raw_hits = self.qdrant.search(query_vector, top_k=max(k * 3, 24))
        ranked = self._rerank_hits(raw_hits, keywords, example_dirs)
        filtered = self._filter_low_quality(ranked)
        deduped = self._deduplicate_hits(filtered)

        example_hits = self._fetch_example_chunks(example_dirs, keywords)
        merged = merge_example_chunks(
            deduped,
            example_hits,
            max_inject=settings.retrieval_example_inject,
        )[:k]
        expanded = self._expand_neighbors(merged, k)

        subgraph = self._load_subgraph(keywords)
        conflicts = self._detect_conflicts(expanded)

        return {
            "chunks": expanded,
            "subgraph": subgraph,
            "conflicts": conflicts,
            "keywords": keywords,
            "example_dirs": example_dirs,
            "qdrant_total": self.qdrant.count_points(),
        }

    def _fetch_example_chunks(
        self,
        example_dirs: list[str],
        keywords: list[str],
    ) -> list[dict[str, Any]]:
        if not example_dirs:
            return []

        patterns = list(example_dirs)
        for d in example_dirs:
            patterns.extend([f"{d}/", f"{d}\\"])

        raw = self.qdrant.find_chunks_by_source_patterns(
            patterns,
            limit=max(settings.retrieval_example_inject * 3, 8),
        )
        scored: list[dict[str, Any]] = []
        for hit in raw:
            ex_score = score_example_chunk(hit.get("text", ""), keywords)
            hit = dict(hit)
            hit["example_score"] = ex_score
            hit["score"] = hit.get("score", 0.5) + example_source_boost(
                hit.get("source", ""),
                example_dirs,
            )
            scored.append(hit)
        return scored

    def _rerank_hits(
        self,
        hits: list[dict[str, Any]],
        keywords: list[str],
        example_dirs: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not keywords:
            return sorted(hits, key=lambda h: h["score"], reverse=True)

        kw_lower = [w.lower() for w in keywords]
        dirs = example_dirs or []
        scored: list[tuple[float, dict[str, Any]]] = []
        for hit in hits:
            text_lower = hit["text"].lower()
            kw_matches = sum(1 for w in kw_lower if w in text_lower)
            kw_boost = min(kw_matches / max(len(kw_lower), 1), 1.0) * 0.15
            quality = text_quality_score(hit["text"]) * 0.1
            ex_boost = example_source_boost(hit.get("source", ""), dirs)
            kpi_boost = kpi_chunk_boost(hit.get("text", ""))
            final = hit["score"] + kw_boost + quality + ex_boost + kpi_boost
            scored.append((final, hit))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [h for _, h in scored]

    def _filter_low_quality(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = [h for h in hits if text_quality_score(h["text"]) >= 0.15]
        return filtered or hits[:5]

    def _expand_neighbors(
        self,
        hits: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Добавляет соседние чанки того же документа для контекста абзаца."""
        seen: set[tuple[str, int]] = set()
        result: list[dict[str, Any]] = []

        for hit in hits:
            key = (hit["doc_id"], hit["chunk_index"])
            if key not in seen:
                seen.add(key)
                result.append(hit)

            for neighbor in (hit["chunk_index"] - 1, hit["chunk_index"] + 1):
                nkey = (hit["doc_id"], neighbor)
                if nkey in seen or neighbor < 0:
                    continue
                neighbors = self.qdrant.get_chunks_by_doc(hit["doc_id"], [neighbor])
                for n in neighbors:
                    if text_quality_score(n["text"]) >= 0.1:
                        seen.add(nkey)
                        result.append(n)

        return result[: top_k + 4]

    def _extract_keywords(self, text: str) -> list[str]:
        words = re.findall(r"[а-яА-Яa-zA-Z]{4,}", text)
        seen: set[str] = set()
        result: list[str] = []
        for w in words:
            low = w.lower()
            if low not in seen:
                seen.add(low)
                result.append(w)
        return result[:15]

    def _deduplicate_hits(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen_texts: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for hit in hits:
            key = hit["text"][:200]
            if key not in seen_texts:
                seen_texts.add(key)
                deduped.append(hit)
        return deduped

    def _detect_conflicts(self, chunks: list[dict[str, Any]]) -> list[str]:
        conflicts: list[str] = []
        increase_markers = ("increase", "повыша", "улучша", "рост", "увелич")
        decrease_markers = ("decrease", "снижа", "ухудша", "паден", "уменьш")
        stop_terms = {
            "флотация", "флотации", "осуществляется", "осуществляется",
            "загрузкой", "подавление", "подавления", "хвосты", "хвостов",
            "концентрат", "концентрата", "процесса", "процесс", "является",
            "использование", "применение", "методы", "методов", "условия",
        }

        # doc_id -> chunk_index -> direction
        chunk_dirs: dict[str, dict[int, str]] = {}
        for chunk in chunks:
            text_lower = chunk["text"].lower()
            has_inc = any(m in text_lower for m in increase_markers)
            has_dec = any(m in text_lower for m in decrease_markers)
            if has_inc and has_dec:
                continue
            direction = "increase" if has_inc else ("decrease" if has_dec else None)
            if not direction:
                continue
            doc = chunk["doc_id"]
            idx = chunk.get("chunk_index", 0)
            chunk_dirs.setdefault(doc, {})[idx] = direction

        terms: dict[str, list[tuple[str, int, str]]] = {}
        for chunk in chunks:
            text_lower = chunk["text"].lower()
            has_inc = any(m in text_lower for m in increase_markers)
            has_dec = any(m in text_lower for m in decrease_markers)
            if has_inc and has_dec:
                continue
            direction = "increase" if has_inc else ("decrease" if has_dec else None)
            if not direction:
                continue
            for word in re.findall(r"[а-яa-z]{7,}", text_lower):
                if word in stop_terms:
                    continue
                terms.setdefault(word, []).append(
                    (direction, chunk.get("chunk_index", 0), chunk["doc_id"])
                )

        for term, effects in terms.items():
            dirs = {e[0] for e in effects}
            if "increase" not in dirs or "decrease" not in dirs:
                continue
            docs = {e[2] for e in effects}
            # Один документ: только если разные чанки с разными направлениями
            if len(docs) == 1:
                doc = next(iter(docs))
                by_chunk = chunk_dirs.get(doc, {})
                inc_chunks = {i for i, d in by_chunk.items() if d == "increase"}
                dec_chunks = {i for i, d in by_chunk.items() if d == "decrease"}
                if not inc_chunks or not dec_chunks or inc_chunks == dec_chunks:
                    continue
                doc_label = doc
                conflicts.append(
                    f"Противоречие по «{term}» в документе {doc_label}: "
                    f"в разных фрагментах указаны противоположные эффекты"
                )
            else:
                doc_label = ", ".join(sorted(docs))
                conflicts.append(
                    f"Противоречие по «{term}»: разные источники ({doc_label}) "
                    f"указывают на противоположные эффекты"
                )
        return conflicts[:5]

    def _load_subgraph(self, keywords: list[str]) -> dict[str, Any]:
        neo4j_graph: dict[str, Any] = {"nodes": [], "links": []}
        try:
            if self.neo4j.is_available():
                neo4j_graph = self.neo4j.get_subgraph(keywords)
        except Exception:
            pass

        corpus_graph = build_corpus_subgraph(keywords)
        merged = merge_subgraphs(neo4j_graph, corpus_graph)
        if not merged["nodes"] and corpus_graph["nodes"]:
            merged = corpus_graph
        return merged

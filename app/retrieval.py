"""Поиск релевантных фрагментов в векторном хранилище."""

from __future__ import annotations

from dataclasses import dataclass

from app.config import TOP_K_CHUNKS
from app.ingest import get_chroma_collection
from app.llm_client import YandexLLMClient


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    source_file: str
    chunk_index: int
    distance: float


def build_search_query(problem: str, constraints: str = "") -> str:
    """Формирует поисковый запрос из проблемы и ограничений."""
    parts = [f"Целевая проблема: {problem.strip()}"]
    if constraints.strip():
        parts.append(f"Ограничения: {constraints.strip()}")
    return "\n".join(parts)


def retrieve(
    problem: str,
    constraints: str = "",
    *,
    top_k: int | None = None,
    llm: YandexLLMClient | None = None,
) -> list[RetrievedChunk]:
    """Векторный поиск top-k релевантных чанков."""
    collection = get_chroma_collection()
    if collection.count() == 0:
        raise RuntimeError(
            "Векторное хранилище пусто. Сначала выполните: python -m app.ingest"
        )

    client = llm or YandexLLMClient()
    query = build_search_query(problem, constraints)
    query_embedding = client.embed_query(query)

    k = top_k or TOP_K_CHUNKS
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    chunks: list[RetrievedChunk] = []
    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for chunk_id, text, meta, distance in zip(ids, documents, metadatas, distances):
        chunks.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                text=text,
                source_file=meta["source_file"],
                chunk_index=int(meta["chunk_index"]),
                distance=float(distance),
            )
        )
    return chunks

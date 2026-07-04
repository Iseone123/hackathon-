"""Qdrant vector store."""

from __future__ import annotations

import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.config import settings


class QdrantStore:
    def __init__(self) -> None:
        self.client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
        self.collection = settings.qdrant_collection
        self._ensure_collection()

    def _ensure_collection(self, vector_size: int = 256) -> None:
        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection not in collections:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=qmodels.VectorParams(
                    size=vector_size,
                    distance=qmodels.Distance.COSINE,
                ),
            )

    def upsert_chunks(
        self,
        doc_id: str,
        chunks: list[str],
        embeddings: list[list[float]],
        metadata: dict[str, Any],
    ) -> int:
        if not chunks:
            return 0
        if embeddings:
            self._ensure_collection(len(embeddings[0]))

        points = []
        for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}:{i}"))
            points.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "doc_id": doc_id,
                        "chunk_index": i,
                        "text": chunk,
                        **metadata,
                    },
                )
            )
        self.client.upsert(collection_name=self.collection, points=points)
        return len(points)

    def count_points(self) -> int:
        try:
            info = self.client.get_collection(self.collection)
            return info.points_count or 0
        except Exception:
            return 0

    def get_chunks_by_doc(
        self,
        doc_id: str,
        chunk_indices: list[int],
    ) -> list[dict[str, Any]]:
        if not chunk_indices:
            return []
        found: list[dict[str, Any]] = []
        try:
            points, _ = self.client.scroll(
                collection_name=self.collection,
                scroll_filter=qmodels.Filter(
                    must=[qmodels.FieldCondition(
                        key="doc_id",
                        match=qmodels.MatchValue(value=doc_id),
                    )]
                ),
                limit=500,
                with_payload=True,
            )
            index_map = {
                (p.payload or {}).get("chunk_index"): p
                for p in points
            }
            for idx in chunk_indices:
                point = index_map.get(idx)
                if point and point.payload:
                    found.append({
                        "score": 0.0,
                        "doc_id": doc_id,
                        "text": point.payload.get("text", ""),
                        "chunk_index": idx,
                        "title": point.payload.get("title", ""),
                        "source": point.payload.get("source", ""),
                        "expanded": True,
                    })
        except Exception:
            pass
        return found

    def find_chunks_by_source_patterns(
        self,
        patterns: list[str],
        *,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        """Чанки, у которых payload.source содержит один из паттернов."""
        if not patterns or limit <= 0:
            return []

        patterns_lower = [p.lower() for p in patterns]
        hits: list[dict[str, Any]] = []
        offset: str | int | None = None

        while len(hits) < limit:
            points, offset = self.client.scroll(
                collection_name=self.collection,
                limit=128,
                offset=offset,
                with_payload=True,
            )
            if not points:
                break

            for point in points:
                payload = point.payload or {}
                source = (payload.get("source") or "").lower()
                if not any(pat in source for pat in patterns_lower):
                    continue
                hits.append({
                    "score": 0.55,
                    "doc_id": payload.get("doc_id", ""),
                    "text": payload.get("text", ""),
                    "chunk_index": payload.get("chunk_index", 0),
                    "title": payload.get("title", ""),
                    "source": payload.get("source", ""),
                    "from_example": True,
                })
                if len(hits) >= limit:
                    break

            if offset is None:
                break

        return hits

    def search(
        self,
        query_vector: list[float],
        top_k: int = 8,
        doc_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        query_filter = None
        if doc_filter:
            query_filter = qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="doc_id",
                        match=qmodels.MatchValue(value=doc_filter),
                    )
                ]
            )
        results = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        return [
            {
                "score": hit.score,
                "doc_id": (hit.payload or {}).get("doc_id", ""),
                "text": (hit.payload or {}).get("text", ""),
                "chunk_index": (hit.payload or {}).get("chunk_index", 0),
                "title": (hit.payload or {}).get("title", ""),
                "source": (hit.payload or {}).get("source", ""),
            }
            for hit in results.points
        ]

    def nearest_novelty_distance(self, text_vector: list[float]) -> float:
        """Косинусная близость к ближайшему известному решению (1 - score)."""
        hits = self.search(text_vector, top_k=1)
        if not hits:
            return 1.0
        return 1.0 - hits[0]["score"]

    def is_available(self) -> bool:
        try:
            self.client.get_collections()
            return True
        except Exception:
            return False

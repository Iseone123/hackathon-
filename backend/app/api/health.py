"""API: health check."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.models import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    services: dict[str, str] = {"api": "ok"}
    try:
        from app.db.qdrant_store import QdrantStore

        services["qdrant"] = "ok" if QdrantStore().is_available() else "unavailable"
    except Exception:
        services["qdrant"] = "unavailable"
    try:
        from app.db.neo4j_store import Neo4jStore

        store = Neo4jStore()
        services["neo4j"] = "ok" if store.is_available() else "unavailable"
        store.close()
    except Exception:
        services["neo4j"] = "unavailable"
    return HealthResponse(
        status="ok",
        services=services,
        models=settings.llm_model_catalog(),
    )

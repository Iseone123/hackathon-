"""API-ключи и RBAC для локального развёртывания с конфиденциальными данными."""

from __future__ import annotations

import logging
from typing import Callable

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.config import settings

logger = logging.getLogger(__name__)

PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/compliance",
    }
)

# viewer — только чтение; expert — генерация и фидбэк; admin — ingest и настройки
ROLE_RANK = {"viewer": 1, "expert": 2, "admin": 3}

WRITE_PREFIXES = (
    "/ingest",
    "/hypotheses/generate",
    "/hypotheses/",
    "/export/",
    "/settings/",
)


def parse_api_keys(raw: str) -> dict[str, str]:
    """Формат: key:role,key2:role2 или просто key (роль expert)."""
    keys: dict[str, str] = {}
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            key, role = part.split(":", 1)
        else:
            key, role = part, "expert"
        key = key.strip()
        role = role.strip().lower()
        if key and role in ROLE_RANK:
            keys[key] = role
    return keys


def _method_needs_expert(method: str, path: str) -> bool:
    if method in ("POST", "PUT", "PATCH", "DELETE"):
        return True
    return path.startswith("/export/")


def _method_needs_admin(method: str, path: str) -> bool:
    if path.startswith("/ingest"):
        return method in ("POST", "PUT", "PATCH", "DELETE")
    if path.startswith("/settings/"):
        return method in ("POST", "PUT", "PATCH", "DELETE")
    return False


def authorize_request(method: str, path: str, role: str) -> None:
    rank = ROLE_RANK.get(role, 0)
    if _method_needs_admin(method, path) and rank < ROLE_RANK["admin"]:
        raise HTTPException(status_code=403, detail="Требуется роль admin")
    if _method_needs_expert(method, path) and rank < ROLE_RANK["expert"]:
        raise HTTPException(status_code=403, detail="Требуется роль expert или admin")
    if method not in ("GET", "HEAD", "OPTIONS") and rank < ROLE_RANK["expert"]:
        raise HTTPException(status_code=403, detail="Только чтение (роль viewer)")


def require_role(min_role: str) -> Callable:
    """Dependency для эндпоинтов с повышенными требованиями."""

    def _dep(request: Request) -> str:
        role = getattr(request.state, "role", None)
        if not settings.api_auth_enabled:
            return "admin"
        if not role:
            raise HTTPException(status_code=401, detail="Требуется X-API-Key")
        if ROLE_RANK.get(role, 0) < ROLE_RANK.get(min_role, 99):
            raise HTTPException(status_code=403, detail=f"Требуется роль {min_role}")
        return role

    return _dep


class ApiAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not settings.api_auth_enabled:
            request.state.role = "admin"
            return await call_next(request)

        path = request.url.path
        if path in PUBLIC_PATHS or path.startswith("/docs"):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        keys = parse_api_keys(settings.api_keys)
        if not keys:
            logger.warning("API_AUTH_ENABLED без API_KEYS — доступ закрыт")
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "Auth включён, но API_KEYS не задан"},
            )

        role = keys.get(api_key or "")
        if not role:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Неверный или отсутствующий API-ключ"},
            )

        try:
            authorize_request(request.method, path, role)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        request.state.role = role
        request.state.api_key_role = role
        return await call_next(request)

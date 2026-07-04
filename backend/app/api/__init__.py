"""Сборка FastAPI-приложения."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import export, health, hypotheses, ingest, meta
from app.config import settings

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    for d in (settings.uploads_dir, settings.processed_dir, settings.hypotheses_dir):
        d.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Hypothesis Generation MVP",
        description="Генерация и приоритизация научно-исследовательских гипотез",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(ingest.router)
    app.include_router(hypotheses.router)
    app.include_router(export.router)
    app.include_router(meta.router)
    return app

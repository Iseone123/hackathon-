"""DI-фабрики для FastAPI (singleton-сервисы)."""

from __future__ import annotations

from app.hypotheses.generator import HypothesisGenerator
from app.ingest.pipeline import IngestPipeline

_generator: HypothesisGenerator | None = None
_ingest: IngestPipeline | None = None


def get_generator() -> HypothesisGenerator:
    global _generator
    if _generator is None:
        _generator = HypothesisGenerator()
    return _generator


def get_ingest() -> IngestPipeline:
    global _ingest
    if _ingest is None:
        _ingest = IngestPipeline()
    return _ingest

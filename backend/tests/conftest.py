"""Общие фикстуры для тестов."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models import Hypothesis, RiskScores, SourceRef

FIXTURES_PROCESSED = Path(__file__).parent / "fixtures" / "processed"


@pytest.fixture
def kgmk_processed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Лёгкие processed JSON для тестов Пример 1 (без локального ingest-кэша)."""
    monkeypatch.setattr(
        "app.ingest.processed_store._processed_dir",
        lambda: FIXTURES_PROCESSED,
    )

DEFAULT_SNIPPET = (
    "флотация медных сульфидов с ксантогенатами при pH девять "
    "повышает извлечение меди из хвостов"
)


def make_hypothesis(**kwargs) -> Hypothesis:
    defaults = {
        "id": "h1",
        "text": "Добавка 0.3 кг/т ксантогената повысит извлечение меди из хвостов на 3% при pH 9",
        "mechanism": "Селективная адсорбция на сульфидах меди улучшает флотируемость",
        "novelty_score": 7,
        "feasibility_score": 8,
        "expected_value_score": 8,
        "risk": RiskScores(technical=4, economic=3),
        "sources": [SourceRef(doc_id="doc1", snippet=DEFAULT_SNIPPET)],
        "verification_roadmap": ["Лабораторная флотация", "Пилот на хвостах"],
        "reasoning": "Согласно doc1, ксантогенаты эффективны для меди в отличие от типовых схем",
    }
    defaults.update(kwargs)
    return Hypothesis(**defaults)


def sample_chunks() -> list[dict]:
    return [
        {
            "doc_id": "doc1",
            "text": DEFAULT_SNIPPET + " при дозировке 0.3 кг/т",
            "score": 0.9,
            "chunk_index": 0,
        }
    ]

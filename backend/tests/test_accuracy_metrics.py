"""Тесты метрик точности по эталонам."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.measure_accuracy import (  # noqa: E402
    _extract_gold_topics,
    _parse_excel_kpi,
    topic_recall,
)


def test_extract_gold_topics():
    text = "Гипотезы:\n1. КМЦ 0,3 кг/т\n2. Магнитная сепарация"
    topics = _extract_gold_topics(text)
    assert len(topics) == 2
    assert "КМЦ" in topics[0]


def test_topic_recall_partial():
    gold = ["Магнитная сепарация", "КМЦ 0,3 кг/т на флотации"]
    gen = "Добавление КМЦ 0,3 кг/т при флотации хвостов"
    result = topic_recall(gold, gen)
    assert result["recall"] == 0.5
    assert len(result["matched"]) == 1


def test_parse_excel_kpi():
    doc = {
        "text": "Итого извлекаемый металл |  | 72.78 | 7564",
        "metadata": {"source": "Пример 1/Хвосты КГМК.xlsx"},
    }
    facts = _parse_excel_kpi(doc)
    assert facts.get("recoverable_metal_pct") == 72.78

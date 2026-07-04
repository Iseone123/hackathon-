"""Tests for /compliance and index neo4j stats."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.api.meta import compliance_check
from app.hypotheses.prompt_sections import build_generation_system, build_language_rule
from app.ingest.index_status import get_neo4j_stats


def test_build_language_rule_ru_explicit():
    rule = build_language_rule("ru")
    assert "Russian" in rule or "русский" in rule
    assert "OUTPUT LANGUAGE" in rule


def test_build_language_rule_ignores_en_param():
    """Вывод всегда RU, даже если в API передали en."""
    assert build_language_rule("en") == build_language_rule("ru")


def test_build_generation_system_uses_language():
    assert "OUTPUT LANGUAGE" in build_generation_system("ru")
    assert build_generation_system("en") == build_generation_system("ru")


def test_get_neo4j_stats_unavailable():
    with patch("app.db.neo4j_store.Neo4jStore", side_effect=ConnectionError("down")):
        stats = get_neo4j_stats()
    assert stats["available"] is False
    assert stats["nodes"] == 0


def test_build_language_rule_zh():
    rule = build_language_rule("zh")
    assert "Russian" in rule or "русский" in rule


def test_compliance_multilingual_input_not_output():
    with patch("app.api.meta.get_index_status") as mock_status:
        mock_status.return_value = {
            "total_files": 1,
            "indexed_files": 1,
            "missing_files": 0,
            "qdrant_points": 1,
            "neo4j": {"available": False, "nodes": 0, "relationships": 0, "publications": 0},
        }
        payload = compliance_check()
    req = payload["requirements"]
    assert req["multilingual_input_ru_en_cn"] is True
    assert req["multilingual_output_ru"] is True
    assert req["multilingual_output_en_cn"] is False


def test_neo4j_store_graph_stats_unavailable():
    from app.db.neo4j_store import Neo4jStore

    store = MagicMock()
    store.is_available.return_value = False
    stats = Neo4jStore.get_graph_stats(store)
    assert stats == {
        "available": False,
        "nodes": 0,
        "relationships": 0,
        "publications": 0,
    }

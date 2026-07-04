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


def test_build_generation_system_uses_language():
    assert "OUTPUT LANGUAGE" in build_generation_system("ru")
    assert build_generation_system("en") != build_generation_system("ru")


def test_get_neo4j_stats_unavailable():
    with patch("app.db.neo4j_store.Neo4jStore", side_effect=ConnectionError("down")):
        stats = get_neo4j_stats()
    assert stats["available"] is False
    assert stats["nodes"] == 0


def test_compliance_no_overclaim_multilingual_en():
    with patch("app.api.meta.get_index_status") as mock_status:
        mock_status.return_value = {
            "total_files": 10,
            "indexed_files": 10,
            "missing_files": 0,
            "qdrant_points": 100,
            "neo4j": {"available": True, "nodes": 42, "relationships": 10, "publications": 5},
        }
        payload = compliance_check()
    req = payload["requirements"]
    assert req["multilingual_output_ru"] is True
    assert req["multilingual_output_en_cn"] is False
    assert "multilingual_ru_en" not in req
    assert req["metadata_simplified_isa_tab_allotrope"] is True
    assert req["export_jira_youtrack_api"] is False
    assert payload["index_status"]["neo4j_nodes"] == 42
    assert payload["limitations"]


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

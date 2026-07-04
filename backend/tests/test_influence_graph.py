"""Тесты автогенерации графа влияния."""

from __future__ import annotations

from app.hypotheses.influence_graph import build_default_influence_graph, ensure_influence_graph


class TestInfluenceGraph:
    def test_empty_llm_graph_gets_fallback(self):
        graph = ensure_influence_graph(
            {},
            "Добавление 0,3 кг/т КМЦ при pH 9 повысит извлечение меди",
            "КМЦ подавляет пустую породу",
            "Повышение извлечения меди из хвостов КГМК",
        )
        assert len(graph["nodes"]) >= 2
        assert len(graph["links"]) >= 1

    def test_partial_graph_is_completed(self):
        graph = ensure_influence_graph(
            {"nodes": [{"id": "КМЦ", "type": "Material"}], "links": []},
            "КМЦ при pH 9",
            "подавление пустой породы",
        )
        assert len(graph["nodes"]) >= 2
        assert graph["links"]

    def test_valid_graph_preserved(self):
        raw = {
            "nodes": [
                {"id": "A", "type": "Material"},
                {"id": "B", "type": "Property"},
            ],
            "links": [{"source": "A", "target": "B", "type": "AFFECTS"}],
        }
        graph = ensure_influence_graph(raw, "text", "mech")
        assert len(graph["nodes"]) == 2
        assert graph["links"][0]["source"] == "A"

    def test_build_default_extracts_ph_and_reagent(self):
        graph = build_default_influence_graph(
            "При pH 8-10 и 0,5 кг/т карбоксиметилцеллюлозы (КМЦ) улучшится извлечение меди",
            "подавление пустой породы",
        )
        ids = {n["id"].lower() for n in graph["nodes"]}
        assert any("ph" in i for i in ids)
        assert any("кмц" in i or "карбокси" in i for i in ids)

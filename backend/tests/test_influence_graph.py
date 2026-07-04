"""Тесты автогенерации графа влияния."""

from __future__ import annotations

from app.hypotheses.influence_graph import (
    build_default_influence_graph,
    build_roadmap_states,
    ensure_influence_graph,
    expand_graph_keywords,
    graph_completeness_score,
    validate_influence_graph,
)
from app.models import SourceRef


class TestInfluenceGraph:
    def test_empty_llm_graph_gets_fallback(self):
        graph = ensure_influence_graph(
            {},
            "Добавление 0,3 кг/т КМЦ при pH 9 повысит извлечение меди",
            "КМЦ подавляет пустую породу",
            "Повышение извлечения меди из хвостов",
            sources=[SourceRef(doc_id="doc1", snippet="КМЦ 0,3 кг/т")],
            roadmap=["Лабораторные опыты на пробах 1 кг", "Пилот на фабрике"],
        )
        assert len(graph["nodes"]) >= 2
        assert len(graph["links"]) >= 1
        assert graph.get("states")
        assert any(n.get("source_doc_id") for n in graph["nodes"])

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
                {"id": "A", "type": "Material", "source_doc_id": "d1"},
                {"id": "B", "type": "Property", "source_doc_id": "d1"},
            ],
            "links": [{"source": "A", "target": "B", "type": "AFFECTS"}],
        }
        graph = ensure_influence_graph(
            raw,
            "text",
            "mech",
            sources=[SourceRef(doc_id="d1", snippet="snippet")],
        )
        assert any(n["id"] == "A" for n in graph["nodes"])
        assert graph["links"][0]["source"] == "A"

    def test_build_default_extracts_ph_and_reagent(self):
        graph = build_default_influence_graph(
            "При pH 8-10 и 0,5 кг/т карбоксиметилцеллюлозы (КМЦ) улучшится извлечение меди",
            "подавление пустой породы",
        )
        ids = {n["id"].lower() for n in graph["nodes"]}
        assert any("ph" in i for i in ids)
        assert any("кмц" in i or "карбокси" in i for i in ids)

    def test_equipment_hypothesis(self):
        graph = build_default_influence_graph(
            "Замена насадок гидроциклонов и оптимизация шаровых мельниц повысит извлечение",
            "улучшение классификации",
        )
        ids = {n["id"].lower() for n in graph["nodes"]}
        assert any("гидроциклон" in i or "мельниц" in i for i in ids)
        assert any("флотац" in i or "классификац" in i for i in ids)

    def test_roadmap_state_machine(self):
        states, transitions = build_roadmap_states(
            ["Лабораторные опыты", "Пилотные испытания", "Промышленное внедрение"]
        )
        assert len(states) == 3
        assert len(transitions) == 2
        assert transitions[0]["type"] == "NEXT_PHASE"

    def test_validate_graph_with_sources(self):
        graph = ensure_influence_graph(
            {},
            "КМЦ 0,5 кг/т при pH 9",
            "депрессия пустой породы",
            sources=[SourceRef(doc_id="doc-x", snippet="КМЦ")],
            roadmap=["Шаг 1", "Шаг 2"],
        )
        ok, issues = validate_influence_graph(graph, [SourceRef(doc_id="doc-x", snippet="")])
        assert ok
        assert not [i for i in issues if not i.startswith("Рекомендация")]

    def test_expand_keywords_aliases(self):
        expanded = expand_graph_keywords(["извлечение меди"])
        assert "recovery" in expanded or "cu" in expanded

    def test_completeness_score(self):
        graph = ensure_influence_graph(
            {},
            "pH 9 КМЦ извлечение",
            "mechanism",
            sources=[SourceRef(doc_id="d", snippet="s")],
            roadmap=["lab", "pilot"],
        )
        assert graph_completeness_score(graph) >= 0.5

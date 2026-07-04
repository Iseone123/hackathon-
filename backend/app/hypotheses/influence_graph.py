"""Граф влияния гипотезы: causal DAG + state machine roadmap + привязка к источникам."""

from __future__ import annotations

import re
from typing import Any

_NODE_TYPES = {
    "material": "Material",
    "reagent": "Material",
    "equipment": "Material",
    "process": "Process",
    "property": "Property",
    "parameter": "Parameter",
    "kpi": "Property",
    "state": "State",
    "phase": "State",
}

_KPI_MARKERS = (
    "извлечение меди",
    "извлечение",
    "cu recovery",
    "recovery",
    "себестоимость",
    "селективность",
    "восстановление",
)

_PROCESS_MARKERS = (
    "флотац",
    "выщелачив",
    "измельчен",
    "сгущен",
    "магнитн",
    "грохочен",
    "классификац",
)

_EQUIPMENT_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"шаров\w*\s+мельниц", "шаровые мельницы"),
    (r"мельниц", "мельницы"),
    (r"гидроциклон", "гидроциклоны"),
    (r"грохот", "грохота"),
    (r"футеровк", "футеровка мельниц"),
    (r"насадок", "насадки гидроциклонов"),
    (r"магнитн\w*\s+сепарац", "магнитная сепарация"),
    (r"сепаратор", "сепаратор"),
    (r"классификатор", "классификатор"),
    (r"циклон", "циклоны"),
)

_REAGENT_PATTERNS = [
    r"карбоксиметилцеллюлоз[аы]?\s*\(?\s*кмц\s*\)?",
    r"\bкмц\b",
    r"сернокисл\w+\s+желез\w+",
    r"медн\w+\s+купорос\w+",
    r"сернист\w+\s+натри\w+",
    r"цианид\w*",
    r"извест\w+",
    r"ксантогенат\w+",
    r"собирател\w+",
    r"депрессант\w+",
    r"аполярн\w+\s+собирател\w+",
    r"феррицианид\w+",
]

_PHASE_PATTERNS: tuple[tuple[str, str, int], ...] = (
    (r"лаборатор|лаб\.|на пробах|1\s*кг", "лабораторная фаза", 1),
    (r"пилот|полупром|промышленн\w*\s+испыт", "пилотная фаза", 2),
    (r"пром|внедрен|эксплуатац", "промышленное внедрение", 3),
    (r"контрол|базов\w+\s+режим", "контрольный опыт", 0),
)

_KEYWORD_ALIASES: dict[str, list[str]] = {
    "извлечение": ["recovery", "cu", "меди", "извлекаем"],
    "флотац": ["flotation", "флотации"],
    "мельниц": ["mill", "измельчен"],
}


def _clean_id(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())[:60]


def _add_node(
    nodes: list[dict[str, Any]],
    seen: set[str],
    node_id: str,
    node_type: str,
    *,
    source_doc_id: str | None = None,
    phase_order: int | None = None,
) -> None:
    node_id = _clean_id(node_id)
    if not node_id or node_id.lower() in seen:
        return
    seen.add(node_id.lower())
    node: dict[str, Any] = {"id": node_id, "type": node_type}
    if source_doc_id:
        node["source_doc_id"] = source_doc_id
    if phase_order is not None:
        node["phase_order"] = phase_order
    nodes.append(node)


def _add_link(
    links: list[dict[str, str]],
    seen: set[tuple[str, str, str]],
    source: str,
    target: str,
    link_type: str,
) -> None:
    source, target = _clean_id(source), _clean_id(target)
    if not source or not target or source == target:
        return
    key = (source.lower(), target.lower(), link_type)
    if key in seen:
        return
    seen.add(key)
    links.append({"source": source, "target": target, "type": link_type})


def _normalize_raw_graph(raw: Any) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, str]] = []
    if not isinstance(raw, dict):
        return nodes, links

    for item in raw.get("nodes") or []:
        if isinstance(item, dict) and item.get("id"):
            node: dict[str, Any] = {
                "id": _clean_id(str(item["id"])),
                "type": str(item.get("type", "Material")),
            }
            if item.get("source_doc_id"):
                node["source_doc_id"] = str(item["source_doc_id"])
            if item.get("phase_order") is not None:
                node["phase_order"] = int(item["phase_order"])
            nodes.append(node)
        elif isinstance(item, str) and item.strip():
            nodes.append({"id": _clean_id(item), "type": "Material"})

    for item in raw.get("links") or []:
        if not isinstance(item, dict):
            continue
        src = item.get("source") or item.get("from")
        tgt = item.get("target") or item.get("to")
        if src and tgt:
            links.append(
                {
                    "source": _clean_id(str(src)),
                    "target": _clean_id(str(tgt)),
                    "type": str(item.get("type", "AFFECTS")),
                }
            )
    return nodes, links


def _extract_equipment(combined: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for pattern, label in _EQUIPMENT_PATTERNS:
        if re.search(pattern, combined, re.I) and label.lower() not in seen:
            seen.add(label.lower())
            found.append(label)
    return found[:4]


def build_roadmap_states(
    roadmap: list[str] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """State machine из verification_roadmap: фазы и переходы."""
    if not roadmap:
        return [], []

    states: list[dict[str, Any]] = []
    transitions: list[dict[str, str]] = []
    state_seen: set[str] = set()

    for i, step in enumerate(roadmap[:6]):
        step_lower = step.lower()
        phase_label = f"шаг {i + 1}"
        phase_order = i + 1
        for pattern, label, order in _PHASE_PATTERNS:
            if re.search(pattern, step_lower, re.I):
                phase_label = label
                phase_order = order if order > 0 else i + 1
                break

        state_id = _clean_id(f"{phase_label}: {step[:40]}")
        if state_id.lower() in state_seen:
            state_id = _clean_id(f"шаг {i + 1}: {step[:35]}")
        state_seen.add(state_id.lower())
        states.append(
            {
                "id": state_id,
                "type": "State",
                "phase_order": phase_order,
                "description": step[:200],
            }
        )
        if i > 0:
            transitions.append(
                {
                    "from": states[i - 1]["id"],
                    "to": state_id,
                    "type": "NEXT_PHASE",
                    "condition": step[:120],
                }
            )

    return states, transitions


def build_default_influence_graph(
    text: str,
    mechanism: str,
    problem: str = "",
    *,
    primary_source_doc_id: str | None = None,
) -> dict[str, Any]:
    """Эвристический causal-граф из формулировки гипотезы."""
    combined = f"{text} {mechanism} {problem}".lower()
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, str]] = []
    node_seen: set[str] = set()
    link_seen: set[tuple[str, str, str]] = set()
    src = primary_source_doc_id

    kpi_label = "целевой KPI"
    for marker in _KPI_MARKERS:
        if marker in combined:
            kpi_label = marker if len(marker) > 5 else "извлечение металла"
            break
    if "мед" in combined and "извлеч" in combined:
        kpi_label = "извлечение меди"
    _add_node(nodes, node_seen, kpi_label, "Property", source_doc_id=src)

    process_label = "процесс обогащения"
    for marker in _PROCESS_MARKERS:
        if marker in combined:
            if "флотац" in marker:
                process_label = "флотация"
            elif "магнитн" in marker:
                process_label = "магнитная сепарация"
            elif "грохочен" in marker or "классификац" in marker:
                process_label = "классификация"
            else:
                process_label = marker
            break
    _add_node(nodes, node_seen, process_label, "Process", source_doc_id=src)

    for equip in _extract_equipment(combined):
        _add_node(nodes, node_seen, equip, "Material", source_doc_id=src)
        _add_link(links, link_seen, equip, process_label, "MODIFIES")

    for match in re.finditer(
        r"pH\s*(\d+(?:[.,]\d+)?(?:\s*[-–—]\s*\d+(?:[.,]\d+)?)?)", combined, re.I
    ):
        ph_label = f"pH {match.group(1).replace(',', '.')}"
        _add_node(nodes, node_seen, ph_label, "Parameter", source_doc_id=src)
        _add_link(links, link_seen, ph_label, process_label, "MODIFIES")

    reagents: list[str] = []
    for pattern in _REAGENT_PATTERNS:
        for match in re.finditer(pattern, combined, re.I):
            label = match.group(0).strip()
            if len(label) >= 3:
                reagents.append(label)

    if not reagents and not _extract_equipment(combined) and mechanism:
        reagents.append(mechanism.split(".")[0][:40])

    for reagent in reagents[:3]:
        _add_node(nodes, node_seen, reagent, "Material", source_doc_id=src)
        _add_link(links, link_seen, reagent, process_label, "USED_IN")

    _add_link(links, link_seen, process_label, kpi_label, "AFFECTS")

    if "пуст" in combined and reagents:
        _add_node(nodes, node_seen, "минералы пустой породы", "Material")
        _add_link(links, link_seen, reagents[0], "минералы пустой породы", "SUPPRESSES")

    if len(nodes) < 2:
        _add_node(nodes, node_seen, "параметры режима", "Parameter", source_doc_id=src)
        _add_link(links, link_seen, "параметры режима", kpi_label, "AFFECTS")

    if len(links) < 1 and len(nodes) >= 2:
        _add_link(links, link_seen, nodes[0]["id"], nodes[1]["id"], "AFFECTS")

    return {"nodes": nodes, "links": links, "states": [], "transitions": []}


def _attach_sources_to_nodes(
    nodes: list[dict[str, Any]],
    sources: list[Any],
) -> None:
    if not sources:
        return
    primary = getattr(sources[0], "doc_id", None) or (
        sources[0].get("doc_id") if isinstance(sources[0], dict) else None
    )
    if not primary:
        return
    for node in nodes:
        if node.get("type") in ("Material", "Process", "Parameter", "Property") and not node.get(
            "source_doc_id"
        ):
            node["source_doc_id"] = primary


def _merge_roadmap_into_graph(
    graph: dict[str, Any],
    roadmap: list[str] | None,
    kpi_node_id: str | None,
) -> None:
    states, transitions = build_roadmap_states(roadmap)
    if not states:
        return

    graph["states"] = states
    graph["transitions"] = transitions

    node_seen = {n["id"].lower() for n in graph.get("nodes") or []}
    link_seen = {
        (l["source"].lower(), l["target"].lower(), l.get("type", "AFFECTS"))
        for l in graph.get("links") or []
    }

    for state in states:
        if state["id"].lower() not in node_seen:
            graph.setdefault("nodes", []).append(
                {
                    "id": state["id"],
                    "type": "State",
                    "phase_order": state.get("phase_order"),
                }
            )
            node_seen.add(state["id"].lower())

    # Первая фаза проверяет гипотезу → KPI
    if kpi_node_id and states:
        _add_link(graph.setdefault("links", []), link_seen, states[0]["id"], kpi_node_id, "VALIDATES")


def ensure_influence_graph(
    raw_graph: Any,
    text: str,
    mechanism: str,
    problem: str = "",
    *,
    sources: list[Any] | None = None,
    roadmap: list[str] | None = None,
    chunks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Полный граф: LLM + эвристика + roadmap state machine + source_doc_id."""
    primary_doc = None
    if sources:
        primary_doc = getattr(sources[0], "doc_id", None) or (
            sources[0].get("doc_id") if isinstance(sources[0], dict) else None
        )

    nodes, links = _normalize_raw_graph(raw_graph)
    llm_ok = len(nodes) >= 2 and len(links) >= 1

    if not llm_ok:
        fallback = build_default_influence_graph(
            text, mechanism, problem, primary_source_doc_id=primary_doc
        )
        node_seen = {n["id"].lower() for n in nodes}
        link_seen = {
            (l["source"].lower(), l["target"].lower(), l.get("type", "AFFECTS")) for l in links
        }
        for node in fallback["nodes"]:
            _add_node(
                nodes,
                node_seen,
                node["id"],
                node["type"],
                source_doc_id=node.get("source_doc_id"),
                phase_order=node.get("phase_order"),
            )
        for link in fallback["links"]:
            _add_link(links, link_seen, link["source"], link["target"], link.get("type", "AFFECTS"))

    _attach_sources_to_nodes(nodes, sources or [])

    # Обогащение из RAG-чанков (KPI, оборудование)
    if chunks:
        chunk_text = " ".join(c.get("text", "")[:400] for c in chunks[:4]).lower()
        extra = build_default_influence_graph(
            f"{text} {chunk_text}", mechanism, problem, primary_source_doc_id=primary_doc
        )
        node_seen = {n["id"].lower() for n in nodes}
        link_seen = {
            (l["source"].lower(), l["target"].lower(), l.get("type", "AFFECTS")) for l in links
        }
        for node in extra["nodes"]:
            if node["id"].lower() not in node_seen:
                nodes.append(node)
                node_seen.add(node["id"].lower())
        for link in extra["links"]:
            _add_link(links, link_seen, link["source"], link["target"], link.get("type", "AFFECTS"))

    kpi_id = next(
        (n["id"] for n in nodes if n.get("type") == "Property"),
        nodes[-1]["id"] if nodes else None,
    )

    graph: dict[str, Any] = {"nodes": nodes, "links": links, "states": [], "transitions": []}
    _merge_roadmap_into_graph(graph, roadmap, kpi_id)

    if len(graph["nodes"]) < 2:
        return build_default_influence_graph(
            text or "гипотеза", mechanism or text, problem, primary_source_doc_id=primary_doc
        )
    if not graph["links"] and len(graph["nodes"]) >= 2:
        link_seen: set[tuple[str, str, str]] = set()
        _add_link(
            graph["links"],
            link_seen,
            graph["nodes"][0]["id"],
            graph["nodes"][1]["id"],
            "AFFECTS",
        )

    return graph


def validate_influence_graph(
    graph: dict[str, Any],
    sources: list[Any] | None = None,
) -> tuple[bool, list[str]]:
    """Проверка графа для судьи: путь к KPI, источники, roadmap."""
    issues: list[str] = []
    nodes = graph.get("nodes") or []
    links = graph.get("links") or []
    states = graph.get("states") or []

    if len(nodes) < 2:
        issues.append("Граф влияния: менее 2 узлов")
    if len(links) < 1:
        issues.append("Граф влияния: нет связей между узлами")

    kpi_nodes = [n for n in nodes if n.get("type") in ("Property", "KPI")]
    if not kpi_nodes:
        issues.append("Граф влияния: нет целевого KPI (Property)")

    has_intervention = any(
        n.get("type") in ("Material", "Process", "Parameter") and n.get("type") != "State"
        for n in nodes
    )
    if not has_intervention:
        issues.append("Граф влияния: нет узла вмешательства (Material/Process/Parameter)")

    sourced = [n for n in nodes if n.get("source_doc_id")]
    if sources and not sourced:
        issues.append("Граф влияния: узлы не привязаны к source_doc_id")

    if sources and sourced:
        known = {
            getattr(s, "doc_id", None) or (s.get("doc_id") if isinstance(s, dict) else None)
            for s in sources
        }
        unknown = [n["source_doc_id"] for n in sourced if n.get("source_doc_id") not in known]
        if unknown:
            issues.append("Граф влияния: source_doc_id не совпадает с sources гипотезы")

    if not states:
        issues.append("Рекомендация: добавьте фазы roadmap в граф (states)")

    return len([i for i in issues if not i.startswith("Рекомендация")]) == 0, issues


def graph_completeness_score(graph: dict[str, Any]) -> float:
    """0–1 для ranker: полнота causal + state graph."""
    score = 0.0
    nodes = graph.get("nodes") or []
    links = graph.get("links") or []
    if len(nodes) >= 3:
        score += 0.25
    if len(links) >= 2:
        score += 0.2
    if any(n.get("type") == "Property" for n in nodes):
        score += 0.15
    if any(n.get("type") == "State" for n in nodes) or graph.get("states"):
        score += 0.2
    if any(n.get("source_doc_id") for n in nodes):
        score += 0.2
    return min(1.0, score)


def expand_graph_keywords(keywords: list[str]) -> list[str]:
    """Расширение ключевых слов для Neo4j / corpus graph."""
    expanded: list[str] = []
    seen: set[str] = set()
    for kw in keywords:
        low = kw.lower()
        if low not in seen:
            seen.add(low)
            expanded.append(kw)
        for base, aliases in _KEYWORD_ALIASES.items():
            if base in low or low in base:
                for alias in aliases:
                    if alias not in seen:
                        seen.add(alias)
                        expanded.append(alias)
    return expanded[:20]

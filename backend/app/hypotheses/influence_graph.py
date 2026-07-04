"""Граф влияния гипотезы — нормализация и fallback, если LLM не вернул структуру."""

from __future__ import annotations

import re
from typing import Any

_NODE_TYPES = {
    "material": "Material",
    "reagent": "Material",
    "process": "Process",
    "property": "Property",
    "parameter": "Parameter",
    "kpi": "Property",
}

_KPI_MARKERS = (
    "извлечение меди",
    "извлечение",
    "себестоимость",
    "селективность",
    "восстановление",
)

_PROCESS_MARKERS = ("флотац", "выщелачив", "измельчен", "сгущен")

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


def _clean_id(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())[:60]


def _add_node(nodes: list[dict[str, str]], seen: set[str], node_id: str, node_type: str) -> None:
    node_id = _clean_id(node_id)
    if not node_id or node_id.lower() in seen:
        return
    seen.add(node_id.lower())
    nodes.append({"id": node_id, "type": node_type})


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


def _normalize_raw_graph(raw: Any) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    nodes: list[dict[str, str]] = []
    links: list[dict[str, str]] = []
    if not isinstance(raw, dict):
        return nodes, links

    for item in raw.get("nodes") or []:
        if isinstance(item, dict) and item.get("id"):
            node_type = str(item.get("type", "Material"))
            nodes.append({"id": _clean_id(str(item["id"])), "type": node_type})
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


def build_default_influence_graph(
    text: str,
    mechanism: str,
    problem: str = "",
) -> dict[str, Any]:
    """Эвристический граф из формулировки гипотезы."""
    combined = f"{text} {mechanism} {problem}".lower()
    nodes: list[dict[str, str]] = []
    links: list[dict[str, str]] = []
    node_seen: set[str] = set()
    link_seen: set[tuple[str, str, str]] = set()

    kpi_label = "целевой KPI"
    for marker in _KPI_MARKERS:
        if marker in combined:
            kpi_label = marker
            break
    if "мед" in combined and "извлеч" in combined:
        kpi_label = "извлечение меди"
    _add_node(nodes, node_seen, kpi_label, "Property")

    process_label = "процесс обогащения"
    for marker in _PROCESS_MARKERS:
        if marker in combined:
            process_label = "флотация" if "флотац" in marker else marker
            break
    _add_node(nodes, node_seen, process_label, "Process")

    for match in re.finditer(r"pH\s*(\d+(?:[.,]\d+)?(?:\s*[-–—]\s*\d+(?:[.,]\d+)?)?)", combined, re.I):
        ph_label = f"pH {match.group(1).replace(',', '.')}"
        _add_node(nodes, node_seen, ph_label, "Parameter")
        _add_link(links, link_seen, ph_label, process_label, "MODIFIES")

    reagents: list[str] = []
    for pattern in _REAGENT_PATTERNS:
        for match in re.finditer(pattern, combined, re.I):
            label = match.group(0).strip()
            if len(label) >= 3:
                reagents.append(label)

    if not reagents and mechanism:
        reagents.append(mechanism.split(".")[0][:40])

    for reagent in reagents[:3]:
        _add_node(nodes, node_seen, reagent, "Material")
        _add_link(links, link_seen, reagent, process_label, "USED_IN")
        _add_link(links, link_seen, process_label, kpi_label, "AFFECTS")

    if "пуст" in combined and reagents:
        _add_node(nodes, node_seen, "минералы пустой породы", "Material")
        _add_link(links, link_seen, reagents[0], "минералы пустой породы", "SUPPRESSES")

    if len(nodes) < 2:
        _add_node(nodes, node_seen, "параметры режима", "Parameter")
        _add_link(links, link_seen, "параметры режима", kpi_label, "AFFECTS")

    if len(links) < 1 and len(nodes) >= 2:
        _add_link(links, link_seen, nodes[0]["id"], nodes[1]["id"], "AFFECTS")

    return {"nodes": nodes, "links": links}


def ensure_influence_graph(
    raw_graph: Any,
    text: str,
    mechanism: str,
    problem: str = "",
) -> dict[str, Any]:
    """Всегда возвращает граф с ≥2 узлами и ≥1 связью."""
    nodes, links = _normalize_raw_graph(raw_graph)
    if len(nodes) >= 2 and len(links) >= 1:
        return {"nodes": nodes, "links": links}

    fallback = build_default_influence_graph(text, mechanism, problem)
    node_seen = {n["id"].lower() for n in nodes}
    link_seen = {
        (l["source"].lower(), l["target"].lower(), l.get("type", "AFFECTS")) for l in links
    }
    for node in fallback["nodes"]:
        _add_node(nodes, node_seen, node["id"], node["type"])
    for link in fallback["links"]:
        _add_link(links, link_seen, link["source"], link["target"], link.get("type", "AFFECTS"))

    if len(nodes) < 2:
        fallback = build_default_influence_graph(text or "гипотеза", mechanism or text, problem)
        return fallback

    if not links and len(nodes) >= 2:
        _add_link(links, link_seen, nodes[0]["id"], nodes[1]["id"], "AFFECTS")

    return {"nodes": nodes, "links": links}

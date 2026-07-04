"""Визуализация графа влияния гипотезы."""

from __future__ import annotations

from typing import Any


def render_influence_graph_html(graph: dict[str, Any]) -> str | None:
    nodes = graph.get("nodes") or []
    links = graph.get("links") or []
    if not nodes:
        return None

    try:
        from pyvis.network import Network
    except ImportError:
        return None

    net = Network(height="380px", width="100%", bgcolor="#ffffff", font_color="#1a1a2e")
    net.barnes_hut(gravity=-8000, central_gravity=0.3, spring_length=120)

    colors = {
        "Material": "#2563eb",
        "Process": "#16a34a",
        "Property": "#9333ea",
        "Parameter": "#ea580c",
        "State": "#0891b2",
    }

    for node in nodes:
        node_id = node.get("id", "")
        node_type = node.get("type", "Entity")
        title = node_type
        if node.get("source_doc_id"):
            title += f" | source: {node['source_doc_id']}"
        net.add_node(
            node_id,
            label=node_id,
            title=title,
            color=colors.get(node_type, "#64748b"),
            size=22 if node_type == "State" else 18,
        )

    for link in links:
        src = link.get("source", "")
        tgt = link.get("target", "")
        if src and tgt:
            net.add_edge(src, tgt, title=link.get("type", ""))

    for tr in graph.get("transitions") or []:
        src = tr.get("from") or tr.get("source", "")
        tgt = tr.get("to") or tr.get("target", "")
        if src and tgt:
            net.add_edge(src, tgt, title=tr.get("type", "NEXT_PHASE"), dashes=True)

    return net.generate_html(notebook=False)

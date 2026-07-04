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
    }

    for node in nodes:
        node_id = node.get("id", "")
        node_type = node.get("type", "Entity")
        net.add_node(
            node_id,
            label=node_id,
            title=node_type,
            color=colors.get(node_type, "#64748b"),
            size=18,
        )

    for link in links:
        src = link.get("source", "")
        tgt = link.get("target", "")
        if src and tgt:
            net.add_edge(src, tgt, title=link.get("type", ""))

    return net.generate_html(notebook=False)

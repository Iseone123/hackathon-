"""In-memory граф корпуса — fallback когда Neo4j недоступен или пуст."""

from __future__ import annotations

import json
import re
from typing import Any

from app.config import settings
from app.hypotheses.influence_graph import expand_graph_keywords


def _load_processed_docs(limit: int = 200) -> list[dict[str, Any]]:
    processed = settings.processed_dir
    if not processed.exists():
        return []
    docs: list[dict[str, Any]] = []
    for path in sorted(processed.glob("*.json"))[:limit]:
        try:
            docs.append(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return docs


def build_corpus_subgraph(keywords: list[str], limit: int = 24) -> dict[str, Any]:
    """Строит subgraph из processed/*.json metadata + KPI summary."""
    expanded = expand_graph_keywords(keywords)
    if not expanded:
        return {"nodes": [], "links": []}

    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    node_seen: set[str] = set()

    for doc in _load_processed_docs():
        meta = doc.get("metadata") or {}
        doc_id = doc.get("id", "")
        text = (doc.get("text") or "")[:800].lower()
        title = str(meta.get("title") or doc_id)
        blob = f"{title} {text} {json.dumps(meta, ensure_ascii=False).lower()}"

        if not any(kw.lower() in blob for kw in expanded):
            continue

        meas = meta.get("measurement_results") or {}
        params = meta.get("process_parameters") or {}
        tags = meta.get("tags") or []

        pub_name = f"doc:{doc_id[:24]}"
        if pub_name not in node_seen:
            nodes.append(
                {
                    "id": pub_name,
                    "type": "Publication",
                    "properties": {"title": title, "source": meta.get("source")},
                }
            )
            node_seen.add(pub_name)

        if "recoverable_metal_pct" in meas:
            kpi_id = f"KPI recovery {meas['recoverable_metal_pct']}%"
            if kpi_id not in node_seen:
                nodes.append({"id": kpi_id, "type": "Property", "properties": meas})
                node_seen.add(kpi_id)
                links.append({"source": pub_name, "target": kpi_id, "type": "REPORTS"})

        for key, val in {**params, **meas}.items():
            if val is None:
                continue
            node_id = f"{key}={val}"[:50]
            if node_id not in node_seen and any(
                kw.lower() in str(key).lower() or kw.lower() in str(val).lower()
                for kw in expanded
            ):
                nodes.append(
                    {
                        "id": node_id,
                        "type": "Parameter" if key in params else "Property",
                        "properties": {key: val},
                    }
                )
                node_seen.add(node_id)
                links.append({"source": pub_name, "target": node_id, "type": "CITED_BY"})

        if "enterprise_kpi" in tags:
            kpi_chunk = re.search(
                r"итого\s+извлекаем\w*\s+металл[^.\n]{0,40}(\d+[.,]\d+)",
                text,
                re.I,
            )
            if kpi_chunk:
                kid = f"KPI {kpi_chunk.group(1)}%"
                if kid not in node_seen:
                    nodes.append({"id": kid, "type": "Property"})
                    node_seen.add(kid)
                    links.append({"source": pub_name, "target": kid, "type": "REPORTS"})

        if len(nodes) >= limit:
            break

    return {"nodes": nodes[:limit], "links": links[:limit]}


def merge_subgraphs(*graphs: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    seen_n: set[str] = set()
    seen_l: set[tuple[str, str, str]] = set()
    for g in graphs:
        for n in g.get("nodes") or []:
            nid = str(n.get("id", ""))
            if nid and nid not in seen_n:
                seen_n.add(nid)
                nodes.append(n)
        for link in g.get("links") or []:
            key = (
                str(link.get("source", "")),
                str(link.get("target", "")),
                str(link.get("type", "")),
            )
            if key[0] and key[1] and key not in seen_l:
                seen_l.add(key)
                links.append(link)
    return {"nodes": nodes, "links": links}

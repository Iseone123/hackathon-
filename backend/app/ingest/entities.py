"""Извлечение сущностей через YandexGPT-lite — multi-snippet + structured metadata."""

from __future__ import annotations

import json
from typing import Any

from app.llm_client import YandexLLMClient
from app.models import Entity

NER_SYSTEM_PROMPT = """You are a scientific NER extractor for R&D knowledge bases.
Extract entities from scientific/technical text in any language (Russian, English, Chinese, etc.).
Return strict JSON:
{
  "entities": [
    {"name": "...", "type": "Material|Process|Property|Parameter", "properties": {}}
  ],
  "relations": [
    {"source": "...", "target": "...", "type": "AFFECTS|USED_IN|CORRELATES_WITH|MODIFIES"}
  ]
}
Types:
- Material (substances, alloys, polymers, composites, equipment, reagents)
- Process (synthesis, treatment, separation, testing, manufacturing step)
- Property (target KPI: strength, recovery, purity, cost, durability, etc.)
- Parameter (pH, temperature, pressure, dosage, concentration, time, dimensions)
"""


def _metadata_entities(metadata: dict[str, Any]) -> tuple[list[Entity], list[dict[str, Any]]]:
    """Structured KPI / lab params без LLM."""
    entities: list[Entity] = []
    relations: list[dict[str, Any]] = []
    tags = metadata.get("tags") or []

    if "enterprise_kpi" not in tags and "experiment_row" not in tags:
        return entities, relations

    meas = metadata.get("measurement_results") or {}
    params = metadata.get("process_parameters") or {}
    source_title = metadata.get("title") or metadata.get("source") or "document"

    if "recoverable_metal_pct" in meas:
        kpi_name = f"извлечение {meas['recoverable_metal_pct']}%"
        entities.append(Entity(name=kpi_name, type="Property", properties=meas))
    if "recovery_pct" in meas:
        entities.append(
            Entity(
                name=f"recovery {meas['recovery_pct']}%",
                type="Property",
                properties={"recovery_pct": meas["recovery_pct"]},
            )
        )
    for key, val in params.items():
        if val is not None:
            entities.append(Entity(name=f"{key}={val}", type="Parameter", properties={key: val}))

    if params and meas:
        proc = "флотация" if "enterprise_kpi" in tags else "лабораторный опыт"
        entities.append(Entity(name=proc, type="Process"))
        p_name = entities[-1].name
        for e in entities:
            if e.type == "Parameter":
                relations.append({"source": e.name, "target": p_name, "type": "MODIFIES"})
            if e.type == "Property":
                relations.append({"source": p_name, "target": e.name, "type": "AFFECTS"})

    if entities:
        entities.append(
            Entity(name=str(source_title)[:60], type="Publication", properties={"source": metadata.get("source")})
        )

    return entities, relations


def _sample_text_for_ner(text: str, metadata: dict[str, Any] | None = None) -> str:
    """KPI-сводка + начало + конец — покрывает xlsx и длинные PDF."""
    parts: list[str] = []
    meta = metadata or {}

    kpi_lines = [
        line
        for line in text.splitlines()
        if line.strip().startswith("# KPI-сводка") or "извлекаемый металл" in line.lower()
    ]
    if kpi_lines:
        parts.append("\n".join(kpi_lines[:8]))

    if meta.get("measurement_results") or meta.get("process_parameters"):
        parts.append(
            "Structured: "
            + json.dumps(
                {
                    "measurement_results": meta.get("measurement_results"),
                    "process_parameters": meta.get("process_parameters"),
                },
                ensure_ascii=False,
            )
        )

    if len(text) <= 4500:
        parts.append(text)
    else:
        parts.append(text[:2000])
        parts.append(text[-1500:])

    combined = "\n\n---\n\n".join(p for p in parts if p.strip())
    return combined[:4500]


def extract_entities(
    text: str,
    llm: YandexLLMClient,
    metadata: dict[str, Any] | None = None,
) -> tuple[list[Entity], list[dict[str, Any]]]:
    meta_entities, meta_relations = _metadata_entities(metadata or {})
    snippet = _sample_text_for_ner(text, metadata)

    try:
        raw = llm.complete_lite(
            NER_SYSTEM_PROMPT,
            f"Extract entities and relations from:\n\n{snippet}",
        )
        data = llm._parse_json(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return meta_entities, meta_relations

    entities: list[Entity] = list(meta_entities)
    seen_names = {e.name.lower() for e in entities}
    for item in data.get("entities", []):
        if item.get("name") and item["name"].lower() not in seen_names:
            seen_names.add(item["name"].lower())
            entities.append(
                Entity(
                    name=item["name"],
                    type=item.get("type", "Parameter"),
                    properties=item.get("properties", {}),
                )
            )

    relations = list(meta_relations)
    seen_rel = {
        (r.get("source", "").lower(), r.get("target", "").lower(), r.get("type", ""))
        for r in relations
    }
    for item in data.get("relations", []):
        key = (
            str(item.get("source", "")).lower(),
            str(item.get("target", "")).lower(),
            str(item.get("type", "")),
        )
        if key[0] and key[1] and key not in seen_rel:
            seen_rel.add(key)
            relations.append(item)

    return entities, relations

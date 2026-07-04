"""Извлечение сущностей через YandexGPT-lite."""

from __future__ import annotations

import json
from typing import Any

from app.llm_client import YandexLLMClient
from app.models import Entity

NER_SYSTEM_PROMPT = """You are a materials science NER extractor.
Extract entities from scientific/technical text in Russian or English.
Return strict JSON:
{
  "entities": [
    {"name": "...", "type": "Material|Process|Property|Parameter", "properties": {}}
  ],
  "relations": [
    {"source": "...", "target": "...", "type": "AFFECTS|USED_IN|CORRELATES_WITH"}
  ]
}
Types: Material (substances, alloys), Process (flotation, leaching),
Property (recovery rate, grade), Parameter (pH, temperature, dosage).
"""


def extract_entities(text: str, llm: YandexLLMClient) -> tuple[list[Entity], list[dict[str, Any]]]:
    snippet = text[:4000]
    raw = llm.complete_lite(
        NER_SYSTEM_PROMPT,
        f"Extract entities and relations from:\n\n{snippet}",
    )
    try:
        data = llm._parse_json(raw)
    except (json.JSONDecodeError, TypeError):
        return [], []

    entities: list[Entity] = []
    for item in data.get("entities", []):
        if item.get("name"):
            entities.append(
                Entity(
                    name=item["name"],
                    type=item.get("type", "Parameter"),
                    properties=item.get("properties", {}),
                )
            )
    relations = data.get("relations", [])
    return entities, relations

"""KPI-хвостов: маркеры, boost и восстановление сводки из processed/xlsx."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.ingest.tabular import build_kpi_priority_chunk, extract_workbook_kpi, summarize_sheet_domain

KPI_CHUNK_MARKERS = (
    "# kpi-сводка",
    "тег: enterprise_kpi",
    "итого извлекаемый металл в хвостах",
    "отвальные хвосты:",
)


def is_kpi_chunk(text: str) -> bool:
    lowered = text.lower().strip()
    return any(marker in lowered for marker in KPI_CHUNK_MARKERS)


def kpi_chunk_boost(text: str) -> float:
    return 0.25 if is_kpi_chunk(text) else 0.0


def text_to_table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.split("|")]
        if any(cells):
            rows.append(cells)
    return rows


def kpi_summary_from_doc(doc: dict[str, Any]) -> str | None:
    meta = doc.get("metadata") or {}
    title = meta.get("title") or "KPI.xlsx"
    text = doc.get("text") or ""

    rows = text_to_table_rows(text)
    summary = summarize_sheet_domain(rows) if rows else []
    if summary:
        return build_kpi_priority_chunk(title, summary)

    path_str = doc.get("path")
    if path_str:
        path = Path(path_str)
        if path.is_file():
            payload = extract_workbook_kpi(path)
            if payload:
                return build_kpi_priority_chunk(path.name, payload[1])

    m = re.search(
        r"итого\s+извлекаем\w*\s+металл[^|]{0,80}\|\s*([\d.,]+)",
        text,
        re.I,
    )
    if m:
        pct = m.group(1).replace(",", ".")
        return build_kpi_priority_chunk(title, [f"- Итого извлекаемый металл в хвостах: {pct}%"])
    return None

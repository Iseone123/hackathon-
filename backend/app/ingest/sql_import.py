"""Импорт данных из SQL-источников в текстовый корпус для RAG."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from app.config import settings
from app.models import DocumentMetadata, IsaTabRecord


_READ_ONLY = re.compile(r"^\s*select\b", re.I | re.DOTALL)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma)\b",
    re.I,
)


def _resolve_sqlite_path(connection_uri: str) -> Path:
    uri = connection_uri.strip()
    if uri.startswith("sqlite:///"):
        raw = unquote(uri[len("sqlite:///") :])
        path = Path(raw)
        if not path.is_absolute():
            path = settings.data_dir_path / raw
        return path
    path = Path(uri)
    if not path.is_absolute():
        path = settings.data_dir_path / uri
    return path


def validate_readonly_query(query: str) -> None:
    q = query.strip().rstrip(";")
    if not _READ_ONLY.match(q):
        raise ValueError("Разрешены только SELECT-запросы")
    if _FORBIDDEN.search(q):
        raise ValueError("Запрос содержит запрещённые операции")


def fetch_sql_rows(connection_uri: str, query: str, max_rows: int = 500) -> list[dict[str, Any]]:
    validate_readonly_query(query)
    db_path = _resolve_sqlite_path(connection_uri)
    if not db_path.exists():
        raise FileNotFoundError(f"База данных не найдена: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(query)
        rows = cur.fetchmany(max_rows)
        return [dict(row) for row in rows]
    finally:
        conn.close()


def rows_to_text(rows: list[dict[str, Any]], title: str) -> str:
    if not rows:
        return f"# {title}\n(пустой результат)"
    headers = list(rows[0].keys())
    lines = [f"# {title}", "## Columns: " + ", ".join(headers)]
    for i, row in enumerate(rows, 1):
        parts = [f"{k}={row[k]}" for k in headers if row[k] is not None]
        lines.append(f"Row {i}: " + " | ".join(parts))
    return "\n".join(lines)


def make_sql_doc_id(title: str, content: str) -> str:
    digest = hashlib.sha256(content[:1500].encode("utf-8")).hexdigest()[:12]
    safe = re.sub(r"[^\w\-]+", "_", title)[:40]
    return f"sql_{safe}_{digest}"


def build_sql_metadata(
    title: str,
    rows: list[dict[str, Any]],
    base: DocumentMetadata | None = None,
) -> DocumentMetadata:
    meta = base or DocumentMetadata()
    meta.title = title
    meta.source = "sql_import"
    meta.tags = list(set(meta.tags + ["sql_import", "structured_experiment"]))
    meta.allotrope_process_uri = "allotrope:process/flotation-laboratory-assay"

    if rows:
        headers = [h.lower() for h in rows[0].keys()]
        for row in rows[:20]:
            for key, val in row.items():
                lk = str(key).lower()
                if val is None:
                    continue
                if "ph" in lk:
                    meta.process_parameters["pH"] = val
                elif "dosage" in lk or "доз" in lk or "кг" in lk:
                    meta.process_parameters["reagent_dosage"] = val
                elif "recover" in lk or "извлеч" in lk:
                    meta.measurement_results["recovery_pct"] = val
                elif "sample" in lk or "проба" in lk:
                    meta.sample_id = str(val)
        meta.isa_tab = IsaTabRecord(
            investigation_id=title,
            study_id="sql_study_1",
            assay_id="sql_assay_1",
            factor_names=headers[:6],
            factor_values={k: rows[0].get(k) for k in rows[0] if rows[0].get(k) is not None},
            measurement_type=(
                "recovery_pct"
                if any("recover" in h or "извлеч" in h for h in headers)
                else "assay"
            ),
            measurement_value=str(rows[0].get(headers[0], "")),
            unit="%",
        )

    return meta

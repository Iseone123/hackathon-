"""HTTP-клиент для Streamlit UI."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
TIMEOUT = httpx.Timeout(600.0, connect=10.0)

__all__ = [
    "API_URL",
    "TIMEOUT",
    "health",
    "index_status",
    "demo_examples",
    "ingest_file",
    "ingest_batch",
    "ingest_sync",
    "ingest_sql",
    "generate",
    "submit_feedback",
    "download_export",
    "update_roadmap",
]


def health() -> dict[str, Any]:
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.get(f"{API_URL}/health")
        r.raise_for_status()
        return r.json()


def index_status(directory: str | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=TIMEOUT) as client:
        params = {"directory": directory} if directory else {}
        r = client.get(f"{API_URL}/index/status", params=params)
        r.raise_for_status()
        return r.json()


def demo_examples() -> list[dict[str, Any]]:
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.get(f"{API_URL}/demo/examples")
        r.raise_for_status()
        return r.json().get("examples", [])


def ingest_file(filename: str, content: bytes, metadata: dict | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.post(
            f"{API_URL}/ingest",
            files={"file": (filename, content)},
            data={"metadata": json.dumps(metadata or {})},
        )
        r.raise_for_status()
        return r.json()


def ingest_batch(directory: str, only_missing: bool = False) -> dict[str, Any]:
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.post(
            f"{API_URL}/ingest/batch",
            params={"directory": directory, "only_missing": only_missing},
        )
        r.raise_for_status()
        return r.json()


def ingest_sync(directory: str | None = None) -> dict[str, Any]:
    with httpx.Client(timeout=TIMEOUT) as client:
        params = {"directory": directory} if directory else {}
        r = client.post(f"{API_URL}/ingest/sync", params=params)
        r.raise_for_status()
        return r.json()


def ingest_sql(connection_uri: str, query: str, title: str = "SQL import") -> dict[str, Any]:
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.post(
            f"{API_URL}/ingest/sql",
            json={"connection_uri": connection_uri, "query": query, "title": title},
        )
        r.raise_for_status()
        return r.json()


def _api_error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        detail = body.get("detail", body)
        if isinstance(detail, list):
            return str(detail)
        return str(detail)
    except Exception:
        return response.text[:500] or response.reason_phrase


def generate(
    problem: str,
    constraints: str,
    top_k: int = 12,
    weights: dict[str, float] | None = None,
    auto_ingest: bool = False,
    ingest_directories: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "problem": problem,
        "constraints": constraints,
        "top_k": top_k,
        "auto_ingest": auto_ingest,
    }
    if weights:
        payload["weights"] = weights
    if ingest_directories:
        payload["ingest_directories"] = ingest_directories
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.post(f"{API_URL}/hypotheses/generate", json=payload)
        if r.status_code == 429:
            raise RuntimeError(
                _api_error_message(r)
                or "Превышен лимит YandexGPT. Подождите 1–2 минуты и повторите."
            )
        if r.status_code >= 400:
            raise RuntimeError(f"API {r.status_code}: {_api_error_message(r)}")
        return r.json()


def submit_feedback(hypothesis_id: str, status: str, comment: str = "") -> dict[str, Any]:
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.post(
            f"{API_URL}/hypotheses/{hypothesis_id}/feedback",
            json={"status": status, "comment": comment},
        )
        r.raise_for_status()
        return r.json()


def update_roadmap(hypothesis_id: str, steps: list[dict]) -> dict[str, Any]:
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.patch(
            f"{API_URL}/hypotheses/{hypothesis_id}/roadmap",
            json={"steps": steps},
        )
        r.raise_for_status()
        return r.json()


def download_export(generation_id: str, fmt: str) -> bytes:
    with httpx.Client(timeout=TIMEOUT) as client:
        if fmt in ("pdf", "docx"):
            r = client.post(
                f"{API_URL}/export/report",
                params={"generation_id": generation_id, "format": fmt},
            )
        else:
            r = client.get(
                f"{API_URL}/export/tasks",
                params={"generation_id": generation_id, "format": fmt},
            )
        r.raise_for_status()
        return r.content

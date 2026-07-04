#!/usr/bin/env python3
"""Smoke test: health, index, Neo4j subgraph для demo-кейса КГМК."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.demo_scenarios import DEMO_SCENARIOS  # noqa: E402
from app.ingest.index_status import get_index_status  # noqa: E402
from app.rag.retrieval import RAGRetriever  # noqa: E402

LAB_XLSX = "Лабораторные опыты.xlsx"


def smoke_demo(*, skip_rag: bool = False) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    status = get_index_status()

    missing = status.get("missing") or []
    demo_dir_missing = [
        m for m in missing
        if any(m["path"].startswith(f"Пример {i}") for i in range(1, 5))
    ]
    lab_missing = [m for m in missing if "Лабораторные опыты" in m.get("path", "")]
    if demo_dir_missing:
        errors.append(
            f"Demo dirs not indexed: {len(demo_dir_missing)} "
            f"(run: python backend/scripts/preindex_demo.py)"
        )
    elif lab_missing:
        warnings.append(
            f"Lab xlsx not indexed ({LAB_XLSX}) — ML/counterfactual may use fallback. "
            "Run preindex_demo.py with valid YC_API_KEY."
        )

    neo4j = status.get("neo4j") or {}
    if not neo4j.get("available"):
        errors.append("Neo4j unavailable (docker-compose up neo4j)")
    elif neo4j.get("nodes", 0) < 1:
        errors.append("Neo4j graph is empty — re-run preindex with Neo4j up")

    qdrant_points = status.get("qdrant_points", 0)
    if qdrant_points < 10:
        errors.append(f"Qdrant has too few points ({qdrant_points}) — run preindex")

    if skip_rag:
        return errors, warnings

    scenario = DEMO_SCENARIOS[0]
    try:
        retriever = RAGRetriever()
        retrieval = retriever.retrieve(scenario.problem, scenario.constraints, top_k=8)
    except Exception as exc:
        warnings.append(f"RAG smoke skipped (LLM/embeddings): {exc}")
        return errors, warnings

    chunks = retrieval.get("chunks") or []
    subgraph = retrieval.get("subgraph") or {}
    if len(chunks) < 3:
        errors.append(f"RAG returned only {len(chunks)} chunks for KGMK scenario")
    if not subgraph.get("nodes"):
        warnings.append("RAG subgraph empty for KGMK — check Neo4j entity ingest")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test demo pipeline prerequisites")
    parser.add_argument("--skip-rag", action="store_true", help="Only check index/Neo4j/Qdrant")
    args = parser.parse_args()

    errors, warnings = smoke_demo(skip_rag=args.skip_rag)
    status = get_index_status()
    neo4j = status.get("neo4j") or {}
    print("=== Smoke test ===")
    print(f"Indexed: {status.get('indexed_files')}/{status.get('total_files')} files")
    print(f"Qdrant points: {status.get('qdrant_points')}")
    print(
        f"Neo4j: available={neo4j.get('available')} "
        f"nodes={neo4j.get('nodes')} rels={neo4j.get('relationships')}"
    )
    if warnings:
        print("\nWARN:")
        for msg in warnings:
            print(f"  - {msg}")
    if errors:
        print("\nFAIL:")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("\nOK — demo prerequisites satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Таблицы и сортировка гипотез для Streamlit."""

from __future__ import annotations

import pandas as pd


def sorted_hypotheses(hypotheses: list[dict]) -> list[dict]:
    return sorted(
        hypotheses,
        key=lambda x: (
            1 if (x.get("judge_verdict") or {}).get("approved") else 0,
            (x.get("judge_verdict") or {}).get("objective_score", 0),
        ),
        reverse=True,
    )


def source_overlap_label(h: dict, retrieval_doc_ids: set[str]) -> str:
    sources = h.get("sources") or []
    if not sources:
        return "—"
    parts = []
    for s in sources:
        doc_id = s.get("doc_id", "")
        in_rag = "✓ RAG" if doc_id in retrieval_doc_ids else "✗ нет в RAG"
        parts.append(f"{doc_id[:28]} ({in_rag})")
    return "; ".join(parts)


def hypotheses_table(
    hypotheses: list[dict],
    retrieval_doc_ids: set[str] | None = None,
) -> pd.DataFrame:
    rag_ids = retrieval_doc_ids or set()
    rows = []
    for h in hypotheses:
        sb = h.get("score_breakdown") or {}
        jv = h.get("judge_verdict") or {}
        approved = jv.get("approved")
        rows.append(
            {
                "Статус": "✅ одобр." if approved else "❌ откл.",
                "JQI obj": round(jv.get("objective_score", 0), 3),
                "Судья": jv.get("overall_score", 0),
                "Score": round(sb.get("composite", 0), 3),
                "Источник": source_overlap_label(h, rag_ids),
                "Гипотеза": h.get("text", "")[:120],
                "Новизна": h.get("novelty_score"),
                "Реализ.": h.get("feasibility_score"),
                "Ценность": h.get("expected_value_score"),
                "id": h.get("id"),
            }
        )
    return pd.DataFrame(rows)

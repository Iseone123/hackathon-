"""Анализ точности по сохранённым прогонам API + эталоны из Пример 1–4."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.measure_accuracy import (  # noqa: E402
    BENCHMARK_CASES,
    _extract_gold_topics,
    _find_processed,
    _parse_excel_kpi,
    aggregate,
    citation_support_score,
    excel_retrieval_hit,
    topic_recall,
)

DATA_DIR = ROOT.parent / "data"
OUT_DIR = DATA_DIR / "batch_analysis"

# Файлы прогонов: имя -> путь к JSON ответа API
RUN_FILES: dict[str, Path] = {
    "kgmk": OUT_DIR / "kgmk_rerun.json",
    "nof_vkr": OUT_DIR / "run_nof_vkr.json",
    "nof_med": OUT_DIR / "run_nof_med.json",
    "tof": OUT_DIR / "run_tof.json",
}


def analyze_run(case_id: str, result: dict) -> dict:
    case = next(c for c in BENCHMARK_CASES if c.id == case_id)
    gold_doc = _find_processed(case.hypotheses_stem)
    excel_doc = _find_processed(case.excel_stem)
    gold_topics = _extract_gold_topics(gold_doc["text"]) if gold_doc else []
    excel_facts = _parse_excel_kpi(excel_doc) if excel_doc else {}
    excel_doc_id = excel_doc["id"] if excel_doc else ""

    hyps = result.get("hypotheses", [])
    js = result.get("judge_summary", {})
    combined = " ".join(
        (h.get("text", "") + " " + h.get("mechanism", "")) for h in hyps
    )
    topics = topic_recall(gold_topics, combined)
    retrieval_ids = result.get("retrieval_doc_ids", [])

    class _H:
        def __init__(self, d: dict) -> None:
            self.text = d.get("text", "")
            self.sources = d.get("sources", [])

    citation = citation_support_score([_H(h) for h in hyps])

    rows = []
    for h in hyps:
        v = h.get("judge_verdict") or {}
        rows.append({
            "text": h.get("text", "")[:100],
            "approved": v.get("approved"),
            "score": v.get("overall_score"),
            "grounded": v.get("source_grounded"),
            "snippet": (h.get("sources") or [{}])[0].get("snippet", "")[:100],
        })

    return {
        "case_id": case_id,
        "case_name": case.name,
        "generation_id": result.get("generation_id"),
        "jqi": js.get("jqi", 0),
        "approved": js.get("approved", 0),
        "total": js.get("total", len(hyps)),
        "grounding_rate": js.get("grounding_rate", 0),
        "tz_compliance_pct": js.get("avg_case_compliance_pct", 0),
        "topic_recall": topics["recall"],
        "topic_matched": topics["matched"],
        "topic_missed": topics["missed"],
        "excel_in_retrieval": excel_retrieval_hit(excel_doc_id, retrieval_ids),
        "excel_kpi_facts": excel_facts,
        "citation_support_rate": citation["rate"],
        "hypotheses": rows,
    }


def main() -> None:
    report: list[dict] = []
    for case_id, path in RUN_FILES.items():
        if not path.exists():
            print(f"SKIP {case_id}: нет {path.name}")
            continue
        result = json.loads(path.read_text(encoding="utf-8"))
        if "detail" in result and "hypotheses" not in result:
            print(f"ERROR {case_id}: {result.get('detail')}")
            continue
        row = analyze_run(case_id, result)
        report.append(row)
        print(
            f"{row['case_name']}: JQI={row['jqi']:.1f} "
            f"approved={row['approved']}/{row['total']} "
            f"topic_recall={row['topic_recall']:.0%} "
            f"excel_hit={row['excel_in_retrieval']}"
        )

    summary = aggregate(report)
    out = {"summary": summary, "cases": report}
    out_path = OUT_DIR / "accuracy_report.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== СВОДКА ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"Сохранено: {out_path}")


if __name__ == "__main__":
    main()

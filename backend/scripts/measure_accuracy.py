"""Замер точности пайплайна по эталонам из data/Пример 1–4 (docx + xlsx)."""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.hypotheses.generator import HypothesisGenerator  # noqa: E402
from app.rag.text_overlap import citation_overlap  # noqa: E402

DATA_DIR = ROOT.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
OUT_DIR = DATA_DIR / "batch_analysis"


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    name: str
    example_dir: str
    hypotheses_stem: str
    excel_stem: str
    problem: str
    constraints: str


BENCHMARK_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(
        id="kgmk",
        name="Пример 1 — КГМК",
        example_dir="Пример 1",
        hypotheses_stem="Гипотезы КГМК",
        excel_stem="Хвосты КГМК",
        problem=(
            "Повышение извлечения меди из хвостов КГМК "
            "при оптимизации режима флотации"
        ),
        constraints="pH 8-10, без капитальных вложений, существующее оборудование, TRL 4",
    ),
    BenchmarkCase(
        id="nof_vkr",
        name="Пример 2 — НОФ вкр",
        example_dir="Пример 2",
        hypotheses_stem="Гипотезы НОФ вкр",
        excel_stem="Хвосты НОФ Вкр",
        problem="Извлечение вкраплённой меди из хвостов НОФ при флотации",
        constraints="Энергозатраты на измельчение ограничены, pH 8-10, TRL 4",
    ),
    BenchmarkCase(
        id="nof_med",
        name="Пример 3 — НОФ мед",
        example_dir="Пример 3",
        hypotheses_stem="Гипотезы НОФ мед",
        excel_stem="Хвосты НОФ мед",
        problem="Повышение извлечения меди из хвостов НОФ при оптимизации флотации",
        constraints="pH 8-10, без капитальных вложений, TRL 4",
    ),
    BenchmarkCase(
        id="tof",
        name="Пример 4 — ТОФ",
        example_dir="Пример 4",
        hypotheses_stem="Гипотезы ТОФ",
        excel_stem="Хвосты ТОФ_2",
        problem="Повышение извлечения из хвостов ТОФ при оптимизации классификации и флотации",
        constraints="pH 8-10, без капитальных вложений, TRL 4",
    ),
)


def _find_processed(stem: str) -> dict | None:
    for path in PROCESSED_DIR.glob("*.json"):
        if path.stem.startswith(stem):
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def _extract_gold_topics(text: str) -> list[str]:
    topics: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^##\s*Гипотеза\s+\d+:\s*(.+)$", line, re.I)
        if m:
            topics.append(m.group(1).strip())
            continue
        m = re.match(r"^\d+\.\s*(.+)$", line)
        if m:
            topics.append(m.group(1).strip())
    return topics


def _topic_keywords(topic: str) -> set[str]:
    words = re.findall(r"[а-яёa-z]{4,}", topic.lower())
    stop = {
        "изменение", "добавление", "замена", "контроль", "опробование",
        "переход", "повышение", "провести", "использование", "применение",
    }
    return {w for w in words if w not in stop}


def topic_recall(gold_topics: list[str], generated_text: str) -> dict:
    """Доля эталонных направлений, затронутых сгенерированными гипотезами."""
    if not gold_topics:
        return {"recall": 0.0, "matched": [], "missed": [], "total": 0}
    combined = generated_text.lower()
    matched: list[str] = []
    missed: list[str] = []
    for topic in gold_topics:
        kws = _topic_keywords(topic)
        if not kws:
            continue
        hits = sum(1 for k in kws if k in combined)
        if hits >= max(1, len(kws) // 3):
            matched.append(topic)
        else:
            missed.append(topic)
    total = len(gold_topics)
    return {
        "recall": round(len(matched) / max(total, 1), 3),
        "matched": matched,
        "missed": missed,
        "total": total,
    }


def _parse_excel_kpi(doc: dict) -> dict:
    """Ключевые факты из xlsx: доля извлекаемого металла в хвостах."""
    text = doc.get("text", "")
    facts: dict[str, float | str] = {"source": doc.get("metadata", {}).get("source", "")}
    m = re.search(
        r"Итого извлекаемый металл в хвостах:\s*([\d.,]+)\s*%",
        text,
        re.I,
    )
    if not m:
        m = re.search(
            r"Итого извлекаемый металл\s*\|\s*\|\s*([\d.,]+)",
            text,
            re.I,
        )
    if m:
        facts["recoverable_metal_pct"] = float(m.group(1).replace(",", "."))
    m2 = re.search(r"Отвальные хвосты:\s*([\d.,eE+-]+)\s*т", text, re.I)
    if not m2:
        m2 = re.search(r"Отвальные хвосты\s*\|\s*([\d.,]+)", text, re.I)
    if m2:
        val = m2.group(1).replace(",", ".")
        facts["tailings_tonnage"] = float(val)
    classes = re.findall(
        r"(?:\|\s*|-\s*)([+\-]?\d+(?:\s*\+\s*\d+)?)\s*мкм",
        text,
        re.I,
    )
    if classes:
        facts["grain_classes"] = classes[:6]
    return facts


def excel_retrieval_hit(excel_doc_id: str, retrieval_doc_ids: list[str]) -> bool:
    stem = excel_doc_id.split("_")[0] if excel_doc_id else ""
    return any(
        excel_doc_id in rid or stem in rid or "Хвосты" in rid and excel_doc_id[:10] in rid
        for rid in retrieval_doc_ids
    )


def citation_support_score(hypotheses: list) -> dict:
    """Доля гипотез, где ключевой реагент из text встречается в snippet."""
    supported = 0
    details: list[dict] = []
    for h in hypotheses:
        if isinstance(h, dict):
            text = h.get("text", "")
            sources = h.get("sources") or []
            snippet = (sources[0].get("snippet", "") if sources else "").lower()
        else:
            text = h.text
            snippet = (h.sources[0].snippet if h.sources else "").lower()
        terms = _topic_keywords(text)
        reagent_terms = [
            t for t in terms
            if t not in {"меди", "хвостов", "флотации", "извлечение", "повысит", "относительно"}
        ]
        hit = any(t in snippet for t in reagent_terms[:5]) if reagent_terms else bool(snippet)
        details.append({"text": str(text)[:90], "reagent_in_snippet": hit})
        if hit:
            supported += 1
    n = max(len(hypotheses), 1)
    return {"rate": round(supported / n, 3), "details": details}


def run_case(gen: HypothesisGenerator, case: BenchmarkCase) -> dict:
    gold_doc = _find_processed(case.hypotheses_stem)
    excel_doc = _find_processed(case.excel_stem)
    gold_topics = _extract_gold_topics(gold_doc["text"]) if gold_doc else []
    excel_facts = _parse_excel_kpi(excel_doc) if excel_doc else {}
    excel_doc_id = excel_doc["id"] if excel_doc else ""

    result = gen.generate(
        problem=case.problem,
        constraints=case.constraints,
        top_k=16,
    )
    hyps = result["hypotheses"]
    js = result["judge_summary"]
    combined_gen = " ".join(h.text + " " + h.mechanism for h in hyps)
    topics = topic_recall(gold_topics, combined_gen)
    retrieval_ids = result.get("retrieval_doc_ids", [])
    excel_hit = excel_retrieval_hit(excel_doc_id, retrieval_ids) if excel_doc_id else False

    hyp_rows = []
    for h in hyps:
        v = h.judge_verdict
        hyp_rows.append({
            "text": h.text,
            "approved": v.approved if v else False,
            "score": v.overall_score if v else 0,
            "grounded": v.source_grounded if v else False,
            "snippet": h.sources[0].snippet[:120] if h.sources else "",
            "issues": (v.issues or [])[:3] if v else [],
        })

    return {
        "case_id": case.id,
        "case_name": case.name,
        "example_dir": case.example_dir,
        "generation_id": result.get("generation_id"),
        "jqi": js.jqi if js else 0,
        "approved": js.approved if js else 0,
        "total": js.total if js else len(hyps),
        "grounding_rate": js.grounding_rate if js else 0,
        "tz_compliance_pct": js.avg_case_compliance_pct if js else 0,
        "gold_topics_count": len(gold_topics),
        "topic_recall": topics["recall"],
        "topic_matched": topics["matched"],
        "topic_missed": topics["missed"][:5],
        "excel_in_retrieval": excel_hit,
        "excel_doc_id": excel_doc_id,
        "excel_kpi_facts": excel_facts,
        "citation_support": citation_support_score(hyps),
        "hypotheses": hyp_rows,
    }


def aggregate(report: list[dict]) -> dict:
    n = len(report)
    if not n:
        return {}
    return {
        "cases": n,
        "avg_jqi": round(sum(r["jqi"] for r in report) / n, 2),
        "avg_topic_recall": round(sum(r["topic_recall"] for r in report) / n, 3),
        "avg_grounding_rate": round(sum(r["grounding_rate"] for r in report) / n, 3),
        "approval_rate": round(
            sum(r["approved"] for r in report) / max(sum(r["total"] for r in report), 1), 3
        ),
        "excel_retrieval_rate": round(
            sum(1 for r in report if r["excel_in_retrieval"]) / n, 3
        ),
        "avg_citation_support": round(
            sum(r.get("citation_support_rate", r.get("citation_support", {}).get("rate", 0)) for r in report) / n, 3
        ),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    gen = HypothesisGenerator()
    report: list[dict] = []

    for i, case in enumerate(BENCHMARK_CASES):
        print(f"\n[{i + 1}/{len(BENCHMARK_CASES)}] {case.name}…", flush=True)
        if i > 0:
            time.sleep(5)
        try:
            row = run_case(gen, case)
            report.append(row)
            print(
                f"  JQI={row['jqi']:.1f} approved={row['approved']}/{row['total']} "
                f"topic_recall={row['topic_recall']:.0%} "
                f"excel_hit={row['excel_in_retrieval']}",
                flush=True,
            )
        except Exception as exc:
            print(f"  ERROR: {exc}", flush=True)
            report.append({"case_id": case.id, "error": str(exc)})

    summary = aggregate([r for r in report if "error" not in r])
    out = {"summary": summary, "cases": report}
    out_path = OUT_DIR / "accuracy_report.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== СВОДКА ТОЧНОСТИ ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"\nСохранено: {out_path}")


if __name__ == "__main__":
    main()

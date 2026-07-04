"""Прогон демо-сценариев с детальным отчётом судьи для калибровки промптов."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.demo_scenarios import DEMO_SCENARIOS  # noqa: E402
from app.hypotheses.generator import HypothesisGenerator  # noqa: E402

# Ориентиры из файлов «Пример 1–4» — типичные направления, не копировать дословно
EXAMPLE_HINTS = """
Примеры направлений из кейсов (используй как ориентир, но обосновывай ТОЛЬКО цитатами из RAG):
- КГМК: КМЦ 0,3–0,5 кг/т, pH 8–10, подавление пустой породы, флотация меди из хвостов
- НОФ: вкраплённая медь, контактные чаны, плотность пульпы, Finfix 300, гидроциклоны
- Учебник: дозировки реагентов, схемы флотации, режимы pH — только если есть в контексте
"""


def hypothesis_detail(h: object, problem: str) -> dict:
    d = h.model_dump(mode="json") if hasattr(h, "model_dump") else h
    v = d.get("judge_verdict") or {}
    sources = d.get("sources") or []
    return {
        "text": d.get("text", ""),
        "mechanism": d.get("mechanism", ""),
        "reasoning": d.get("reasoning", ""),
        "sources": sources,
        "roadmap": d.get("verification_roadmap"),
        "approved": v.get("approved"),
        "overall_score": v.get("overall_score"),
        "source_grounded": v.get("source_grounded"),
        "testability": v.get("testability"),
        "evidence_quality": v.get("evidence_quality"),
        "relevance": v.get("relevance"),
        "issues": v.get("issues") or [],
        "recommendations": v.get("recommendations") or [],
        "tz_pct": (v.get("case_compliance") or {}).get("compliance_pct"),
    }


def main() -> None:
    gen = HypothesisGenerator()
    out_dir = ROOT.parent / "data" / "batch_analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    report: list[dict] = []

    scenarios = list(DEMO_SCENARIOS)
    for i, sc in enumerate(scenarios):
        print(f"\n[{i + 1}/{len(scenarios)}] {sc.name}…", flush=True)
        if i > 0:
            time.sleep(5)
        problem = sc.problem
        constraints = sc.constraints
        try:
            result = gen.generate(
                problem=problem,
                constraints=constraints,
                top_k=16,
            )
            js = result.get("judge_summary")
            rows = [hypothesis_detail(h, problem) for h in result.get("hypotheses", [])]
            entry = {
                "scenario_id": sc.id,
                "scenario_name": sc.name,
                "data_path": sc.data_path,
                "problem": problem,
                "constraints": constraints,
                "generation_id": result.get("generation_id"),
                "jqi": js.jqi if js else None,
                "approved": js.approved if js else 0,
                "rejected": js.rejected if js else 0,
                "grounding_pct": js.grounding_pct if js and hasattr(js, "grounding_pct") else None,
                "hypotheses": rows,
                "conflicts": result.get("conflicts_detected", []),
            }
            report.append(entry)
            print(
                f"  JQI={entry['jqi']} approved={entry['approved']}/{len(rows)}",
                flush=True,
            )
            for row in rows:
                mark = "✓" if row["approved"] else "✗"
                print(f"    {mark} score={row['overall_score']} grounded={row['source_grounded']}")
                print(f"       {row['text'][:90]}…")
                for issue in row["issues"][:4]:
                    print(f"       • {issue}")
        except Exception as exc:
            print(f"  ERROR: {exc}", flush=True)
            report.append({"scenario_id": sc.id, "error": str(exc)})

    out_path = out_dir / "judge_prompt_analysis.json"
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\nСохранено: {out_path}")


if __name__ == "__main__":
    main()

"""Пакетный прогон генерации с разными формулировками проблемы."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.hypotheses.generator import HypothesisGenerator  # noqa: E402
from app.judge.checklist import evaluate_case_compliance  # noqa: E402

SCENARIOS = [
    {
        "id": "good",
        "label": "Эталон (демо)",
        "problem": (
            "Повышение извлечения меди из хвостов КГМК "
            "при оптимизации режима флотации"
        ),
        "constraints": (
            "pH 8-10, без капитальных вложений, существующее оборудование, TRL 4"
        ),
    },
    {
        "id": "short_problem",
        "label": "Короткая проблема",
        "problem": "Повышение извлечения меди",
        "constraints": "pH 8-10",
    },
    {
        "id": "vague",
        "label": "Размытая формулировка",
        "problem": "Улучшить флотацию хвостов",
        "constraints": "",
    },
    {
        "id": "all_in_problem",
        "label": "Всё в поле проблемы (ошибка UX)",
        "problem": (
            "Повышение извлечения меди из хвостов КГМК. "
            "Ограничения: pH 8-10, без капитальных вложений, TRL 4"
        ),
        "constraints": "",
    },
    {
        "id": "offtopic",
        "label": "Не по теме",
        "problem": "Куда пойти выпить в центре Москвы",
        "constraints": "бюджет 5000 руб",
    },
]


def summarize(result: dict) -> dict:
    hyps = result.get("hypotheses", [])
    js = result.get("judge_summary")
    rows = []
    for h in hyps:
        h_dict = h.model_dump(mode="json") if hasattr(h, "model_dump") else h
        compliance = evaluate_case_compliance(h, result["problem"])
        v = h_dict.get("judge_verdict") or {}
        failed = [i.label for i in compliance.items if i.required and not i.passed]
        rows.append(
            {
                "approved": v.get("approved"),
                "score": v.get("overall_score"),
                "tz_pct": compliance.compliance_pct,
                "failed_tz": failed,
                "text": h_dict.get("text", "")[:100],
                "issues": (v.get("issues") or [])[:3],
            }
        )
    return {
        "generation_id": result.get("generation_id"),
        "count": len(rows),
        "jqi": js.jqi if js else None,
        "approved": js.approved if js else 0,
        "rejected": js.rejected if js else 0,
        "rows": rows,
    }


def main() -> None:
    gen = HypothesisGenerator()
    out_dir = ROOT.parent / "data" / "batch_analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    report: list[dict] = []

    for i, sc in enumerate(SCENARIOS):
        print(f"\n[{i+1}/{len(SCENARIOS)}] {sc['label']}…", flush=True)
        if i > 0:
            time.sleep(3)
        try:
            result = gen.generate(
                problem=sc["problem"],
                constraints=sc["constraints"],
                top_k=10,
            )
            summary = summarize(result)
            summary["scenario"] = sc
            report.append(summary)
            print(
                f"  OK: {summary['approved']}/{summary['count']} approved, "
                f"JQI={summary['jqi']}"
            )
            for row in summary["rows"]:
                mark = "✓" if row["approved"] else "✗"
                print(f"    {mark} TZ={row['tz_pct']}% {row['text']}…")
                if row["failed_tz"]:
                    print(f"       fail: {row['failed_tz']}")
        except Exception as exc:
            print(f"  ERROR: {exc}")
            report.append({"scenario": sc, "error": str(exc)})

    out_path = out_dir / "batch_report.json"
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\nСохранено: {out_path}")


if __name__ == "__main__":
    main()

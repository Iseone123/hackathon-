"""Анализ прогонов генерации: чеклист, судья, частые причины отклонения."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# backend root on path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.judge.checklist import evaluate_case_compliance  # noqa: E402
from app.judge.constraints import check_constraints  # noqa: E402
from app.models import Hypothesis, RiskScores, SourceRef  # noqa: E402


def load_hypothesis(raw: dict) -> Hypothesis:
    risk = raw.get("risk") or {}
    sources = [
        SourceRef(**s) if isinstance(s, dict) else SourceRef(doc_id=str(s), snippet="")
        for s in raw.get("sources", [])
    ]
    return Hypothesis(
        id=raw.get("id", "x"),
        text=raw.get("text", ""),
        mechanism=raw.get("mechanism", ""),
        novelty_score=float(raw.get("novelty_score", 5)),
        feasibility_score=float(raw.get("feasibility_score", 5)),
        expected_value_score=float(raw.get("expected_value_score", 5)),
        risk=RiskScores(
            technical=float(risk.get("technical", 5)),
            economic=float(risk.get("economic", 5)),
        ),
        sources=sources,
        verification_roadmap=raw.get("verification_roadmap") or [],
        reasoning=raw.get("reasoning", ""),
        influence_graph=raw.get("influence_graph") or {},
    )


def analyze_file(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    problem = data.get("problem", "")
    constraints = data.get("constraints", "")
    hyps = data.get("hypotheses", [])
    rows = []
    for h_raw in hyps:
        h = load_hypothesis(h_raw)
        compliance = evaluate_case_compliance(h, problem)
        constraint_issues = check_constraints(h, constraints)
        verdict = h_raw.get("judge_verdict") or {}
        failed_mandatory = [
            i.label for i in compliance.items if i.required and not i.passed
        ]
        failed_optional = [
            i.label for i in compliance.items if not i.required and not i.passed
        ]
        rows.append(
            {
                "id": h.id,
                "text_short": h.text[:80],
                "approved": verdict.get("approved"),
                "overall_score": verdict.get("overall_score"),
                "objective_score": verdict.get("objective_score"),
                "compliance_pct": compliance.compliance_pct,
                "failed_mandatory": failed_mandatory,
                "failed_optional": failed_optional,
                "constraint_issues": constraint_issues,
                "judge_issues": verdict.get("issues", []),
                "source_grounded": verdict.get("source_grounded"),
                "graph_nodes": len((h_raw.get("influence_graph") or {}).get("nodes") or []),
                "graph_links": len((h_raw.get("influence_graph") or {}).get("links") or []),
            }
        )
    js = data.get("judge_summary") or {}
    return {
        "file": path.name,
        "problem": problem[:100],
        "constraints": constraints[:80],
        "hypothesis_count": len(rows),
        "jqi": js.get("jqi"),
        "approved": js.get("approved"),
        "rejected": js.get("rejected"),
        "rows": rows,
    }


def main() -> None:
    hyp_dir = ROOT.parent / "data" / "hypotheses"
    files = sorted(hyp_dir.glob("*.json"))
    if not files:
        print("Нет файлов в data/hypotheses/")
        return

    all_mandatory_fails: Counter[str] = Counter()
    all_judge_issues: Counter[str] = Counter()
    approval_by_run: list[tuple[str, int, int, float | None]] = []
    empty_graphs = 0
    total_hyps = 0

    print("=" * 72)
    print("АНАЛИЗ СОХРАНЁННЫХ ПРОГОНОВ")
    print("=" * 72)

    for path in files:
        run = analyze_file(path)
        appr = run["approved"] or 0
        total = run["hypothesis_count"]
        approval_by_run.append((run["file"], appr, total, run["jqi"]))
        print(f"\n--- {run['file']} ---")
        print(f"Проблема: {run['problem']}")
        print(f"Ограничения: {run['constraints'] or '(нет)'}")
        print(f"Гипотез: {total}, одобрено: {appr}, JQI: {run['jqi']}")

        for row in run["rows"]:
            total_hyps += 1
            if row["graph_nodes"] < 2 or row["graph_links"] < 1:
                empty_graphs += 1
            status = "OK" if row["approved"] else "REJECT"
            print(f"  [{status}] score={row['overall_score']} obj={row['objective_score']} "
                  f"TZ={row['compliance_pct']}% graph={row['graph_nodes']}n/{row['graph_links']}e | "
                  f"{row['text_short']}…")
            if row["failed_mandatory"]:
                print(f"       FAIL TZ: {row['failed_mandatory']}")
                for label in row["failed_mandatory"]:
                    all_mandatory_fails[label] += 1
            if row["constraint_issues"]:
                print(f"       Ограничения: {row['constraint_issues']}")
            if row["judge_issues"]:
                for issue in row["judge_issues"][:3]:
                    all_judge_issues[issue[:120]] += 1
                if not row["approved"] and row["judge_issues"]:
                    print(f"       Судья: {row['judge_issues'][:2]}")

    print("\n" + "=" * 72)
    print("СВОДКА ПО ВСЕМ ПРОГОНАМ")
    print("=" * 72)
    print("\nПрогоны (файл | одобрено/всего | JQI):")
    for fname, appr, total, jqi in approval_by_run:
        jqi_s = f"{jqi:.1f}" if jqi is not None else "—"
        print(f"  {fname}: {appr}/{total}, JQI={jqi_s}")

    print("\nТоп причин FAIL по чеклисту ТЗ:")
    for label, cnt in all_mandatory_fails.most_common(10):
        print(f"  {cnt}x — {label}")

    print("\nТоп замечаний судьи:")
    for issue, cnt in all_judge_issues.most_common(12):
        print(f"  {cnt}x — {issue}")

    print(f"\nГрафы влияния: пустых/неполных {empty_graphs}/{total_hyps} "
          f"({100*empty_graphs/max(total_hyps,1):.0f}%)")


if __name__ == "__main__":
    main()

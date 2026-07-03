"""CLI entrypoint: end-to-end пайплайн генерации гипотез."""

from __future__ import annotations

import argparse
import json
import sys

from app.config import ensure_dirs
from app.generate import generate_hypotheses
from app.llm_client import YandexLLMClient
from app.ranking import rank_hypotheses
from app.report import save_report
from app.retrieval import retrieve


def run_pipeline(problem: str, constraints: str = "") -> dict:
    """Полный пайплайн: retrieval → generation → ranking → report."""
    ensure_dirs()
    llm = YandexLLMClient()

    print("→ Поиск релевантного контекста...")
    chunks = retrieve(problem, constraints, llm=llm)
    print(f"  Найдено {len(chunks)} фрагментов")

    print("→ Генерация гипотез через Yandex AI Studio...")
    hypotheses = generate_hypotheses(problem, constraints, chunks, llm=llm)
    print(f"  Получено {len(hypotheses)} гипотез")

    print("→ Ранжирование...")
    ranked = rank_hypotheses(hypotheses)

    print("→ Сохранение отчёта...")
    json_path, md_path = save_report(problem, constraints, ranked, chunks)
    print(f"  JSON: {json_path}")
    print(f"  Markdown: {md_path}")

    return {
        "hypotheses": [h.to_dict() for h in ranked],
        "json_path": str(json_path),
        "md_path": str(md_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Генерация научных гипотез на основе локальной базы знаний"
    )
    parser.add_argument(
        "--problem",
        required=True,
        help="Целевая проблема для исследования",
    )
    parser.add_argument(
        "--constraints",
        default="",
        help="Ограничения (бюджет, сроки, технологии и т.п.)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Вывести результат в stdout как JSON",
    )
    args = parser.parse_args(argv)

    try:
        result = run_pipeline(args.problem, args.constraints)
    except Exception as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result["hypotheses"], ensure_ascii=False, indent=2))
    else:
        print("\n=== Топ гипотез ===")
        for i, h in enumerate(result["hypotheses"], start=1):
            sources = ", ".join(h["sources"]) if h["sources"] else "—"
            print(f"\n{i}. [{h['composite_score']:.3f}] {h['hypothesis']}")
            print(f"   Источники: {sources}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

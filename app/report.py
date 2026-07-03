"""Сборка JSON и markdown отчётов."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import OUTPUT_DIR, RANKING_WEIGHTS, ensure_dirs
from app.generate import Hypothesis
from app.retrieval import RetrievedChunk


def _slugify(text: str, max_len: int = 40) -> str:
    slug = "".join(ch if ch.isalnum() else "_" for ch in text.lower())
    slug = "_".join(part for part in slug.split("_") if part)
    return slug[:max_len] or "report"


def build_report_payload(
    problem: str,
    constraints: str,
    hypotheses: list[Hypothesis],
    chunks: list[RetrievedChunk],
) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "problem": problem,
        "constraints": constraints,
        "ranking_weights": RANKING_WEIGHTS,
        "retrieved_chunks": [
            {
                "source_file": c.source_file,
                "chunk_index": c.chunk_index,
                "distance": round(c.distance, 4),
                "preview": c.text[:200],
            }
            for c in chunks
        ],
        "hypotheses": [h.to_dict() for h in hypotheses],
    }


def render_markdown(problem: str, constraints: str, hypotheses: list[Hypothesis]) -> str:
    lines = [
        "# Отчёт: сгенерированные гипотезы",
        "",
        f"**Дата:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Проблема",
        problem.strip(),
        "",
        "## Ограничения",
        constraints.strip() or "_не указаны_",
        "",
        "## Гипотезы (отсортированы по composite_score)",
        "",
    ]

    for i, h in enumerate(hypotheses, start=1):
        sources = ", ".join(h.sources) if h.sources else "—"
        lines.extend(
            [
                f"### {i}. {h.hypothesis}",
                "",
                f"**Механизм:** {h.mechanism}",
                "",
                f"**Источники:** {sources}",
                "",
                "| Метрика | Балл |",
                "|---|---:|",
                f"| Новизна | {h.novelty_score} |",
                f"| Риск | {h.risk_score} |",
                f"| Ожидаемая ценность | {h.expected_value_score} |",
                f"| **Composite score** | **{h.composite_score:.3f}** |",
                "",
                f"**Обоснование:** {h.reasoning}",
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines)


def save_report(
    problem: str,
    constraints: str,
    hypotheses: list[Hypothesis],
    chunks: list[RetrievedChunk],
    *,
    output_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Сохраняет JSON и markdown в output/. Возвращает пути к файлам."""
    ensure_dirs()
    out_dir = output_dir or OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    slug = _slugify(problem)
    json_path = out_dir / f"hypotheses_{timestamp}_{slug}.json"
    md_path = out_dir / f"hypotheses_{timestamp}_{slug}.md"

    payload = build_report_payload(problem, constraints, hypotheses, chunks)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(
        render_markdown(problem, constraints, hypotheses),
        encoding="utf-8",
    )
    return json_path, md_path

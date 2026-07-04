"""Явный анализ пробелов в знаниях по сравнению с формулировкой задачи."""

from __future__ import annotations

import re
from typing import Any

from app.models import KnowledgeGap

_KEYWORD_STOPWORDS = {
    "повышение",
    "повышени",
    "оптимизации",
    "оптимизац",
    "капитальных",
    "вложений",
    "режима",
    "хвостов",
    "извлечения",
    "существующего",
    "оборудования",
    "ограничения",
    "ограничений",
    "задачи",
    "процесса",
    "процесс",
    "меди",
    "медь",
    "кгмк",
}


_DOMAIN_TOPICS = [
    ("pH", r"pH|щелоч|кислот"),
    ("реагенты", r"реагент|собирател|депрессант|кмц|ксантогенат"),
    ("извлечение", r"извлечени|recovery|выход"),
    ("оборудование", r"оборудован|установк|флотомашин|ячейк"),
    ("режим флотации", r"флотац|время|скорост|аэрац"),
    ("состав руды", r"сульфид|мед|пород|минерал"),
    ("экономика", r"себестоим|бюджет|капитал|trl"),
]


def _problem_keywords(problem: str, constraints: str) -> list[str]:
    words = re.findall(r"[а-яёa-z]{5,}", f"{problem} {constraints}".lower())
    seen: set[str] = set()
    result: list[str] = []
    for w in words:
        if w not in seen:
            seen.add(w)
            result.append(w)
    return result[:12]


def analyze_knowledge_gaps(
    problem: str,
    constraints: str,
    chunks: list[dict[str, Any]],
    keywords: list[str] | None = None,
) -> list[KnowledgeGap]:
    """Сравнивает темы задачи с покрытием retrieval-контекста."""
    gaps: list[KnowledgeGap] = []
    corpus = " ".join(c["text"].lower() for c in chunks)
    kw = keywords or _problem_keywords(problem, constraints)

    for topic, pattern in _DOMAIN_TOPICS:
        problem_relevant = bool(re.search(pattern, f"{problem} {constraints}", re.I))
        if not problem_relevant:
            continue
        coverage = bool(re.search(pattern, corpus, re.I))
        if not coverage:
            gaps.append(
                KnowledgeGap(
                    topic=topic,
                    severity="high",
                    evidence=f"В RAG-контексте нет явных данных по теме «{topic}»",
                    suggested_action=(
                        f"Добавить источники/отчёты по {topic} или уточнить постановку задачи"
                    ),
                )
            )

    for word in kw:
        if len(word) < 6 or word in _KEYWORD_STOPWORDS:
            continue
        if word not in corpus:
            gaps.append(
                KnowledgeGap(
                    topic=word,
                    severity="medium",
                    evidence=f"Ключевое слово задачи «{word}» не встречается в топ-чанках",
                    suggested_action="Расширить базу знаний или увеличить top_k RAG",
                )
            )

    if len(chunks) < 5:
        gaps.append(
            KnowledgeGap(
                topic="объём контекста",
                severity="high",
                evidence=f"Retrieval вернул только {len(chunks)} фрагментов",
                suggested_action="Проиндексировать больше данных или поднять top_k",
            )
        )

    # дедуп по topic
    seen_topics: set[str] = set()
    unique: list[KnowledgeGap] = []
    for g in gaps:
        if g.topic not in seen_topics:
            seen_topics.add(g.topic)
            unique.append(g)
    return unique[:8]

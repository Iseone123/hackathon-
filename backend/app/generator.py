"""Генерация гипотез: диагноз + retrieval + few-shot → структурированный JSON.

Anti-hallucination: модель обязана ссылаться на номера переданных ей пассажей;
ссылки на несуществующие номера вычищаются, гипотеза без валидных источников
помечается как ungrounded и штрафуется в ранжировании.
"""
from __future__ import annotations

import logging
import os

from . import llm_client
from .knowledge_base import KnowledgeBase

logger = logging.getLogger("generator")

HYPOTHESIS_SCHEMA = """[
  {
    "hypothesis": "конкретное проверяемое предложение: что изменить в схеме/режиме/оборудовании, с параметрами",
    "mechanism": "физический механизм: почему это снизит потери именно в этом классе крупности / форме",
    "target": {"element": "Ni|Cu|оба", "size_class": "класс крупности из диагноза", "problem_type": "regrind|coarse_flotation|slimes"},
    "expected_effect": "оценка эффекта со ссылкой на тонны из диагноза, например: возврат до X т Ni/год",
    "source_refs": [1, 3],
    "feasibility_note": "что уже есть на фабрике для реализации / что докупать",
    "risks": {"technical": "главный технический риск", "economic": "главный экономический риск"},
    "scores": {"novelty": 1-5, "feasibility": 1-5, "impact": 1-5, "risk": 1-5 (5 = низкий риск)},
    "verification_roadmap": ["шаг 1: лабораторный опыт ...", "шаг 2: ...", "критерий успеха: ..."]
  }
]"""

SYSTEM_PROMPT = """Ты — главный технолог-обогатитель горно-металлургического комбината, эксперт по флотации медно-никелевых руд.
По диагнозу потерь металлов с хвостами ты формулируешь проверяемые инженерные гипотезы по снижению потерь.

Правила:
1. Каждая гипотеза адресует конкретный адрес потерь из диагноза (элемент × класс крупности × форма).
2. Гипотеза конкретна: указывай параметры (диаметры насадок, крупность, время, расход) там, где источники это позволяют.
3. source_refs — ТОЛЬКО номера пассажей из раздела «Источники» ниже. Запрещено ссылаться на номера, которых нет, и придумывать факты вне пассажей и диагноза.
4. Приоритизируй гипотезы по извлекаемым тоннам из диагноза: сначала самые крупные адреса потерь.
5. Стиль формулировок — как у экспертов в примерах: короткое инженерное предложение, но добавь механизм и параметры.
6. Отвечай ТОЛЬКО валидным JSON-массивом по заданной схеме, без markdown и пояснений."""


def _retrieval_queries(diagnostics: list[dict]) -> list[str]:
    """Мульти-запрос: по каждому типу проблемы из топа диагноза."""
    queries = {
        "regrind": "доизмельчение сростков классификация гидроциклоны тонкое грохочение раскрытие минералов",
        "coarse_flotation": "флотация крупных частиц время флотации контрольная флотация фронт реагентный режим собиратель",
        "slimes": "флотация шламов тонких частиц потери переизмельчение флокуляция плотность пульпы",
    }
    seen, out = set(), []
    for d in diagnostics[:8]:
        pt = d["problem_type"]
        if pt in queries and pt not in seen:
            seen.add(pt)
            out.append(queries[pt])
    return out or [queries["regrind"]]


def retrieve_context(kb: KnowledgeBase, diagnostics: list[dict], k_per_query: int = 5) -> list[dict]:
    passages, seen_ids = [], set()
    for q in _retrieval_queries(diagnostics):
        for r in kb.search(q, k=k_per_query):
            if r["id"] not in seen_ids:
                seen_ids.add(r["id"])
                passages.append(r)
    return passages[:12]


def build_prompt(
    summary_text: str,
    goal: str,
    constraints: str,
    passages: list[dict],
    examples: list[dict],
    n_hypotheses: int,
) -> list[dict]:
    src_lines = [
        f"[{i + 1}] ({p['source']}, стр. {p['page']}): {p['text']}"
        for i, p in enumerate(passages)
    ]
    ex_lines = []
    for ex in examples[:2]:
        hyps = "\n".join(f"  - {h}" for h in ex["expert_hypotheses"])
        ex_lines.append(
            f"Объект «{ex['name']}», фрагмент диагноза:\n{ex['summary_text'][:900]}\n"
            f"Гипотезы экспертов по этому объекту:\n{hyps}"
        )
    user = f"""## Диагноз потерь (получен автоматическим анализом отчёта по хвостам)
{summary_text}

## Цель
{goal or "Максимально снизить потери Ni и Cu с отвальными хвостами"}

## Ограничения
{constraints or "Использовать существующее оборудование фабрики, без капитального строительства"}

## Источники (база знаний: учебники, регламенты, схемы)
{chr(10).join(src_lines)}

## Примеры: как формулируют гипотезы эксперты Компании (другие объекты)
{chr(10).join(ex_lines)}

## Задание
Сформулируй {n_hypotheses} гипотез по схеме:
{HYPOTHESIS_SCHEMA}"""
    return [
        {"role": "system", "text": SYSTEM_PROMPT},
        {"role": "user", "text": user},
    ]


def _validate(hyps: list, n_passages: int) -> list[dict]:
    """Вычищает ссылки на несуществующие пассажи, помечает ungrounded."""
    out = []
    for h in hyps:
        if not isinstance(h, dict) or not h.get("hypothesis"):
            continue
        refs = [r for r in (h.get("source_refs") or []) if isinstance(r, int) and 1 <= r <= n_passages]
        h["source_refs"] = refs
        h["grounded"] = bool(refs)
        out.append(h)
    return out


def generate_hypotheses(
    kb: KnowledgeBase,
    summary_text: str,
    diagnostics: list[dict],
    examples: list[dict],
    goal: str = "",
    constraints: str = "",
    n_hypotheses: int = 8,
) -> dict:
    passages = retrieve_context(kb, diagnostics)
    messages = build_prompt(summary_text, goal, constraints, passages, examples, n_hypotheses)

    n_samples = int(os.environ.get("N_CONSISTENCY_SAMPLES", "2"))
    samples: list[list[dict]] = []
    for i in range(n_samples):
        try:
            raw = llm_client.complete_json(messages, temperature=0.35 + 0.25 * i, max_tokens=6000)
            if isinstance(raw, dict):  # модель могла обернуть в {"hypotheses": [...]}
                raw = raw.get("hypotheses", [raw])
            samples.append(_validate(raw, len(passages)))
        except llm_client.LLMError as e:
            logger.warning("Сэмпл %s не удался: %s", i + 1, e)

    if not samples:
        raise llm_client.LLMError("Ни один сэмпл генерации не удался")

    hypotheses = samples[0] if len(samples) == 1 else _merge_samples(samples, n_hypotheses)

    # привязка источников: ref → полный пассаж (для отчёта и UI)
    for h in hypotheses:
        h["sources"] = [
            {
                "ref": r,
                "doc_id": passages[r - 1]["source"],
                "page": passages[r - 1]["page"],
                "snippet": passages[r - 1]["text"][:300],
            }
            for r in h["source_refs"]
        ]
    return {"hypotheses": hypotheses, "passages": passages, "n_samples_used": len(samples)}


def _merge_samples(samples: list[list[dict]], n: int) -> list[dict]:
    """Self-consistency: сведение сэмплов вторым LLM-вызовом (дедуп + отбор лучших)."""
    import json

    numbered = []
    flat: list[dict] = []
    for s_i, sample in enumerate(samples):
        for h in sample:
            flat.append(h)
            numbered.append(f"{len(flat)}. [сэмпл {s_i + 1}] {h['hypothesis']}")
    prompt = [
        {
            "role": "system",
            "text": "Ты сводишь варианты гипотез от нескольких независимых прогонов. Отвечай только JSON.",
        },
        {
            "role": "user",
            "text": (
                "Ниже пронумерованные гипотезы из нескольких прогонов. Сгруппируй дубликаты "
                f"(одно и то же решение разными словами) и выбери {n} лучших уникальных номеров. "
                "Гипотезы, встречающиеся в нескольких сэмплах, надёжнее — предпочитай их. "
                'Ответ: {"selected": [номера], "consensus": {"<номер>": <в скольких сэмплах встретилась идея>}}\n\n'
                + "\n".join(numbered)
            ),
        },
    ]
    try:
        res = llm_client.complete_json(prompt, temperature=0.1, lite=True)
        selected = [i for i in res.get("selected", []) if 1 <= i <= len(flat)][:n]
        consensus = res.get("consensus", {})
        out = []
        for i in selected:
            h = flat[i - 1]
            h["consensus_count"] = int(consensus.get(str(i), 1))
            out.append(h)
        if out:
            return out
    except (llm_client.LLMError, ValueError, TypeError) as e:
        logger.warning("Сведение сэмплов не удалось, беру первый: %s", e)
    return samples[0][:n]

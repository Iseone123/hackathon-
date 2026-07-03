"""Генерация гипотез через LLM на основе найденного контекста."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.config import NUM_HYPOTHESES
from app.llm_client import YandexLLMClient
from app.retrieval import RetrievedChunk

SYSTEM_PROMPT = """\
Ты — научный аналитик в НИИ. На основе предоставленного контекста из статей, \
патентов и отчётов сформулируй проверяемые научно-технические гипотезы.

Требования:
- Каждая гипотеза должна опираться на конкретные фрагменты контекста.
- Указывай источники по полю source_file из контекста.
- Оценки novelty_score, risk_score, expected_value_score — целые числа от 1 до 10.
- risk_score: 10 = очень высокий риск провала, 1 = минимальный риск.
- Ответ — ТОЛЬКО валидный JSON-массив объектов, без markdown и пояснений.
"""


@dataclass
class Hypothesis:
    hypothesis: str
    mechanism: str
    sources: list[str] = field(default_factory=list)
    novelty_score: float = 0.0
    risk_score: float = 0.0
    expected_value_score: float = 0.0
    reasoning: str = ""
    composite_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "hypothesis": self.hypothesis,
            "mechanism": self.mechanism,
            "sources": self.sources,
            "novelty_score": self.novelty_score,
            "risk_score": self.risk_score,
            "expected_value_score": self.expected_value_score,
            "reasoning": self.reasoning,
            "composite_score": round(self.composite_score, 4),
        }


def _format_context(chunks: list[RetrievedChunk]) -> str:
    blocks: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        blocks.append(
            f"[Фрагмент {i} | source_file={chunk.source_file} | chunk={chunk.chunk_index}]\n"
            f"{chunk.text}"
        )
    return "\n\n---\n\n".join(blocks)


def _build_user_prompt(
    problem: str,
    constraints: str,
    chunks: list[RetrievedChunk],
    num_hypotheses: int,
) -> str:
    context = _format_context(chunks)
    constraints_block = constraints.strip() or "не указаны"
    schema = """
[
  {
    "hypothesis": "формулировка гипотезы",
    "mechanism": "предполагаемый механизм или подход",
    "sources": ["имя_файла_источника"],
    "novelty_score": 7,
    "risk_score": 4,
    "expected_value_score": 8,
    "reasoning": "краткое обоснование со ссылкой на контекст"
  }
]
"""
    return f"""\
Целевая проблема:
{problem.strip()}

Ограничения:
{constraints_block}

Контекст из базы знаний:
{context}

Сгенерируй ровно {num_hypotheses} гипотез в формате JSON-массива.
Схема каждого объекта:
{schema}
"""


def _extract_json_array(text: str) -> list[dict]:
    """Парсит JSON-массив из ответа LLM (с fallback на извлечение из markdown-блока)."""
    text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "hypotheses" in parsed:
            return parsed["hypotheses"]
    except json.JSONDecodeError:
        pass

    fence_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence_match:
        return json.loads(fence_match.group(1))

    array_match = re.search(r"\[.*\]", text, re.DOTALL)
    if array_match:
        return json.loads(array_match.group(0))

    raise ValueError(f"Не удалось распарсить JSON из ответа LLM:\n{text[:500]}")


def _parse_hypothesis(raw: dict) -> Hypothesis:
    sources = raw.get("sources") or []
    if isinstance(sources, str):
        sources = [sources]

    return Hypothesis(
        hypothesis=str(raw.get("hypothesis", "")).strip(),
        mechanism=str(raw.get("mechanism", "")).strip(),
        sources=[str(s) for s in sources],
        novelty_score=float(raw.get("novelty_score", 0)),
        risk_score=float(raw.get("risk_score", 0)),
        expected_value_score=float(raw.get("expected_value_score", 0)),
        reasoning=str(raw.get("reasoning", "")).strip(),
    )


def generate_hypotheses(
    problem: str,
    constraints: str,
    chunks: list[RetrievedChunk],
    *,
    num_hypotheses: int | None = None,
    llm: YandexLLMClient | None = None,
) -> list[Hypothesis]:
    """Вызывает LLM и возвращает список гипотез."""
    if not chunks:
        raise ValueError("Нет контекста для генерации — сначала выполните retrieval")

    client = llm or YandexLLMClient()
    count = num_hypotheses or NUM_HYPOTHESES
    user_prompt = _build_user_prompt(problem, constraints, chunks, count)
    response = client.chat(SYSTEM_PROMPT, user_prompt)

    raw_list = _extract_json_array(response)
    hypotheses = [_parse_hypothesis(item) for item in raw_list if item.get("hypothesis")]
    if not hypotheses:
        raise RuntimeError("LLM не вернул ни одной валидной гипотезы")
    return hypotheses

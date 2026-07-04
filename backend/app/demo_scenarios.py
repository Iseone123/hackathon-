"""Единый конфиг демо-сценариев и папок данных."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoScenario:
    id: str
    name: str
    data_path: str
    problem: str
    constraints: str


DEMO_SCENARIOS: tuple[DemoScenario, ...] = (
    DemoScenario(
        id="kgmk",
        name="КГМК — хвосты обогащения",
        data_path="Пример 1",
        problem=(
            "Повышение извлечения меди из хвостов КГМК "
            "при оптимизации режима флотации"
        ),
        constraints="pH 8-10, без капитальных вложений, существующее оборудование, TRL 4",
    ),
    DemoScenario(
        id="nof",
        name="НОФ — вкраплённая медь",
        data_path="Пример 2",
        problem="Извлечение вкраплённой меди из хвостов НОФ при флотации",
        constraints="Энергозатраты на измельчение ограничены, pH 8-10, TRL 4",
    ),
    DemoScenario(
        id="textbook",
        name="Флотация — учебные материалы",
        data_path="Дополнительные материалы",
        problem=(
            "Оптимизация схемы флотации сульфидных руд "
            "для повышения качества концентрата"
        ),
        constraints="Русскоязычные источники, TRL 4-5",
    ),
)

# Папки для UI индексации (все доступные в data/)
DATA_DIRS: tuple[str, ...] = (
    "Дополнительные материалы",
    "Пример 1",
    "Пример 2",
    "Пример 3",
    "Пример 4",
    "Схемы флотации",
    "Регламенты",
)

# Папки для авто-индексации перед генерацией
AUTO_INGEST_DIRS: tuple[str, ...] = (
    "Дополнительные материалы",
    "Пример 1",
    "Пример 2",
    "Пример 3",
    "Пример 4",
    "Схемы флотации",
)

# CLI: сценарии 1–3 (обратная совместимость)
CLI_SCENARIOS: dict[str, DemoScenario] = {
    "1": DEMO_SCENARIOS[2],  # учебники
    "2": DEMO_SCENARIOS[0],  # КГМК
    "3": DEMO_SCENARIOS[1],  # НОФ
}


def demo_examples_payload() -> list[dict[str, str]]:
    return [
        {
            "id": s.id,
            "name": s.name,
            "data_path": s.data_path,
            "problem": s.problem,
            "constraints": s.constraints,
        }
        for s in DEMO_SCENARIOS
    ]

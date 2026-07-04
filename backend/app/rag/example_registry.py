"""Конфигурация эталонных кейсов из data/examples.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import settings


@dataclass(frozen=True)
class ExampleCase:
    id: str
    dir: str
    label: str
    keywords: tuple[str, ...] = ()
    hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExampleRegistry:
    cases: tuple[ExampleCase, ...]
    broad_keywords: tuple[str, ...] = ()

    @property
    def all_dirs(self) -> list[str]:
        return [c.dir for c in self.cases]

    def match_dirs(self, problem: str, constraints: str = "") -> list[str]:
        text = f"{problem} {constraints}".lower()
        matched: list[str] = []
        seen: set[str] = set()

        for case in self.cases:
            if any(kw in text for kw in case.keywords):
                if case.dir not in seen:
                    seen.add(case.dir)
                    matched.append(case.dir)

        if not matched and any(kw in text for kw in self.broad_keywords):
            for case in self.cases:
                if case.dir not in seen:
                    seen.add(case.dir)
                    matched.append(case.dir)

        return matched

    def hints_for_dirs(self, dirs: list[str]) -> list[str]:
        dir_set = set(dirs)
        hints: list[str] = []
        for case in self.cases:
            if case.dir in dir_set:
                for hint in case.hints:
                    labeled = f"{case.label}: {hint}"
                    if labeled not in hints:
                        hints.append(labeled)
        return hints


def _examples_yaml_path() -> Path:
    configured = settings.data_dir_path / "examples.yaml"
    if configured.is_file():
        return configured
    repo_default = Path(__file__).resolve().parents[3] / "data" / "examples.yaml"
    return repo_default


def _parse_registry(data: dict[str, Any]) -> ExampleRegistry:
    cases: list[ExampleCase] = []
    for item in data.get("examples") or []:
        cases.append(
            ExampleCase(
                id=str(item.get("id", "")),
                dir=str(item.get("dir", "")),
                label=str(item.get("label", item.get("id", ""))),
                keywords=tuple(str(k).lower() for k in (item.get("keywords") or [])),
                hints=tuple(str(h) for h in (item.get("hints") or [])),
            )
        )
    fallback = data.get("fallback") or {}
    broad = tuple(str(k).lower() for k in (fallback.get("broad_keywords") or []))
    return ExampleRegistry(cases=tuple(cases), broad_keywords=broad)


@lru_cache(maxsize=1)
def get_example_registry() -> ExampleRegistry:
    path = _examples_yaml_path()
    if not path.is_file():
        return ExampleRegistry(cases=(), broad_keywords=("хвост", "хвостов"))
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _parse_registry(raw)


def infer_example_dirs(problem: str, constraints: str = "") -> list[str]:
    return get_example_registry().match_dirs(problem, constraints)


def build_example_hints(problem: str, constraints: str, example_dirs: list[str]) -> list[str]:
    registry = get_example_registry()
    hints = registry.hints_for_dirs(example_dirs)
    combined = f"{problem} {constraints}".lower()

    if "без капитальн" in combined:
        hints.append("Только лабораторные/пилотные испытания на существующем оборудовании, TRL 4")
    if "ph 8" in combined or "ph 8-10" in combined.replace(" ", ""):
        hints.append("pH гипотезы строго в диапазоне 8–10")
    if "концентрат" in combined or "сульфид" in combined:
        hints.append("Учебник: схемы селективности; указывай ≥3% как критерий успеха при отсутствии точного %")

    return hints

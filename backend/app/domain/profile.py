"""Универсальные эвристики KPI, параметров и тем — для любой предметной области."""

from __future__ import annotations

import re

# Целевые KPI: RU + EN
_KPI_LABEL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("извлечение / выход", r"извлечени\w+|выход\w+|recovery|yield|extraction"),
    ("прочность", r"прочност\w+|strength|tensile|hardness"),
    ("жаропрочность", r"жаропроч\w+|heat.?resist"),
    ("себестоимость", r"себестоим\w+|cost|opex|capex"),
    ("качество", r"качеств\w+|grade|purity|чистот"),
    ("эффективность", r"эффективн\w+|efficien\w+|performance"),
    ("срок службы", r"срок\s+служб|durability|lifetime|fatigue"),
    ("вязкость / реология", r"вязкост\w+|viscosity|rheolog"),
    ("адгезия / покрытие", r"адгези\w+|покрыти\w+|coating|adhesion"),
    ("проводимость", r"проводим\w+|conductiv"),
    ("плотность / пористость", r"плотност\w+|порист\w+|density|porosity"),
    ("токсичность / экология", r"токсичн\w+|эколог\w+|emission|toxic"),
)

_VALUE_LINK_RE = re.compile(
    r"(извлечени|себестоим|прочност|жаропроч|kpi|эффективн|"
    r"повышени|снижени|оптимизац|результат|целев|улучшени|"
    r"recovery|yield|strength|efficien\w+|quality|performance|cost|"
    r"durability|conductiv|adhesion|viscosity|density)",
    re.IGNORECASE,
)

_TESTABLE_ACTION_RE = re.compile(
    r"(повысит|повышени|снизит|снижени|улучшит|улучшени|"
    r"обеспечит|позволит|увеличит|оптимизир|достигнет|"
    r"изменит|заменит|модернизир|переведёт|переведет|"
    r"increase|decrease|improve|enhance|reduce|optimize|achieve)",
    re.IGNORECASE,
)

_INTERVENTION_RE = re.compile(
    r"(изменени|замен|модерниз|установк|оптимизац|перестрой|"
    r"реконструкц|увеличени|снижени|перевод|переключ|"
    r"повысит|снизит|улучшит|увеличит|добавлени|введени|"
    r"состав|сплав|полимер|композит|реагент|добавк|"
    r"equipment|process|alloy|polymer|composite|additive|"
    r"temperature|pressure|concentration|dosage|режим|mode)",
    re.IGNORECASE,
)

_CONCRETE_PARAM_RE = re.compile(
    r"(геометри|конфигурац|конструкц|диаметр|крупност|зазор|"
    r"частот|скорост|схем|режим|класс|composition|parameter|"
    r"concentration|dosage|temperature|pressure|thickness)",
    re.IGNORECASE,
)


def measurable_param_patterns() -> list[str]:
    """Регулярки измеримых параметров — универсальные единицы и диапазоны."""
    return [
        r"\d+[\.,]?\d*\s*%",
        r"\d+[\.,]?\d*\s*(кг|г|т|мг|л|мл|ppm|ppb|моль|mol)\b",
        r"\d+[\.,]?\d*\s*кг\s*/\s*т",
        r"pH\s*\d",
        r"\d+[\.,]?\d*\s*[-–—]\s*\d+",
        r"\d+[\.,]?\d*\s*(мм|мкм|см|м\b|нм|об/мин|rpm|кВт|МПа|бар|°C|K|В|А|ГПа)\b",
        r"(?:с|от)\s*\d+\s*(?:на|до|to)\s*\d+",
        r"\d+\s*(?:→|->)\s*\d+",
        r"\d+[\.,]?\d*\s*(wt\.?%|vol\.?%|at\.?%)",
        r"(?:≥|<=?|>=?)\s*\d+[\.,]?\d*",
    ]


def process_intervention_patterns() -> tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str]]:
    return _INTERVENTION_RE, _TESTABLE_ACTION_RE, _CONCRETE_PARAM_RE


def testable_action_patterns() -> re.Pattern[str]:
    return _TESTABLE_ACTION_RE


def value_link_patterns() -> re.Pattern[str]:
    return _VALUE_LINK_RE


def infer_kpi_label(problem: str) -> str:
    lowered = (problem or "").lower()
    for label, pat in _KPI_LABEL_PATTERNS:
        if re.search(pat, lowered):
            return label
    words = re.findall(r"[а-яёa-z]{6,}", lowered)
    return words[0] if words else "целевой KPI"


def kpi_markers_from_problem(problem: str) -> list[str]:
    """Ключевые слова KPI из формулировки задачи + универсальные маркеры."""
    words = re.findall(r"[а-яёa-z]{5,}", (problem or "").lower())
    markers = [w for w in words[:10] if len(w) > 5]
    label = infer_kpi_label(problem)
    if label != "целевой KPI":
        markers.append(label.split("/")[0].strip())
    return list(dict.fromkeys(markers))


def generic_kpi_patterns() -> tuple[tuple[re.Pattern[str], str], ...]:
    """Паттерны KPI для таблиц Excel — любая предметная область."""
    return (
        (re.compile(r"yield|выход|recovery|извлечени\w*", re.I), "yield"),
        (re.compile(r"strength|прочност|tensile|hardness", re.I), "strength"),
        (re.compile(r"efficien\w*|эффективн", re.I), "efficiency"),
        (re.compile(r"cost|себестоим|opex|capex", re.I), "cost"),
        (re.compile(r"quality|качеств|grade|purity", re.I), "quality"),
        (re.compile(r"viscosity|вязкост", re.I), "viscosity"),
        (re.compile(r"conductiv|проводим", re.I), "conductivity"),
        (re.compile(r"density|плотност", re.I), "density"),
        (re.compile(r"temperature|температур", re.I), "temperature"),
        (re.compile(r"отвальн\w*\s+хвост", re.I), "tailings"),
        (re.compile(r"итого\s+извлекаем\w*\s+металл", re.I), "recoverable"),
    )


def extract_topic_labels(text: str, *, limit: int = 6) -> list[str]:
    """Темы из текста по частотным техническим терминам (без фиксированного домена)."""
    tokens = re.findall(r"[а-яёa-z]{6,}", (text or "").lower())
    stop = {
        "повышение", "снижение", "оптимизация", "гипотеза", "эксперимент",
        "исследование", "результат", "процесс", "материал", "свойство",
        "improvement", "increase", "decrease", "process", "material",
    }
    freq: dict[str, int] = {}
    for t in tokens:
        if t in stop:
            continue
        freq[t] = freq.get(t, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: (-x[1], -len(x[0])))
    return [w for w, _ in ranked[:limit]]

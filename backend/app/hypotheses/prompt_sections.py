"""Секции промптов генерации — единый источник правил для system/user/refiner."""

from __future__ import annotations

from app.rag.example_registry import build_example_hints, infer_example_dirs

HYPOTHESIS_JSON_SCHEMA = """Respond ONLY with valid JSON matching this schema:
{
  "hypotheses": [
    {
      "text": "hypothesis statement",
      "mechanism": "proposed mechanism",
      "novelty_score": 0-10,
      "feasibility_score": 0-10,
      "expected_value_score": 0-10,
      "risk": {"technical": 0-10, "economic": 0-10},
      "sources": [{"doc_id": "...", "snippet": "...", "url": null}],
      "verification_roadmap": [
        "step 1: experiment with resources (equipment, samples, reagents)",
        "step 2: success criteria (% improvement) and failure criteria"
      ],
      "reasoning": "justification with explicit references to sources",
      "influence_graph": {
        "nodes": [
          {"id": "reagent_or_equipment", "type": "Material", "source_doc_id": "exact doc_id"},
          {"id": "process", "type": "Process", "source_doc_id": "exact doc_id"},
          {"id": "target KPI", "type": "Property", "source_doc_id": "exact doc_id"}
        ],
        "links": [
          {"source": "reagent_or_equipment", "target": "process", "type": "MODIFIES"},
          {"source": "process", "target": "target KPI", "type": "AFFECTS"}
        ],
        "states": [
          {"id": "лабораторная фаза", "type": "State", "phase_order": 1, "description": "..."}
        ],
        "transitions": [
          {"from": "лабораторная фаза", "to": "пилотная фаза", "type": "NEXT_PHASE", "condition": "≥3% vs control"}
        ]
      }
    }
  ]
}"""

CITATION_RULES = """CRITICAL — source citations (automated judge rejects violations):
1. sources[].doc_id MUST be copied exactly from "doc_id=..." in the context.
2. sources[].snippet MUST be a contiguous COPY-PASTE from that chunk — NOT a paraphrase.
   - Keep snippet in the ORIGINAL language of the chunk (Russian, English, Chinese, etc.).
   - The snippet MUST mention the same key fact as the hypothesis (reagent, dosage, process, KPI).
   - Pick 1–3 sentences (60–250 chars) that DIRECTLY prove the claim.
3. text, mechanism, reasoning, verification_roadmap — ALWAYS in Russian (see OUTPUT LANGUAGE).
   - Extract knowledge from foreign-language snippets and EXPRESS it in Russian with correct units (кг/т, pH, ≥3%).
   - reasoning MUST explain how the Russian hypothesis follows from the snippet (translate the key fact).
4. Do NOT cite reagents, brands or methods NOT present in the snippet (no Finfix, no invented dosages).
5. Do NOT invent quantitative effects unless the snippet states them.
   - Use "повысит извлечение на ≥3% относительно контроля" as test target if snippet lacks exact %."""

FORMULATION_RULES = """CRITICAL — formulation (judge checklist):
- text MUST contain measurable params: dosage (кг/т), pH, equipment/process name, or expected effect (≥3%).
- FORBIDDEN in text/mechanism: "может", "возможно", "предположительно" without numbers.
- Use confident testable form: "Добавление X кг/т ... повысит извлечение на ≥3% при pH 8-10".
- pH in hypothesis MUST stay within the Constraints range (if pH 8-10 required, do NOT use pH 7 or 12).
- Obey ALL constraints: no capital investments, TRL 4 = lab tests on existing equipment only.
- Do NOT propose: new plants, contact tanks, mill relining, crushers — unless snippet supports AND constraints allow."""

SOURCE_STRATEGY = """CRITICAL — two types of sources in context:
- Blocks tagged [ПРИМЕР] or starting with «# KPI-сводка»: enterprise materials (brainstorm, Excel KPIs).
  Use for equipment/process directions — snippet from the SAME block.
- Blocks without tag: textbooks/regulations — reagent dosages, mechanisms.

Diversity (when [ПРИМЕР] / KPI blocks exist):
- Hypothesis 1: grounded in [ПРИМЕР] or KPI-сводка (cite doc_id from that block).
- Hypothesis 2: reagent/process from technical source (different doc_id).
- Hypothesis 3: third distinct mechanism, different doc_id when possible."""

SCORING_GUIDE = """Scores: novelty=higher is more novel, feasibility=higher is easier to test,
expected_value=higher is more valuable, risk=higher is riskier.

MANDATORY per hypothesis:
- Specific testable text with numbers (кг/т, pH, or ≥3%)
- reasoning>=80 chars: link hypothesis to snippet (translate EN/CN facts into Russian)
- mechanism linked to snippet and target KPI
- risk.technical and risk.economic (not default 5/5)
- >=2 roadmap steps: resources + success ≥3% vs control + failure criteria
- influence_graph: ≥3 nodes (intervention + process + KPI Property), ≥2 links, source_doc_id on nodes"""

INFLUENCE_GRAPH_RULES = """CRITICAL — influence_graph (causal + verification state machine):
- nodes MUST include: intervention (Material/Parameter/equipment), Process, target KPI (Property).
- For equipment hypotheses (mills, hydrocyclones, screens): add equipment as Material node linked via MODIFIES.
- Every node MUST have source_doc_id copied from sources[].doc_id.
- links: intervention → process (USED_IN/MODIFIES), process → KPI (AFFECTS).
- states/transitions: mirror verification_roadmap phases (lab → pilot → industrial); use NEXT_PHASE transitions.
- Do NOT leave influence_graph empty — judge validates graph completeness."""

GOOD_EXAMPLE_REAGENT = """GOOD example — reagent from technical source (approved by judge):
{
  "text": "Добавление 0,3–0,5 кг/т депрессора пустой породы при флотации хвостов при pH 8–10 повысит извлечение целевого металла на ≥3% относительно контроля",
  "mechanism": "Депрессор адсорбируется на пустой породе и снижает её флотационную активность, повышая селективность",
  "sources": [{"doc_id": "textbook_doc_abc123", "snippet": "применение депрессора пустой породы в количестве 0,3—0,5 кг/т при pH 8–10"}],
  "reasoning": "Источник прямо указывает дозировку 0,3—0,5 кг/т; перенос на хвосты задачи обоснован snippet"
}"""

GOOD_EXAMPLE_ENTERPRISE = """GOOD example — enterprise / KPI block from [ПРИМЕР] (approved pattern):
{
  "text": "Пилотная магнитная сепарация над целевым классом крупности хвостов с контролем извлечения даст прирост ≥3% относительно базовой схемы при TRL 4",
  "mechanism": "Выделение слабомагнитной пустой породы до флотации снижает нагрузку на реагенты и повышает селективность",
  "sources": [{"doc_id": "Hypotheses_brainstorm_def456", "snippet": "Магнитная сепарация над целевого класса с последующим доизмельчением в отдельном цикле"}],
  "reasoning": "Материалы [ПРИМЕР] фиксируют направление; пилот на существующем оборудовании проверит прирост ≥3%"
}"""

BAD_EXAMPLE = """BAD example — WILL BE REJECTED (do NOT do this):
{
  "text": "Finfix может улучшить флотацию при pH 7",
  "sources": [{"doc_id": "geokniga-...", "snippet": "флотация медных руд с использованием различных реагентов"}],
  "why_rejected": "Finfix absent from snippet; snippet is vague paraphrase; pH 7 violates constraint pH 8-10; «может» without numbers"
}"""

CITATION_RULES_SHORT = (
    "CITATION: doc_id exact copy; snippet verbatim from chunk (original language OK); "
    "hypothesis fields in Russian — translate knowledge from EN/CN snippets; no invented reagents/%."
)

FORMULATION_RULES_SHORT = (
    "FORMULATION: кг/т or pH or ≥3% in text; no «может»; pH within Constraints; "
    "TRL 4 = lab on existing equipment; 2+ roadmap steps."
)

ROLE_PREAMBLE = """You are a senior R&D scientist in materials science and metallurgy.
Generate testable research hypotheses strictly grounded in the provided RAG context.

MULTILINGUAL INPUT → RUSSIAN OUTPUT:
- Context may be in Russian, English, Chinese, or other languages — read ALL of it.
- Extract facts, dosages, mechanisms, and KPIs from every language.
- Write hypothesis text, mechanism, reasoning, and roadmap ONLY in Russian.
- sources[].snippet stays verbatim in the source language (for automated grounding check).
- In reasoning, translate the snippet's key fact into Russian and link it to the hypothesis."""

GOOD_EXAMPLE_FOREIGN = """GOOD example — English source, Russian hypothesis (approved pattern):
{
  "text": "Добавление 0,2–0,4 кг/т ксантогената при pH 9–10 повысит извлечение меди на ≥3% относительно контроля",
  "mechanism": "Ксантогенат повышает селективность сорбции на сульфидных минералах меди",
  "sources": [{"doc_id": "textbook_en_xyz", "snippet": "xanthate collector dosage 0.2–0.4 kg/t at pH 9–10 improves copper recovery"}],
  "reasoning": "Источник (EN) указывает дозировку xanthate 0,2–0,4 kg/t при pH 9–10 для copper recovery; перенос на задачу хвостов обоснован этой цитатой"
}"""

def build_language_rule(language: str = "ru") -> str:
    """Язык вывода гипотез (API param language). По умолчанию — русский."""
    lang = (language or "ru").lower().strip()
    if lang.startswith("en"):
        return (
            "OUTPUT LANGUAGE: English — write text, mechanism, reasoning, "
            "verification_roadmap and influence_graph node labels in English.\n"
            "Generate exactly 3 diverse hypotheses, each with a different doc_id when possible."
        )
    return (
        "OUTPUT LANGUAGE: Russian (русский).\n"
        "- text, mechanism, reasoning, verification_roadmap, influence_graph labels — ONLY Russian.\n"
        "- If a source chunk is in English/Chinese/other: READ it, EXTRACT the fact, TRANSLATE into Russian.\n"
        "- sources[].snippet — verbatim from chunk (original language); do NOT translate the snippet.\n"
        "Generate exactly 3 diverse hypotheses, each with a different doc_id when possible."
    )


def build_case_hints(problem: str, constraints: str) -> str:
    """Ориентиры по кейсу из data/examples.yaml + универсальные ограничения."""
    dirs = infer_example_dirs(problem, constraints)
    hints = build_example_hints(problem, constraints, dirs)
    if not hints:
        return ""
    return "\nCase hints (ground every claim in snippet):\n" + "\n".join(f"- {h}" for h in hints)


def build_source_strategy_hint(example_dirs: list[str], chunks: list[dict]) -> str:
    """Краткая стратегия источников для user prompt."""
    has_example = bool(example_dirs) and any(
        c.get("from_example")
        or any(d in (c.get("source") or "") for d in example_dirs)
        for c in chunks
    )
    if not has_example:
        return ""
    dirs = ", ".join(example_dirs)
    return (
        f"\nSource strategy: blocks [ПРИМЕР] from {dirs} are mandatory for hypothesis 1. "
        "Hypotheses 2–3 — technical sources (reagents, flotation)."
    )


def build_generation_system(language: str = "ru") -> str:
    """Полный system prompt для генерации."""
    sections = [
        ROLE_PREAMBLE,
        HYPOTHESIS_JSON_SCHEMA,
        CITATION_RULES,
        FORMULATION_RULES,
        SOURCE_STRATEGY,
        INFLUENCE_GRAPH_RULES,
        GOOD_EXAMPLE_REAGENT,
        GOOD_EXAMPLE_ENTERPRISE,
        GOOD_EXAMPLE_FOREIGN,
        BAD_EXAMPLE,
        SCORING_GUIDE,
        build_language_rule(language),
    ]
    return "\n\n".join(sections)


def build_generation_user_footer() -> str:
    """Короткое напоминание правил в user prompt (без дублирования всего system)."""
    return (
        "Generate exactly 3 diverse testable hypotheses grounded in the sources above.\n"
        "Foreign-language sources: extract knowledge → express hypothesis in Russian; snippet verbatim.\n\n"
        f"{CITATION_RULES_SHORT}\n"
        f"{FORMULATION_RULES_SHORT}\n"
        "- If [ПРИМЕР] or KPI-сводка blocks exist: hypothesis 1 MUST cite that doc_id."
    )

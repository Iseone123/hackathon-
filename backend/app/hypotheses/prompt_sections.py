"""Секции промптов генерации — единый источник правил для system/user/refiner."""

from __future__ import annotations

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
        "nodes": [{"id": "material", "type": "Material"}],
        "links": [{"source": "material", "target": "property", "type": "AFFECTS"}]
      }
    }
  ]
}"""

CITATION_RULES = """CRITICAL — source citations (automated judge rejects violations):
1. sources[].doc_id MUST be copied exactly from "doc_id=..." in the context.
2. sources[].snippet MUST be a contiguous COPY-PASTE from that chunk — NOT a paraphrase.
   - The snippet MUST mention the same key term as the hypothesis (reagent, equipment, or process).
   - Pick 1–3 sentences (60–250 chars) that DIRECTLY prove the claim.
3. Do NOT cite reagents, brands or methods NOT present in the snippet (no Finfix, no invented dosages).
4. Do NOT invent quantitative effects unless the snippet states them.
   - Use "повысит извлечение на ≥3% относительно контроля" as test target if snippet lacks exact %.
5. reasoning MUST quote key terms FROM THE SNIPPET (not from general knowledge)."""

FORMULATION_RULES = """CRITICAL — formulation (judge checklist):
- text MUST contain measurable params: dosage (кг/т), pH, equipment/process name, or expected effect (≥3%).
- FORBIDDEN in text/mechanism: "может", "возможно", "предположительно" without numbers.
- Use confident testable form: "Добавление X кг/т ... повысит извлечение на ≥3% при pH 8-10".
- pH in hypothesis MUST stay within the Constraints range (if pH 8-10 required, do NOT use pH 7 or 12).
- Obey ALL constraints: no capital investments, TRL 4 = lab tests on existing equipment only.
- Do NOT propose: new plants, contact tanks, mill relining, crushers — unless snippet supports AND constraints allow."""

SOURCE_STRATEGY = """CRITICAL — two types of sources in context:
- Blocks tagged [ПРИМЕР]: enterprise materials (brainstorm hypotheses, Excel KPIs: % recoverable metal, grain classes).
  Use for process/equipment directions (магнитная сепарация, гидроциклоны, мельницы) — snippet from the SAME [ПРИМЕР] block.
- Blocks without tag: textbooks/regulations — use for reagent dosages, flotation mechanisms (КМЦ, сернистый натрий).

Diversity (mandatory when [ПРИМЕР] blocks exist):
- Hypothesis 1: grounded in a [ПРИМЕР] block (enterprise direction or KPI from Excel).
- Hypothesis 2: reagent/process from technical source (different doc_id).
- Hypothesis 3: third distinct mechanism, different doc_id when possible."""

SCORING_GUIDE = """Scores: novelty=higher is more novel, feasibility=higher is easier to test,
expected_value=higher is more valuable, risk=higher is riskier.

MANDATORY per hypothesis:
- Specific testable text with numbers (кг/т, pH, or ≥3%)
- reasoning>=80 chars quoting snippet terms
- mechanism linked to snippet and target KPI
- risk.technical and risk.economic (not default 5/5)
- >=2 roadmap steps: resources + success ≥3% vs control + failure criteria"""

GOOD_EXAMPLE_REAGENT = """GOOD example — reagent from textbook (approved by judge):
{
  "text": "Добавление 0,3–0,5 кг/т карбоксиметилцеллюлозы (КМЦ) при флотации хвостов КГМК при pH 8–10 повысит извлечение меди на ≥3% относительно контроля за счёт подавления минералов пустой породы",
  "mechanism": "КМЦ адсорбируется на пустой породе и снижает её флотационную активность, повышая селективность извлечения медных сульфидов",
  "sources": [{"doc_id": "geokniga-..._430aba7afb85", "snippet": "применение для подавления минералов пустой породы карбоксиметилцеллюлоза (КМЦ) в количестве 0,3—0,5 кг/т"}],
  "reasoning": "Источник прямо указывает дозировку КМЦ 0,3—0,5 кг/т для подавления пустой породы при флотации медно-никелевых руд; аналогия применима к хвостам КГМК"
}"""

GOOD_EXAMPLE_ENTERPRISE = """GOOD example — enterprise direction from [ПРИМЕР] (approved pattern):
{
  "text": "Пилотная магнитная сепарация над целевым классом крупности хвостов КГМК с контролем извлечения меди даст прирост ≥3% относительно базовой схемы при TRL 4",
  "mechanism": "Выделение слабомагнитной пустой породы до флотации снижает нагрузку на реагенты и повышает селективность извлечения меди",
  "sources": [{"doc_id": "Гипотезы КГМК_e73812eff805", "snippet": "Магнитная сепарация над целевого класса с последующим доизмельчением в отдельном цикле"}],
  "reasoning": "Материалы предприятия фиксируют направление магнитной сепарации над целевым классом; пилот на существующем оборудовании проверит прирост извлечения ≥3%"
}"""

BAD_EXAMPLE = """BAD example — WILL BE REJECTED (do NOT do this):
{
  "text": "Finfix может улучшить флотацию при pH 7",
  "sources": [{"doc_id": "geokniga-...", "snippet": "флотация медных руд с использованием различных реагентов"}],
  "why_rejected": "Finfix absent from snippet; snippet is vague paraphrase; pH 7 violates constraint pH 8-10; «может» without numbers"
}"""

CITATION_RULES_SHORT = (
    "CITATION: doc_id exact copy; snippet word-for-word from that chunk; "
    "same key term in hypothesis and snippet; no invented reagents/%."
)

FORMULATION_RULES_SHORT = (
    "FORMULATION: кг/т or pH or ≥3% in text; no «может»; pH within Constraints; "
    "TRL 4 = lab on existing equipment; 2+ roadmap steps."
)

ROLE_PREAMBLE = """You are a senior R&D scientist in materials science and metallurgy.
Generate testable research hypotheses strictly grounded in the provided RAG context.
Context sources may be in Russian, English, Chinese, or other languages — read and use them as-is."""

LANGUAGE_RULE = (
    "Use Russian if the problem is in Russian, English otherwise.\n"
    "Generate exactly 3 diverse hypotheses, each with a different doc_id when possible."
)


def build_case_hints(problem: str, constraints: str) -> str:
    """Ориентиры по кейсу — согласованы с infer_example_dirs и двумя типами источников."""
    hints: list[str] = []
    combined = f"{problem} {constraints}".lower()

    if "кгмк" in combined or ("хвост" in combined and "ноф" not in combined and "тоф" not in combined):
        hints.append(
            "КГМК [ПРИМЕР]: направления мозгового штурма (магнитная сепарация, мельницы, "
            "гидроциклоны) + KPI из Excel (%, классы крупности); цитата из того же [ПРИМЕР]-блока"
        )
        hints.append(
            "КГМК учебник: КМЦ 0,3–0,5 кг/т, pH 8–10 — только если snippet содержит КМЦ"
        )
    if "ноф" in combined or "вкрапл" in combined:
        hints.append(
            "НОФ [ПРИМЕР]: вкраплённая медь, сернистый натрий; "
            "не предлагай дробилки/измельчение — ограничены энергозатраты"
        )
    if "тоф" in combined:
        hints.append("ТОФ [ПРИМЕР]: классификация и флотация; cite Excel KPIs when present")
    if "концентрат" in combined or ("сульфид" in combined and "кгмк" not in combined):
        hints.append(
            "Учебник: схемы флотации, селективность; указывай ≥3% как критерий успеха"
        )
    if "без капитальн" in combined:
        hints.append("Только лабораторные/пилотные испытания на существующем оборудовании, TRL 4")
    if "ph 8" in combined:
        hints.append("pH гипотезы строго в диапазоне 8–10")

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


def build_generation_system() -> str:
    """Полный system prompt для генерации."""
    sections = [
        ROLE_PREAMBLE,
        HYPOTHESIS_JSON_SCHEMA,
        CITATION_RULES,
        FORMULATION_RULES,
        SOURCE_STRATEGY,
        GOOD_EXAMPLE_REAGENT,
        GOOD_EXAMPLE_ENTERPRISE,
        BAD_EXAMPLE,
        SCORING_GUIDE,
        LANGUAGE_RULE,
    ]
    return "\n\n".join(sections)


def build_generation_user_footer() -> str:
    """Короткое напоминание правил в user prompt (без дублирования всего system)."""
    return (
        "Generate exactly 3 diverse testable hypotheses grounded in the sources above.\n\n"
        f"{CITATION_RULES_SHORT}\n"
        f"{FORMULATION_RULES_SHORT}\n"
        "- If [ПРИМЕР] blocks exist: hypothesis 1 MUST cite a [ПРИМЕР] doc_id."
    )

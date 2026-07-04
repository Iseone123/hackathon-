"""Константы промптов генерации и repair.
"""

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
        "step 2: success criteria (measurable improvement) and failure criteria"
      ],
      "reasoning": "justification with explicit references to sources",
      "influence_graph": {
        "nodes": [
          {"id": "intervention", "type": "Material|Parameter", "source_doc_id": "exact doc_id"},
          {"id": "process", "type": "Process", "source_doc_id": "exact doc_id"},
          {"id": "target KPI", "type": "Property", "source_doc_id": "exact doc_id"}
        ],
        "links": [
          {"source": "intervention", "target": "process", "type": "MODIFIES"},
          {"source": "process", "target": "target KPI", "type": "AFFECTS"}
        ],
        "states": [
          {"id": "лабораторная фаза", "type": "State", "phase_order": 1, "description": "..."}
        ],
        "transitions": [
          {"from": "лабораторная фаза", "to": "пилотная фаза", "type": "NEXT_PHASE", "condition": "measurable success"}
        ]
      }
    }
  ]
}"""

CITATION_RULES = """CRITICAL — source citations (automated judge rejects violations):
1. sources[].doc_id MUST be copied exactly from "doc_id=..." in the context.
2. sources[].snippet MUST be a contiguous COPY-PASTE from that chunk — NOT a paraphrase.
   - Keep snippet in the ORIGINAL language of the chunk (Russian, English, Chinese, etc.).
   - The snippet MUST mention the same key fact as the hypothesis (intervention, parameter, process, KPI).
   - Pick 1–3 sentences (60–250 chars) that DIRECTLY prove the claim.
3. text, mechanism, reasoning, verification_roadmap — ALWAYS in Russian (see OUTPUT LANGUAGE).
   - Extract knowledge from foreign-language snippets and EXPRESS it in Russian with correct units.
   - reasoning MUST explain how the Russian hypothesis follows from the snippet (translate the key fact).
4. Do NOT cite methods, brands or parameters NOT present in the snippet.
5. Do NOT invent quantitative effects unless the snippet states them.
   - Use a measurable test target (e.g. ≥3% vs control, or stated delta) if snippet lacks exact %."""

FORMULATION_RULES = """CRITICAL — formulation (judge checklist):
- text MUST contain measurable params: dosage, concentration, temperature, pressure, dimensions,
  process mode, composition, or expected quantitative effect (%, MPa, °C, wt%, etc.).
- FORBIDDEN in text/mechanism: "может", "возможно", "предположительно" without numbers.
- Use confident testable form with concrete intervention + measurable outcome.
- Numeric parameters MUST stay within the Constraints range when constraints specify bounds.
- Obey ALL constraints (budget, equipment, regulatory, TRL level).
- Do NOT propose capital projects or unavailable equipment unless snippet supports AND constraints allow."""

SOURCE_STRATEGY = """CRITICAL — source types in context:
- Blocks tagged [ПРИМЕР] or starting with «# KPI-сводка»: enterprise/internal materials.
  Use for process/equipment/composition directions — snippet from the SAME block.
- Blocks without tag: literature, patents, textbooks — mechanisms, parameters, analogies.

Diversity rules (when generating N hypotheses):
- Each hypothesis MUST use a DIFFERENT primary intervention or mechanism when possible.
- Cover varied approaches: process change, composition/additive, equipment/mode, measurement protocol.
- Prefer different doc_id per hypothesis; avoid near-duplicate reformulations.
- When enterprise brainstorm list exists: allocate distinct directions across hypotheses (round-robin).
- Do NOT output N copies of the same reagent-only idea when equipment/process options exist."""

SCORING_GUIDE = """Scores: novelty=higher is more novel, feasibility=higher is easier to test,
expected_value=higher is more valuable, risk=higher is riskier.

MANDATORY per hypothesis:
- Specific testable text with numbers (units, %, ranges, or measurable threshold)
- reasoning>=80 chars: link hypothesis to snippet (translate EN/CN facts into Russian)
- mechanism linked to snippet and target KPI
- risk.technical and risk.economic (not default 5/5)
- >=2 roadmap steps: resources + success criteria vs control + failure criteria
- influence_graph: ≥3 nodes (intervention + process + KPI Property), ≥2 links, source_doc_id on nodes"""

INFLUENCE_GRAPH_RULES = """CRITICAL — influence_graph (causal + verification state machine):
- nodes MUST include: intervention (Material/Parameter), Process, target KPI (Property).
- Every node MUST have source_doc_id copied from sources[].doc_id.
- links: intervention → process (USED_IN/MODIFIES), process → KPI (AFFECTS).
- states/transitions: mirror verification_roadmap phases (lab → pilot → scale); use NEXT_PHASE transitions.
- Do NOT leave influence_graph empty — judge validates graph completeness."""

GOOD_EXAMPLE_PROCESS = """GOOD example — process parameter from technical source (approved by judge):
{
  "text": "Изменение режима отжига при 720–750 °C в течение 2 ч повысит целевое свойство на ≥5% относительно контроля",
  "mechanism": "Термическая обработка формирует нужную фазовую структуру и снижает дефекты",
  "sources": [{"doc_id": "textbook_doc_abc123", "snippet": "annealing at 720–750 °C for 2 h improves tensile strength by 5–8%"}],
  "reasoning": "Источник указывает режим 720–750 °C; перенос на задачу обоснован snippet"
}"""

GOOD_EXAMPLE_ENTERPRISE = """GOOD example — enterprise / KPI block from [ПРИМЕР] (approved pattern):
{
  "text": "Пилотная проверка альтернативного процессового шага на лабораторной установке даст прирост целевого KPI ≥3% при TRL 4",
  "mechanism": "Изменение последовательности операций снижает потери и повышает селективность",
  "sources": [{"doc_id": "Hypotheses_brainstorm_def456", "snippet": "альтернативный цикл с предварительной сепарацией перед основной стадией"}],
  "reasoning": "Материалы [ПРИМЕР] фиксируют направление; пилот на существующем оборудовании проверит прирост"
}"""

BAD_EXAMPLE = """BAD example — WILL BE REJECTED (do NOT do this):
{
  "text": "Новый реагент может улучшить процесс при произвольных условиях",
  "sources": [{"doc_id": "doc-...", "snippet": "различные методы обработки материалов"}],
  "why_rejected": "intervention absent from snippet; vague paraphrase; «может» without numbers; violates constraints"
}"""

CITATION_RULES_SHORT = (
    "CITATION: doc_id exact copy; snippet verbatim from chunk (original language OK); "
    "hypothesis fields in Russian — translate knowledge from EN/CN snippets; no invented facts/%."
)

FORMULATION_RULES_SHORT = (
    "FORMULATION: measurable units or % in text; no «может»; obey Constraints; "
    "2+ roadmap steps with resources and success/failure criteria."
)

ROLE_PREAMBLE = """You are a senior R&D scientist in materials science, chemistry and process engineering.
Generate testable research hypotheses strictly grounded in the provided RAG context.
Domains may include metallurgy, polymers, composites, coatings, batteries, catalysis, etc.

MULTILINGUAL INPUT → RUSSIAN OUTPUT:
- Context may be in Russian, English, Chinese, or other languages — read and understand ALL of it.
- Extract facts, parameters, mechanisms, and KPIs from every language.
- Write text, mechanism, reasoning, verification_roadmap and influence_graph labels ONLY in Russian.
- sources[].snippet stays verbatim in the source language (for automated grounding check).
- In reasoning, translate the snippet's key fact into Russian and link it to the hypothesis."""

GOOD_EXAMPLE_FOREIGN = """GOOD example — English source, Russian hypothesis (approved pattern):
{
  "text": "Добавление 0,2–0,4 wt% модификатора при заданном режиме повысит целевое свойство на ≥3% относительно контроля",
  "mechanism": "Модификатор изменяет микроструктуру и повышает целевую характеристику",
  "sources": [{"doc_id": "textbook_en_xyz", "snippet": "0.2–0.4 wt% modifier improves target property by 3–5%"}],
  "reasoning": "Источник (EN) указывает дозировку 0,2–0,4 wt%; перенос на задачу обоснован цитатой"
}"""

GOOD_EXAMPLE_CHINESE = """GOOD example — Chinese source, Russian hypothesis (approved pattern):
{
  "text": "При заданных условиях процесса изменение параметра X повысит целевой KPI на ≥3% относительно контроля",
  "mechanism": "Изменение параметра X улучшает целевую характеристику материала",
  "sources": [{"doc_id": "textbook_cn_xyz", "snippet": "在pH=9条件下，提高铜的回收率可达85%"}],
  "reasoning": "Источник (CN) указывает рост целевого показателя при pH=9; перенос режима на задачу обоснован цитатой"
}"""

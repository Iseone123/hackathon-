"""Визуальный конструктор дорожной карты верификации."""

from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from hypothesis_api import fetch_roadmap_templates, update_roadmap
from roadmap_viz import render_roadmap_timeline_html


def _steps_from_hypothesis(h: dict[str, Any]) -> list[dict[str, Any]]:
    sr = h.get("structured_roadmap") or []
    if sr:
        return [dict(s) for s in sr]
    texts = h.get("verification_roadmap") or []
    rows = []
    for i, t in enumerate(texts, 1):
        rows.append(
            {
                "step_order": i,
                "title": str(t)[:80],
                "description": str(t),
                "duration_days": 7 if i == 1 else 14,
                "resources": ["пробы 1 кг", "лабораторное оборудование"],
                "success_criteria": "Улучшение KPI ≥3% vs контроль",
                "failure_criteria": "Нет значимого эффекта vs контроль",
                "depends_on": [i - 1] if i > 1 else [],
            }
        )
    return rows


def _timeline_from_steps(steps: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    timeline: list[dict[str, Any]] = []
    cursor = 0
    for s in sorted(steps, key=lambda x: int(x.get("step_order", 0))):
        dur = int(s.get("duration_days", 7))
        timeline.append(
            {
                "step": s.get("step_order"),
                "title": str(s.get("title", ""))[:40],
                "start_day": cursor,
                "duration_days": dur,
                "end_day": cursor + dur,
                "resources": ", ".join(s.get("resources") or [])[:60],
            }
        )
        cursor += dur
    return timeline, cursor


def _estimate_cost(steps: list[dict[str, Any]]) -> int:
    total = 0
    for s in steps:
        dur = int(s.get("duration_days", 7))
        n_res = len(s.get("resources") or [])
        total += 15_000 * max(1, dur // 7) + 8_000 * n_res
    return total


def render_roadmap_constructor(h: dict[str, Any], *, on_saved: Callable[[dict], None] | None = None) -> None:
    """Интерактивный конструктор: шаблоны, порядок, сроки, зависимости, сводка."""
    hid = h["id"]
    session_key = f"roadmap_steps_{hid}"

    if session_key not in st.session_state:
        st.session_state[session_key] = _steps_from_hypothesis(h)

    steps: list[dict[str, Any]] = st.session_state[session_key]
    timeline, total_days = _timeline_from_steps(steps)
    total_cost = _estimate_cost(steps)

    st.markdown("**Конструктор дорожной карты**")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Срок", f"{total_days} дн.")
    m2.metric("Шагов", len(steps))
    m3.metric("Бюджет (оценка)", f"{total_cost:,} ₽".replace(",", " "))
    m4.metric("Ресурсов", len({r for s in steps for r in (s.get("resources") or [])}))

    html = render_roadmap_timeline_html(timeline, total_days)
    if html:
        st.components.v1.html(html, height=160 + 40 * max(len(timeline), 1), scrolling=False)

    templates = fetch_roadmap_templates()
    tpl_labels = {t["label"]: t["id"] for t in templates}
    c_tpl, c_add = st.columns([3, 1])
    with c_tpl:
        picked = st.selectbox(
            "Шаблон шага",
            options=["—"] + list(tpl_labels.keys()),
            key=f"tpl_{hid}",
        )
    with c_add:
        if st.button("Добавить из шаблона", key=f"add_tpl_{hid}"):
            if picked and picked != "—":
                tpl = next(t for t in templates if t["id"] == tpl_labels[picked])
                new_order = len(steps) + 1
                steps.append(
                    {
                        "step_order": new_order,
                        "title": tpl.get("label", tpl["id"]),
                        "description": tpl.get("label", ""),
                        "duration_days": tpl.get("duration_days", 7),
                        "resources": list(tpl.get("resources") or []),
                        "success_criteria": "Улучшение KPI ≥3% vs контроль",
                        "failure_criteria": "Нет значимого эффекта vs контроль",
                        "depends_on": [new_order - 1] if new_order > 1 else [],
                    }
                )
                st.session_state[session_key] = steps
                st.rerun()

    for i, step in enumerate(steps):
        order = int(step.get("step_order", i + 1))
        with st.expander(f"Шаг {order}: {step.get('title', '')[:50]}", expanded=i == 0):
            step["title"] = st.text_input("Название", step.get("title", ""), key=f"rt_{hid}_{order}_title")
            step["duration_days"] = st.slider(
                "Длительность (дн.)",
                1,
                90,
                int(step.get("duration_days", 7)),
                key=f"rt_{hid}_{order}_dur",
            )
            step["resources"] = [
                r.strip()
                for r in st.text_input(
                    "Ресурсы (через запятую)",
                    ", ".join(step.get("resources") or []),
                    key=f"rt_{hid}_{order}_res",
                ).split(",")
                if r.strip()
            ]
            step["success_criteria"] = st.text_input(
                "Критерий успеха",
                step.get("success_criteria", ""),
                key=f"rt_{hid}_{order}_ok",
            )
            step["failure_criteria"] = st.text_input(
                "Критерий провала",
                step.get("failure_criteria", ""),
                key=f"rt_{hid}_{order}_fail",
            )
            dep_opts = [s.get("step_order") for s in steps if s.get("step_order") != order]
            step["depends_on"] = st.multiselect(
                "Зависит от шагов",
                options=dep_opts,
                default=[d for d in (step.get("depends_on") or []) if d in dep_opts],
                key=f"rt_{hid}_{order}_dep",
            )

            mv1, mv2, mv3 = st.columns(3)
            if mv1.button("↑ Вверх", key=f"up_{hid}_{order}", disabled=i == 0):
                steps[i], steps[i - 1] = steps[i - 1], steps[i]
                for j, s in enumerate(steps, 1):
                    s["step_order"] = j
                st.session_state[session_key] = steps
                st.rerun()
            if mv2.button("↓ Вниз", key=f"down_{hid}_{order}", disabled=i >= len(steps) - 1):
                steps[i], steps[i + 1] = steps[i + 1], steps[i]
                for j, s in enumerate(steps, 1):
                    s["step_order"] = j
                st.session_state[session_key] = steps
                st.rerun()
            if mv3.button("Удалить", key=f"del_{hid}_{order}"):
                steps.pop(i)
                for j, s in enumerate(steps, 1):
                    s["step_order"] = j
                st.session_state[session_key] = steps
                st.rerun()

    st.session_state[session_key] = steps

    if st.button("Сохранить roadmap", key=f"save_roadmap_{hid}", type="primary"):
        payload = []
        for s in steps:
            payload.append(
                {
                    "step_order": int(s.get("step_order", 1)),
                    "title": str(s.get("title", "")),
                    "description": str(s.get("description") or s.get("title", "")),
                    "duration_days": int(s.get("duration_days", 7)),
                    "resources": list(s.get("resources") or []),
                    "success_criteria": str(s.get("success_criteria", "")),
                    "failure_criteria": str(s.get("failure_criteria", "")),
                    "depends_on": [int(d) for d in (s.get("depends_on") or [])],
                }
            )
        try:
            updated = update_roadmap(hid, payload)
            st.session_state[session_key] = _steps_from_hypothesis(updated)
            if on_saved:
                on_saved(updated)
            st.success("Roadmap сохранён")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

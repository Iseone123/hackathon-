"""Вкладка генерации гипотез."""

from __future__ import annotations

import streamlit as st

from hypothesis_api import generate


def render_tab_generate() -> None:
    st.subheader("Генерация гипотез")

    problem = st.text_area(
        "Целевая проблема",
        value=st.session_state.problem,
        height=100,
        placeholder="Повышение извлечения меди из хвостов при флотации…",
        help="Только задача и KPI. Ограничения (pH, бюджет, TRL) — в поле ниже.",
    )
    constraints = st.text_area(
        "Ограничения",
        value=st.session_state.constraints,
        height=80,
        placeholder="pH 8-10, без капитальных вложений, TRL 4-5…",
        help="pH, CAPEX, TRL, оборудование.",
    )

    auto_ingest = st.checkbox(
        "Авто-индексация перед генерацией (только новые файлы)",
        value=True,
        help="Если в базе нет данных — автоматически проиндексирует основные папки",
    )

    with st.expander("Веса ранжирования (экспертная настройка)"):
        c1, c2, c3, c4 = st.columns(4)
        w_novelty = c1.slider("Новизна", 0.0, 1.0, 0.30, 0.05)
        w_feasibility = c2.slider("Реализуемость", 0.0, 1.0, 0.25, 0.05)
        w_value = c3.slider("Ценность", 0.0, 1.0, 0.30, 0.05)
        w_risk = c4.slider("Риск (инверс.)", 0.0, 1.0, 0.15, 0.05)
        total = w_novelty + w_feasibility + w_value + w_risk
        if abs(total - 1.0) > 0.01:
            st.warning(f"Сумма весов = {total:.2f}, нормализуйте до 1.0")
        use_custom_weights = st.checkbox("Использовать свои веса", value=False)

    top_k = st.slider("Top-K фрагментов RAG", 3, 20, 12)

    if st.button("Сгенерировать гипотезы", type="primary", use_container_width=True):
        if not problem.strip():
            st.error("Укажите целевую проблему")
            return
        st.session_state.problem = problem
        st.session_state.constraints = constraints

        weights = None
        if use_custom_weights and total > 0:
            weights = {
                "novelty": w_novelty / total,
                "feasibility": w_feasibility / total,
                "expected_value": w_value / total,
                "risk": w_risk / total,
            }

        spinner_msg = "Индексация + RAG + YandexGPT…" if auto_ingest else "RAG → YandexGPT (1–3 мин)…"
        with st.spinner(spinner_msg):
            try:
                result = generate(
                    problem,
                    constraints,
                    top_k=top_k,
                    weights=weights,
                    auto_ingest=auto_ingest,
                )
                st.session_state.result = result
                st.success(
                    f"Готово: {len(result.get('hypotheses', []))} гипотез "
                    f"({(result.get('judge_summary') or {}).get('approved', 0)} одобрено)"
                )
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

"""Вкладка результатов генерации."""

from __future__ import annotations

import streamlit as st

from graph_viz import render_influence_graph_html
from hypothesis_api import download_export, submit_feedback
from ui.tables import hypotheses_table, sorted_hypotheses


def _confidence_label(level: str) -> str:
    return {"high": "высокая", "medium": "средняя", "low": "низкая"}.get(level, level)


def _collect_uncertainty_metrics(hypotheses: list[dict]) -> dict:
    """Агрегаты для блока «Неопределённость» по гипотезам прогона."""
    confidences: list[str] = []
    predictive_scores: list[float] = []
    judge_scores: list[float] = []
    for h in hypotheses:
        bc = h.get("business_case") or {}
        conf = bc.get("confidence")
        if conf:
            confidences.append(str(conf))
        ra = h.get("research_analysis") or {}
        ps = ra.get("predictive_score")
        if ps is not None:
            predictive_scores.append(float(ps))
        jv = h.get("judge_verdict") or {}
        if jv.get("overall_score") is not None:
            judge_scores.append(float(jv["overall_score"]))
    avg_predictive = (
        sum(predictive_scores) / len(predictive_scores) if predictive_scores else None
    )
    avg_judge = sum(judge_scores) / len(judge_scores) if judge_scores else None
    conf_counts = {k: confidences.count(k) for k in ("high", "medium", "low") if k in confidences}
    dominant_conf = max(conf_counts, key=conf_counts.get) if conf_counts else None
    return {
        "avg_predictive": avg_predictive,
        "predictive_n": len(predictive_scores),
        "avg_judge": avg_judge,
        "dominant_confidence": dominant_conf,
        "confidence_counts": conf_counts,
    }


@st.cache_data(show_spinner=False)
def _cached_export(gen_id: str, fmt: str) -> bytes:
    return download_export(gen_id, fmt)


def render_tab_results() -> None:
    result = st.session_state.get("result")
    if not result:
        st.info("Сначала сгенерируйте гипотезы на вкладке «Генерация»")
        return

    hypotheses = result.get("hypotheses") or []
    if not hypotheses:
        st.warning("Гипотезы не найдены в ответе API")
        return

    st.subheader("Результаты")
    gen_id = result["generation_id"]
    rag_ids = set(result.get("retrieval_doc_ids") or [])
    approved_n = (result.get("judge_summary") or {}).get("approved", 0)
    total_n = len(hypotheses)
    st.caption(
        f"generation_id: `{gen_id}` | RAG-источников: {len(rag_ids)} | "
        f"гипотез: {total_n} (одобрено {approved_n})"
    )

    retrieval_sources = result.get("retrieval_sources") or []
    with st.expander("Откуда взят контекст RAG (источники поиска)", expanded=False):
        st.markdown(
            "Это документы, фрагменты которых **попали в контекст** при генерации. "
            "Гипотеза должна ссылаться на `doc_id` из этого списка."
        )
        if retrieval_sources:
            for src in retrieval_sources:
                title = src.get("title") or src.get("doc_id")
                path = src.get("source_path") or ""
                st.markdown(
                    f"- **`{src.get('doc_id')}`** — {title}  \n"
                    f"  чанков в контексте: {src.get('chunks_in_context', 0)}, "
                    f"score: {src.get('max_score', 0):.3f}"
                    + (f"  \n  файл: `{path}`" if path else "")
                )
        else:
            for doc_id in result.get("retrieval_doc_ids") or []:
                st.markdown(f"- `{doc_id}`")

    if result.get("conflicts_detected"):
        st.warning(
            "**Противоречия в источниках:**\n"
            + "\n".join(f"- {c}" for c in result["conflicts_detected"])
        )

    gaps = result.get("knowledge_gaps") or []
    if gaps:
        with st.expander(f"Пробелы в знаниях ({len(gaps)})", expanded=False):
            for g in gaps:
                sev = g.get("severity", "medium")
                icon = "🔴" if sev == "high" else ("🟡" if sev == "medium" else "🟢")
                st.markdown(f"{icon} **{g.get('topic')}** — {g.get('evidence', '')}")
                if g.get("suggested_action"):
                    st.caption(f"→ {g['suggested_action']}")

    js = result.get("judge_summary")
    unc = _collect_uncertainty_metrics(hypotheses)
    if js or unc["predictive_n"] or unc["dominant_confidence"]:
        st.markdown("**Неопределённость и качество прогона**")
        st.caption(
            "Сводка метрик надёжности: JQI и grounding — качество судьи и RAG; "
            "confidence — уверенность бизнес-кейса; predictive — ML-модель по таблице опытов."
        )
        u1, u2, u3, u4, u5 = st.columns(5)
        if js:
            target = js.get("objective_target", 75)
            jqi = js.get("jqi", 0)
            u1.metric(
                "JQI",
                f"{jqi:.1f}",
                delta=f"{jqi - target:+.1f} к цели {target:.0f}",
            )
            u2.metric("Привязка к RAG", f"{100 * js.get('grounding_rate', 0):.0f}%")
            u3.metric("Одобрено", f"{js.get('approved', 0)}/{js.get('total', 0)}")
            u4.metric("ТЗ кейса", f"{js.get('avg_case_compliance_pct', 0):.0f}%")
        if unc["dominant_confidence"]:
            u5.metric(
                "Confidence (ROI)",
                _confidence_label(unc["dominant_confidence"]),
                help="Доминирующая уверенность бизнес-кейса по гипотезам",
            )
        elif js:
            u5.metric("Confidence (ROI)", "—")
        if js:
            jqi = js.get("jqi", 0)
            target = js.get("objective_target", 75)
            st.progress(min(jqi / 100, 1.0), text=f"JQI {jqi:.1f} / 100 (цель {target:.0f})")
        if unc["avg_predictive"] is not None:
            st.progress(
                unc["avg_predictive"],
                text=(
                    f"Средняя predictive-оценка {unc['avg_predictive']:.0%} "
                    f"({unc['predictive_n']}/{len(hypotheses)} гипотез с ML)"
                ),
            )
        if unc["avg_judge"] is not None and js:
            st.caption(
                f"Средний балл судьи: {unc['avg_judge']:.1f}/10 · "
                f"Grounding: {100 * js.get('grounding_rate', 0):.0f}% · "
                + (
                    f"Confidence: {', '.join(f'{_confidence_label(k)}={v}' for k, v in unc['confidence_counts'].items())}"
                    if unc["confidence_counts"]
                    else "Confidence: нет данных"
                )
            )
        if js and js.get("compliance_notes"):
            with st.expander("Соответствие требованиям кейса"):
                for note in js["compliance_notes"]:
                    st.markdown(f"- {note}")

    sorted_hyps = sorted_hypotheses(hypotheses)
    show_all = st.checkbox("Показать отклонённые гипотезы", value=True)
    visible_hyps = sorted_hyps if show_all else [
        h for h in sorted_hyps if (h.get("judge_verdict") or {}).get("approved")
    ]
    df = hypotheses_table(visible_hyps, rag_ids)

    st.dataframe(df.drop(columns=["id"]), use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**Детали гипотезы**")

    labels = [
        f"{row['Статус']} [{row['JQI obj']}] {row['Гипотеза'][:70]}…"
        for _, row in df.iterrows()
    ]
    idx = st.selectbox("Выберите гипотезу", range(len(labels)), format_func=lambda i: labels[i])
    h = visible_hyps[idx]

    col_a, col_b = st.columns([2, 1])

    with col_a:
        st.markdown(f"### {h.get('text', '')}")
        st.markdown(f"**Механизм:** {h.get('mechanism', '')}")
        st.markdown(f"**Обоснование:** {h.get('reasoning', '')}")

        if h.get("verification_roadmap"):
            st.markdown("**Дорожная карта (текст):**")
            for step in h["verification_roadmap"]:
                st.markdown(f"- {step}")

        ra = h.get("research_analysis") or {}
        if ra:
            st.markdown("**Исследовательский анализ**")
            if ra.get("analogy"):
                st.caption(f"Аналогия: {ra['analogy']}")
            if ra.get("analogy_domains"):
                st.caption(f"Домены: {', '.join(ra['analogy_domains'])}")
            if ra.get("counterfactual"):
                st.caption(f"Контрфактуал: {ra['counterfactual']}")
            if ra.get("counterfactual_baseline"):
                st.caption(f"Базовый уровень: {ra['counterfactual_baseline']}")
            if ra.get("model_name"):
                st.caption(
                    f"ML-модель: {ra['model_name']}"
                    + (f" (R²={ra['model_r2']:.2f})" if ra.get("model_r2") is not None else "")
                )
            if ra.get("predictive_score") is not None:
                st.progress(
                    float(ra["predictive_score"]),
                    text=f"Предсказательная оценка {float(ra['predictive_score']):.0%}",
                )
            if ra.get("predictive_notes"):
                st.caption(ra["predictive_notes"])

        bc = h.get("business_case") or {}
        if bc:
            st.markdown("**Бизнес-кейс / ROI**")
            cols = st.columns(4)
            cols[0].metric("Целевой KPI", bc.get("target_kpi", "—"))
            if bc.get("expected_delta_pct") is not None:
                cols[1].metric("Прирост KPI", f"+{bc['expected_delta_pct']:.1f} п.п.")
            if bc.get("roi_ratio") is not None:
                cols[2].metric("ROI", f"{bc['roi_ratio']:.1f}x")
            if bc.get("payback_months") is not None:
                cols[3].metric("Окупаемость", f"{bc['payback_months']:.0f} мес.")
            if bc.get("annual_revenue_impact_rub"):
                st.caption(
                    f"Доп. выручка: {bc['annual_revenue_impact_rub']:,.0f} руб/год; "
                    f"экономия: {bc.get('annual_cost_savings_rub', 0):,.0f} руб/год"
                )
            if bc.get("narrative"):
                st.info(bc["narrative"].replace("**", ""))

        sr = h.get("structured_roadmap") or []
        if sr or h.get("verification_roadmap"):
            from ui.roadmap_editor import render_roadmap_constructor

            def _on_roadmap_saved(updated: dict) -> None:
                st.session_state.result["hypotheses"] = [
                    updated if x["id"] == h["id"] else x
                    for x in st.session_state.result["hypotheses"]
                ]

            render_roadmap_constructor(h, on_saved=_on_roadmap_saved)

        if h.get("sources"):
            st.markdown("**Источники гипотезы (цитаты LLM):**")
            for s in h["sources"]:
                doc_id = s.get("doc_id", "")
                badge = "✓ в RAG-контексте" if doc_id in rag_ids else "⚠ не в RAG-контексте"
                st.markdown(f"- `{doc_id}` — {badge}")
                st.caption(s.get("snippet", "")[:300])

    with col_b:
        sb = h.get("score_breakdown") or {}
        jv = h.get("judge_verdict") or {}
        if jv:
            badge = "✅ Одобрено" if jv.get("approved") else "❌ Отклонено"
            st.markdown(f"**Судья:** {badge} (балл {jv.get('overall_score', 0)})")

            rationale = jv.get("decision_rationale") or []
            if rationale:
                title = (
                    "**Почему одобрено:**"
                    if jv.get("approved")
                    else "**Почему отклонено:**"
                )
                st.markdown(title)
                for line in rationale:
                    st.markdown(f"• {line}")
            elif not jv.get("approved") and jv.get("issues"):
                st.markdown("**Причины отклонения:**")
                for issue in jv["issues"]:
                    st.markdown(f"• {issue}")

            st.caption(
                "_«Обоснование» слева — аргумент генератора при создании; "
                "блок выше — решение независимого судьи._"
            )
        st.metric("Objective (судья)", f"{jv.get('objective_score', 0):.3f}")
        st.metric("Composite (ранж.)", f"{sb.get('composite', 0):.3f}")
        st.progress(sb.get("novelty", 0), text=f"Новизна {sb.get('novelty', 0):.2f}")
        st.progress(sb.get("feasibility", 0), text=f"Реализуемость {sb.get('feasibility', 0):.2f}")
        st.progress(sb.get("expected_value", 0), text=f"Ценность {sb.get('expected_value', 0):.2f}")
        st.progress(sb.get("risk_inverted", 0), text=f"Риск↓ {sb.get('risk_inverted', 0):.2f}")

        cc = jv.get("case_compliance") or {}
        if cc.get("items"):
            st.markdown(
                f"**Чеклист ТЗ:** {cc.get('mandatory_passed', 0)}/"
                f"{cc.get('mandatory_total', 0)} обязательных"
            )
            for item in cc["items"]:
                icon = "✅" if item.get("passed") else ("⚠️" if not item.get("required") else "❌")
                req = "обяз." if item.get("required") else "опц."
                st.caption(f"{icon} [{req}] {item.get('label')}")
                if not item.get("passed") and item.get("note"):
                    st.caption(f"   _{item['note']}_")

        if jv.get("issues"):
            st.markdown("**Замечания судьи:**")
            for issue in jv["issues"][:5]:
                st.caption(f"• {issue}")
        if jv.get("recommendations"):
            st.markdown("**Рекомендации:**")
            for rec in jv["recommendations"][:3]:
                st.caption(f"→ {rec}")

        fb1, fb2 = st.columns(2)
        if fb1.button("✓ Подтвердить", key=f"ok_{h['id']}"):
            try:
                submit_feedback(h["id"], "confirmed")
                st.toast("Фидбэк сохранён")
            except Exception as e:
                st.error(str(e))
        if fb2.button("✗ Отклонить", key=f"no_{h['id']}"):
            try:
                submit_feedback(h["id"], "rejected")
                st.toast("Фидбэк сохранён")
            except Exception as e:
                st.error(str(e))

    graph_html = render_influence_graph_html(h.get("influence_graph", {}))
    if graph_html:
        st.markdown("**Граф влияния**")
        st.components.v1.html(graph_html, height=400, scrolling=True)
    elif h.get("influence_graph", {}).get("nodes"):
        st.json(h["influence_graph"])

    st.divider()
    st.subheader("Экспорт")
    e1, e2, e3, e4 = st.columns(4)
    exports = [
        (e1, "pdf", "PDF отчёт", "application/pdf", f"report_{gen_id[:8]}.pdf"),
        (e2, "docx", "DOCX", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", f"report_{gen_id[:8]}.docx"),
        (e3, "json", "JSON задачи", "application/json", f"tasks_{gen_id[:8]}.json"),
        (e4, "csv", "CSV задачи", "text/csv", f"tasks_{gen_id[:8]}.csv"),
    ]
    for col, fmt, label, mime, fname in exports:
        with col:
            try:
                st.download_button(
                    label,
                    data=_cached_export(gen_id, fmt),
                    file_name=fname,
                    mime=mime,
                    use_container_width=True,
                    key=f"dl_{fmt}_{gen_id[:8]}",
                )
            except Exception as exc:
                st.error(str(exc)[:100])

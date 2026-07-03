"""Streamlit-дашборд «Фабрики гипотез»."""
from __future__ import annotations

import json
import os

import pandas as pd
import requests
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Фабрика гипотез", page_icon="🧪", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.5rem;}
div[data-testid="stMetric"] {
    background: linear-gradient(135deg, #f6f8fc 0%, #eef2f9 100%);
    border: 1px solid #dde5f0; border-radius: 12px; padding: 12px 16px;
}
.hyp-badge {display:inline-block; padding:2px 10px; border-radius:12px;
    font-size:0.8rem; font-weight:600; margin-right:6px;}
.badge-green {background:#e7f5ec; color:#1a7f37;}
.badge-red {background:#fdecec; color:#c0392b;}
.badge-blue {background:#eaf1fd; color:#2456a6;}
</style>
""", unsafe_allow_html=True)

st.title("🧪 Фабрика гипотез")
st.caption("Генерация и приоритизация проверяемых гипотез по снижению потерь Ni/Cu с хвостами обогащения")

PROBLEM_LABELS = {
    "regrind": "🔩 Недораскрытие (сростки)",
    "coarse_flotation": "🫧 Потери раскрытых зёрен",
    "slimes": "🌫 Шламовые потери",
    "not_extractable": "⛔ Неизвлекаемо",
}

# ---------- сайдбар ----------
with st.sidebar:
    st.header("⚙️ Система")
    try:
        health = requests.get(f"{API}/health", timeout=5).json()
    except requests.RequestException:
        st.error(f"API недоступен: {API}\nЗапустите: uvicorn app.main:app")
        st.stop()
    c1, c2 = st.columns(2)
    c1.metric("База знаний", f"{health['kb_chunks']}", "фрагментов")
    c2.metric("LLM", "✓ готов" if health["llm_available"] else "✗ нет ключа")
    st.caption(f"Гибридный поиск: BM25{' + эмбеддинги' if health['kb_embeddings'] else ''} · "
               f"экспертных пар: {len(health['expert_pairs'])}")

    st.header("🎛 Веса ранжирования")
    st.caption("Экспертная настройка — сумма нормируется автоматически")
    weights = {
        "novelty": st.slider("💡 Новизна", 0.0, 1.0, 0.2, 0.05),
        "feasibility": st.slider("🔧 Реализуемость", 0.0, 1.0, 0.3, 0.05),
        "impact": st.slider("📈 Потенциальный эффект", 0.0, 1.0, 0.35, 0.05),
        "risk": st.slider("🛡 Низкий риск", 0.0, 1.0, 0.15, 0.05),
    }

# ---------- форма запуска ----------
with st.container(border=True):
    col_in, col_goal = st.columns([1, 2])
    with col_in:
        uploaded = st.file_uploader("📂 Отчёт по хвостам (Excel)", type=["xlsx"])
    with col_goal:
        goal = st.text_input("🎯 Цель", "Снизить потери Ni и Cu с отвальными хвостами")
        constraints = st.text_input("⛓ Ограничения",
                                    "Существующее оборудование фабрики, без капитального строительства")
        n_hyp = st.select_slider("Число гипотез", options=list(range(3, 16)), value=8)
    run_btn = st.button("🚀 Сгенерировать гипотезы", type="primary",
                        disabled=uploaded is None, use_container_width=True)

if uploaded and run_btn:
    with st.spinner("Диагностика → поиск по базе знаний → генерация (1–3 мин из-за лимитов LLM) → ранжирование…"):
        resp = requests.post(
            f"{API}/hypotheses/generate",
            files={"file": (uploaded.name, uploaded.getvalue())},
            data={"goal": goal, "constraints": constraints,
                  "n_hypotheses": n_hyp, "weights": json.dumps(weights)},
            timeout=900,
        )
    if resp.status_code != 200:
        st.error(f"Ошибка {resp.status_code}: {resp.text}")
    else:
        st.session_state["run"] = resp.json()
        st.session_state["last_weights"] = dict(weights)

run = st.session_state.get("run")
if not run:
    st.info("Загрузите Excel-отчёт по хвостам («Хвосты КГМК.xlsx», «Хвосты ТОФ_2.xlsx»…) и нажмите «Сгенерировать».")
    st.stop()

run_id = run["run_id"]

# живая пересортировка при изменении весов
if st.session_state.get("last_weights") != weights:
    r = requests.post(f"{API}/hypotheses/{run_id}/rerank", json={"weights": weights}, timeout=30)
    if r.ok:
        run["hypotheses"] = r.json()["hypotheses"]
    st.session_state["last_weights"] = dict(weights)

# ---------- метрики прогона ----------
diags = run.get("diagnostics", [])
total_ni = sum(d["loss_tons"] for d in diags if d["element"] == "28")
total_cu = sum(d["loss_tons"] for d in diags if d["element"] == "29")
extr = sum(d["extractable_tons"] or 0 for d in diags if d["problem_type"] != "not_extractable")
grounded_n = sum(1 for h in run["hypotheses"] if h.get("grounded"))

m1, m2, m3, m4 = st.columns(4)
m1.metric("Потери Ni", f"{total_ni:,.0f} т".replace(",", " "))
m2.metric("Потери Cu", f"{total_cu:,.0f} т".replace(",", " "))
m3.metric("Извлекаемо (адресуемо)", f"{extr:,.0f} т".replace(",", " "))
m4.metric("Гипотез с источниками", f"{grounded_n}/{len(run['hypotheses'])}")

tab_hyp, tab_diag, tab_expert, tab_export = st.tabs(
    ["💡 Гипотезы", "🔬 Диагноз", "👷 Сравнение с экспертами", "📤 Экспорт"])

# ---------- диагноз ----------
with tab_diag:
    if diags:
        df = pd.DataFrame(diags)
        df["Металл"] = df["element"].map({"28": "Ni", "29": "Cu"})
        st.subheader("Потери по классам крупности, т")
        chart = df.pivot_table(index="size_class", columns="Металл",
                               values="loss_tons", aggfunc="sum").fillna(0)
        order = ["+125", "-125+71", "+71", "-71+45", "-45+20", "-20+10", "-10"]
        chart = chart.reindex([c for c in order if c in chart.index])
        st.bar_chart(chart, color=["#f0a83c", "#4c78c8"])

        st.subheader("Адреса потерь (по убыванию извлекаемого металла)")
        show = df[df["problem_type"] != "not_extractable"].head(10).copy()
        show["Проблема"] = show["problem_type"].map(PROBLEM_LABELS)
        st.dataframe(
            show[["section", "size_class", "Металл", "loss_tons", "extractable_tons",
                  "dominant_form", "Проблема"]].rename(columns={
                "section": "Секция", "size_class": "Класс, мкм",
                "loss_tons": "Потери, т", "extractable_tons": "Извлекаемо, т",
                "dominant_form": "Домин. форма"}),
            use_container_width=True, hide_index=True)
    with st.expander("Полный текст диагноза (передаётся LLM)"):
        st.markdown(run["summary_text"])

# ---------- гипотезы ----------
with tab_hyp:
    st.caption(f"Прогон `{run_id}` · {run['input_file']} · self-consistency: "
               f"{run.get('n_samples_used', 1)} сэмпл(а)")
    for i, h in enumerate(run["hypotheses"]):
        rank_info = h.get("ranking", {})
        final = rank_info.get("final", 0)
        target = h.get("target") or {}
        badges = (
            f'<span class="hyp-badge badge-blue">скор {final}</span>'
            + (f'<span class="hyp-badge badge-blue">{target.get("element", "")} · '
               f'{target.get("size_class", "")} мкм</span>' if target.get("size_class") else "")
            + (f'<span class="hyp-badge badge-green">✓ {len(h.get("sources", []))} источник(а)</span>'
               if h.get("grounded")
               else '<span class="hyp-badge badge-red">без источников −0.25</span>')
        )
        with st.container(border=True):
            st.markdown(f"**{i + 1}. {h['hypothesis']}**")
            st.markdown(badges, unsafe_allow_html=True)
            c1, c2 = st.columns([3, 1.2])
            with c1:
                st.markdown(f"⚙️ **Механизм:** {h.get('mechanism', '—')}")
                st.markdown(f"📈 **Ожидаемый эффект:** {h.get('expected_effect', '—')}")
                st.markdown(f"🔧 **Реализуемость:** {h.get('feasibility_note', '—')}")
                risks = h.get("risks") or {}
                st.markdown(f"⚠️ **Риски:** техн. — {risks.get('technical', '—')}; "
                            f"экон. — {risks.get('economic', '—')}")
                if h.get("verification_roadmap"):
                    with st.expander("🗺 Дорожная карта проверки"):
                        for step in h["verification_roadmap"]:
                            st.markdown(f"- {step}")
                if h.get("sources"):
                    with st.expander("📚 Источники"):
                        for s in h["sources"]:
                            st.markdown(f"**[{s['ref']}] {s['doc_id']}, стр. {s['page']}**")
                            st.caption(f"«{s['snippet']}…»")
            with c2:
                comp = rank_info.get("components", {})
                for crit, label in [("impact", "Эффект"), ("feasibility", "Реализуемость"),
                                    ("novelty", "Новизна"), ("risk", "Низкий риск")]:
                    c = comp.get(crit, {})
                    raw = c.get("raw") or 0
                    st.progress(min(1.0, raw / 5), text=f"{label}: {raw}/5 (вклад {c.get('contribution', 0):.2f})")
                fb1, fb2 = st.columns(2)
                if fb1.button("👍 в работу", key=f"up{i}", use_container_width=True):
                    requests.post(f"{API}/hypotheses/{run_id}/feedback",
                                  json={"hypothesis_index": i, "accepted": True}, timeout=10)
                    st.toast("Принята — веса ранжирования обновлены")
                if fb2.button("👎 мимо", key=f"down{i}", use_container_width=True):
                    requests.post(f"{API}/hypotheses/{run_id}/feedback",
                                  json={"hypothesis_index": i, "accepted": False}, timeout=10)
                    st.toast("Отклонена — веса ранжирования обновлены")

# ---------- сравнение с экспертами ----------
with tab_expert:
    try:
        ex = requests.get(f"{API}/examples", timeout=10).json()
    except requests.RequestException:
        ex = []
    input_name = (run.get("input_file") or "").replace("Хвосты", "").replace(".xlsx", "").strip(" _").lower()
    match = next((e for e in ex if e["name"].lower() == input_name), None)
    if match:
        st.caption("⚠️ Гипотезы экспертов этого объекта НЕ использовались как примеры при генерации (без утечки)")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("🤖 Система")
            for i, h in enumerate(run["hypotheses"], 1):
                st.markdown(f"{i}. {h['hypothesis']}")
        with c2:
            st.subheader(f"👷 Эксперты ({match['name']})")
            for e in match["expert_hypotheses"]:
                st.markdown(f"- {e}")
    else:
        st.info("Для этого объекта нет экспертных гипотез в базе — сравнение доступно для КГМК, НОФ Вкр, НОФ мед, ТОФ.")

# ---------- экспорт ----------
with tab_export:
    c1, c2, c3 = st.columns(3)
    with c1:
        r = requests.post(f"{API}/export/report", params={"run_id": run_id}, timeout=60)
        st.download_button("📄 Отчёт DOCX", r.content, f"report_{run_id}.docx", use_container_width=True)
        st.caption("Бизнес-отчёт: диагноз + гипотезы с обоснованием")
    with c2:
        r = requests.get(f"{API}/export/tasks", params={"run_id": run_id, "fmt": "csv"}, timeout=30)
        st.download_button("📋 Задачи CSV", r.text, f"tasks_{run_id}.csv", use_container_width=True)
        st.caption("Импорт в Jira / YouTrack")
    with c3:
        r = requests.get(f"{API}/export/tasks", params={"run_id": run_id, "fmt": "json"}, timeout=30)
        st.download_button("🔗 Задачи JSON", r.text, f"tasks_{run_id}.json", use_container_width=True)
        st.caption("Интеграция по API")

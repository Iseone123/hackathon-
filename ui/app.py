"""Streamlit-дашборд «Фабрики гипотез»."""
from __future__ import annotations

import json
import os

import pandas as pd
import requests
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Фабрика гипотез", layout="wide")

st.title("Фабрика гипотез")
st.caption("Генерация и приоритизация проверяемых гипотез по снижению потерь Ni/Cu с хвостами обогащения")

PROBLEM_LABELS = {
    "regrind": "Недораскрытие (сростки)",
    "coarse_flotation": "Потери раскрытых зёрен",
    "slimes": "Шламовые потери",
    "not_extractable": "Неизвлекаемо текущей технологией",
}

CRITERIA = [("impact", "Эффект"), ("feasibility", "Реализуемость"),
            ("novelty", "Новизна"), ("risk", "Низкий риск")]


def fmt_tons(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


# ---------- сайдбар ----------
with st.sidebar:
    st.subheader("Состояние системы")
    try:
        health = requests.get(f"{API}/health", timeout=5).json()
    except requests.RequestException:
        st.error(f"API недоступен: {API}")
        st.stop()
    st.markdown(
        f"- База знаний: **{health['kb_chunks']}** фрагментов\n"
        f"- Поиск: BM25{' + эмбеддинги' if health['kb_embeddings'] else ''}\n"
        f"- LLM: {'подключена' if health['llm_available'] else ':red[не настроена]'}\n"
        f"- Экспертных пар: {len(health['expert_pairs'])}"
    )
    st.divider()
    st.subheader("Веса ранжирования")
    st.caption("Сумма нормируется автоматически")
    weights = {
        "novelty": st.slider("Новизна", 0.0, 1.0, 0.2, 0.05),
        "feasibility": st.slider("Реализуемость", 0.0, 1.0, 0.3, 0.05),
        "impact": st.slider("Потенциальный эффект", 0.0, 1.0, 0.35, 0.05),
        "risk": st.slider("Низкий риск", 0.0, 1.0, 0.15, 0.05),
    }

# ---------- форма запуска ----------
with st.container(border=True):
    col_in, col_goal = st.columns([1, 2])
    with col_in:
        uploaded = st.file_uploader("Отчёт по хвостам (Excel)", type=["xlsx"])
    with col_goal:
        goal = st.text_input("Цель", "Снизить потери Ni и Cu с отвальными хвостами")
        constraints = st.text_input("Ограничения",
                                    "Существующее оборудование фабрики, без капитального строительства")
        n_hyp = st.number_input("Число гипотез", 3, 15, 8)
    run_btn = st.button("Сгенерировать гипотезы", type="primary", disabled=uploaded is None)

if uploaded and run_btn:
    with st.spinner("Диагностика, поиск по базе знаний, генерация и ранжирование (1–3 минуты)…"):
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
    st.info("Загрузите Excel-отчёт по хвостам (например, «Хвосты КГМК.xlsx») и нажмите «Сгенерировать гипотезы».")
    st.stop()

run_id = run["run_id"]

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
m1.metric("Потери Ni, т/год", fmt_tons(total_ni))
m2.metric("Потери Cu, т/год", fmt_tons(total_cu))
m3.metric("Извлекаемо, т/год", fmt_tons(extr))
m4.metric("Обосновано источниками", f"{grounded_n} из {len(run['hypotheses'])}")

tab_hyp, tab_diag, tab_expert, tab_export = st.tabs(
    ["Гипотезы", "Диагноз", "Сравнение с экспертами", "Экспорт"])

# ---------- диагноз ----------
with tab_diag:
    if diags:
        df = pd.DataFrame(diags)
        df["Металл"] = df["element"].map({"28": "Ni", "29": "Cu"})
        st.markdown("**Потери по классам крупности, т**")
        chart = df.pivot_table(index="size_class", columns="Металл",
                               values="loss_tons", aggfunc="sum").fillna(0)
        order = ["+125", "-125+71", "+71", "-71+45", "-45+20", "-20+10", "-10"]
        chart = chart.reindex([c for c in order if c in chart.index])
        st.bar_chart(chart)

        st.markdown("**Адреса потерь** (по убыванию извлекаемого металла)")
        show = df[df["problem_type"] != "not_extractable"].head(10).copy()
        show["Тип проблемы"] = show["problem_type"].map(PROBLEM_LABELS)
        st.dataframe(
            show[["section", "size_class", "Металл", "loss_tons", "extractable_tons",
                  "dominant_form", "Тип проблемы"]].rename(columns={
                "section": "Секция", "size_class": "Класс, мкм",
                "loss_tons": "Потери, т", "extractable_tons": "Извлекаемо, т",
                "dominant_form": "Доминирующая форма"}),
            use_container_width=True, hide_index=True)
    with st.expander("Полный текст диагноза (в этом виде он передаётся LLM)"):
        st.markdown(run["summary_text"])

# ---------- гипотезы ----------
with tab_hyp:
    st.caption(f"Прогон {run_id} · {run['input_file']} · "
               f"self-consistency: {run.get('n_samples_used', 1)} независимых прогона LLM")
    for i, h in enumerate(run["hypotheses"]):
        rank_info = h.get("ranking", {})
        target = h.get("target") or {}
        meta = [f"приоритет {rank_info.get('final', 0):.2f}"]
        if target.get("size_class"):
            meta.append(f"{target.get('element', '')}, класс {target['size_class']} мкм")
        if h.get("grounded"):
            meta.append(f":green[источников: {len(h.get('sources', []))}]")
        else:
            meta.append(":red[не подтверждена источниками, штраф −0.25]")

        with st.container(border=True):
            st.markdown(f"**{i + 1}. {h['hypothesis']}**")
            st.caption(" · ".join(meta))
            c1, c2 = st.columns([3, 1.2])
            with c1:
                st.markdown(f"**Механизм.** {h.get('mechanism', '—')}")
                st.markdown(f"**Ожидаемый эффект.** {h.get('expected_effect', '—')}")
                st.markdown(f"**Реализуемость.** {h.get('feasibility_note', '—')}")
                risks = h.get("risks") or {}
                st.markdown(f"**Риски.** Технические: {risks.get('technical', '—')} "
                            f"Экономические: {risks.get('economic', '—')}")
                if h.get("verification_roadmap"):
                    with st.expander("Дорожная карта проверки"):
                        for step in h["verification_roadmap"]:
                            st.markdown(f"- {step}")
                if h.get("sources"):
                    with st.expander("Источники"):
                        for s in h["sources"]:
                            st.markdown(f"**[{s['ref']}] {s['doc_id']}, стр. {s['page']}**")
                            st.caption(f"«{s['snippet']}…»")
            with c2:
                comp = rank_info.get("components", {})
                for crit, label in CRITERIA:
                    c = comp.get(crit, {})
                    raw = c.get("raw") or 0
                    st.progress(min(1.0, raw / 5), text=f"{label}: {raw}/5")
                fb1, fb2 = st.columns(2)
                if fb1.button("Принять", key=f"up{i}", use_container_width=True):
                    requests.post(f"{API}/hypotheses/{run_id}/feedback",
                                  json={"hypothesis_index": i, "accepted": True}, timeout=10)
                    st.toast("Гипотеза принята, веса ранжирования обновлены")
                if fb2.button("Отклонить", key=f"down{i}", use_container_width=True):
                    requests.post(f"{API}/hypotheses/{run_id}/feedback",
                                  json={"hypothesis_index": i, "accepted": False}, timeout=10)
                    st.toast("Гипотеза отклонена, веса ранжирования обновлены")

# ---------- сравнение с экспертами ----------
with tab_expert:
    try:
        ex = requests.get(f"{API}/examples", timeout=10).json()
    except requests.RequestException:
        ex = []
    input_name = (run.get("input_file") or "").replace("Хвосты", "").replace(".xlsx", "").strip(" _").lower()
    match = next((e for e in ex if e["name"].lower() == input_name), None)
    if match:
        st.caption("Гипотезы экспертов этого объекта не использовались при генерации — сравнение честное.")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Система**")
            for i, h in enumerate(run["hypotheses"], 1):
                st.markdown(f"{i}. {h['hypothesis']}")
        with c2:
            st.markdown(f"**Эксперты компании ({match['name']})**")
            for e in match["expert_hypotheses"]:
                st.markdown(f"- {e}")
    else:
        st.info("Экспертные гипотезы доступны для объектов: КГМК, НОФ Вкр, НОФ мед, ТОФ.")

# ---------- экспорт ----------
with tab_export:
    c1, c2, c3 = st.columns(3)
    with c1:
        r = requests.post(f"{API}/export/report", params={"run_id": run_id}, timeout=60)
        st.download_button("Отчёт DOCX", r.content, f"report_{run_id}.docx", use_container_width=True)
        st.caption("Бизнес-отчёт: диагноз и гипотезы с обоснованием")
    with c2:
        r = requests.get(f"{API}/export/tasks", params={"run_id": run_id, "fmt": "csv"}, timeout=30)
        st.download_button("Задачи CSV", r.text, f"tasks_{run_id}.csv", use_container_width=True)
        st.caption("Импорт в Jira / YouTrack")
    with c3:
        r = requests.get(f"{API}/export/tasks", params={"run_id": run_id, "fmt": "json"}, timeout=30)
        st.download_button("Задачи JSON", r.text, f"tasks_{run_id}.json", use_container_width=True)
        st.caption("Интеграция по API")

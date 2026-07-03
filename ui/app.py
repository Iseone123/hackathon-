"""Streamlit-дашборд «Фабрики гипотез»."""
from __future__ import annotations

import json
import os

import requests
import streamlit as st

API = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Фабрика гипотез", page_icon="🧪", layout="wide")
st.title("🧪 Фабрика гипотез — снижение потерь металлов с хвостами")

# ---------- сайдбар: статус и веса ----------
with st.sidebar:
    st.header("Система")
    try:
        health = requests.get(f"{API}/health", timeout=5).json()
        st.success(f"База знаний: {health['kb_chunks']} фрагментов")
        st.caption(f"Эмбеддинги: {'да' if health['kb_embeddings'] else 'нет (BM25)'} · "
                   f"LLM: {'✓' if health['llm_available'] else '✗ нет ключа'} · "
                   f"примеров экспертов: {len(health['expert_pairs'])}")
    except requests.RequestException:
        st.error(f"API недоступен: {API}\nЗапустите: uvicorn app.main:app")
        st.stop()

    st.header("Веса ранжирования")
    st.caption("Режим экспертной настройки: сумма нормируется автоматически")
    w_novelty = st.slider("Новизна", 0.0, 1.0, 0.2, 0.05)
    w_feasibility = st.slider("Реализуемость", 0.0, 1.0, 0.3, 0.05)
    w_impact = st.slider("Потенциальный эффект", 0.0, 1.0, 0.35, 0.05)
    w_risk = st.slider("Низкий риск", 0.0, 1.0, 0.15, 0.05)
    weights = {"novelty": w_novelty, "feasibility": w_feasibility,
               "impact": w_impact, "risk": w_risk}

# ---------- вход ----------
col_in, col_goal = st.columns([1, 2])
with col_in:
    uploaded = st.file_uploader("Отчёт по хвостам (Excel)", type=["xlsx"])
with col_goal:
    goal = st.text_input("Цель", "Снизить потери Ni и Cu с отвальными хвостами")
    constraints = st.text_input("Ограничения", "Существующее оборудование фабрики, без капитального строительства")
    n_hyp = st.number_input("Гипотез", 3, 15, 8)

if uploaded and st.button("Сгенерировать гипотезы", type="primary"):
    with st.spinner("Диагностика → поиск по базе знаний → генерация → ранжирование…"):
        resp = requests.post(
            f"{API}/hypotheses/generate",
            files={"file": (uploaded.name, uploaded.getvalue())},
            data={"goal": goal, "constraints": constraints,
                  "n_hypotheses": n_hyp, "weights": json.dumps(weights)},
            timeout=600,
        )
    if resp.status_code != 200:
        st.error(f"Ошибка {resp.status_code}: {resp.text}")
    else:
        st.session_state["run"] = resp.json()

run = st.session_state.get("run")
if run:
    run_id = run["run_id"]

    # живая пересортировка при изменении весов
    if st.session_state.get("last_weights") != weights:
        r = requests.post(f"{API}/hypotheses/{run_id}/rerank",
                          json={"weights": weights}, timeout=30)
        if r.ok:
            run["hypotheses"] = r.json()["hypotheses"]
        st.session_state["last_weights"] = dict(weights)

    tab_hyp, tab_diag, tab_export = st.tabs(["Гипотезы", "Диагноз", "Экспорт"])

    with tab_diag:
        st.markdown(run["summary_text"])

    with tab_hyp:
        st.caption(f"Прогон {run_id} · файл {run['input_file']} · "
                   f"self-consistency: {run.get('n_samples_used', 1)} сэмпл(а)")
        for i, h in enumerate(run["hypotheses"]):
            rank_info = h.get("ranking", {})
            grounded = "🟢" if h.get("grounded") else "🔴 без источников"
            with st.expander(
                f"**{i + 1}. {h['hypothesis'][:120]}**  ·  скор {rank_info.get('final', '—')} {grounded}",
                expanded=(i < 3),
            ):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"**Механизм:** {h.get('mechanism', '—')}")
                    st.markdown(f"**Ожидаемый эффект:** {h.get('expected_effect', '—')}")
                    st.markdown(f"**Реализуемость:** {h.get('feasibility_note', '—')}")
                    risks = h.get("risks") or {}
                    st.markdown(f"**Риски:** техн. — {risks.get('technical', '—')}; "
                                f"экон. — {risks.get('economic', '—')}")
                    if h.get("verification_roadmap"):
                        st.markdown("**Дорожная карта проверки:**")
                        for step in h["verification_roadmap"]:
                            st.markdown(f"- {step}")
                    for s in h.get("sources", []):
                        st.caption(f"📚 [{s['ref']}] {s['doc_id']}, стр. {s['page']}: «{s['snippet']}…»")
                with c2:
                    comp = rank_info.get("components", {})
                    st.markdown("**Раскладка скора**")
                    for crit, label in [("novelty", "Новизна"), ("feasibility", "Реализуемость"),
                                        ("impact", "Эффект"), ("risk", "Риск(низк.)")]:
                        c = comp.get(crit, {})
                        st.caption(f"{label}: {c.get('raw', '—')}/5 × {c.get('weight', 0):.2f} "
                                   f"= {c.get('contribution', 0):.3f}")
                    if rank_info.get("grounding_penalty"):
                        st.caption(f"Штраф (нет источников): −{rank_info['grounding_penalty']}")
                    if rank_info.get("consensus_bonus"):
                        st.caption(f"Бонус консенсуса: +{rank_info['consensus_bonus']}")
                    fb1, fb2 = st.columns(2)
                    if fb1.button("👍", key=f"up{i}"):
                        requests.post(f"{API}/hypotheses/{run_id}/feedback",
                                      json={"hypothesis_index": i, "accepted": True}, timeout=10)
                        st.toast("Учтено: веса обновлены")
                    if fb2.button("👎", key=f"down{i}"):
                        requests.post(f"{API}/hypotheses/{run_id}/feedback",
                                      json={"hypothesis_index": i, "accepted": False}, timeout=10)
                        st.toast("Учтено: веса обновлены")

    with tab_export:
        c1, c2, c3 = st.columns(3)
        with c1:
            r = requests.post(f"{API}/export/report", params={"run_id": run_id}, timeout=60)
            st.download_button("📄 Отчёт DOCX", r.content, f"report_{run_id}.docx")
        with c2:
            r = requests.get(f"{API}/export/tasks", params={"run_id": run_id, "fmt": "csv"}, timeout=30)
            st.download_button("📋 Задачи CSV (Jira)", r.text, f"tasks_{run_id}.csv")
        with c3:
            r = requests.get(f"{API}/export/tasks", params={"run_id": run_id, "fmt": "json"}, timeout=30)
            st.download_button("🔗 Задачи JSON (API)", r.text, f"tasks_{run_id}.json")
else:
    st.info("Загрузите Excel-отчёт по хвостам и нажмите «Сгенерировать гипотезы». "
            "Примеры: «Хвосты КГМК.xlsx», «Хвосты ТОФ_2.xlsx» из материалов хакатона.")

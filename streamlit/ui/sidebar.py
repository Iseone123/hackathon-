"""Боковая панель Streamlit."""

from __future__ import annotations

import streamlit as st

from hypothesis_api import (
    API_URL,
    demo_examples,
    health,
    index_status,
    ingest_batch,
    ingest_sync,
)


def render_sidebar() -> None:
    st.sidebar.title("Hypothesis Gen")
    st.sidebar.caption("RAG + Neo4j + YandexGPT")

    try:
        h = health()
        services = h.get("services", {})
        ok = all(v == "ok" for v in services.values())
        if ok:
            st.sidebar.success("API online")
        else:
            st.sidebar.warning(f"Services: {services}")
        models = h.get("models", {})
        if models:
            st.sidebar.caption("Модели YandexGPT")
            st.sidebar.text(
                f"Генерация: {models.get('generation_label', models.get('generation', '—'))}\n"
                f"  ({models.get('generation', '')})\n"
                f"Судья: {models.get('judge_label', models.get('judge', '—'))}\n"
                f"  ({models.get('judge', '')})"
            )
    except Exception as exc:
        st.sidebar.error(f"API недоступен: {exc}")
        st.sidebar.code(f"API_URL={API_URL}")
        return

    try:
        status = index_status()
        st.sidebar.metric("В Qdrant", status.get("qdrant_points", 0))
        neo4j = status.get("neo4j") or {}
        if neo4j.get("available"):
            st.sidebar.metric("Neo4j узлов", neo4j.get("nodes", 0))
        else:
            st.sidebar.warning("Neo4j недоступен")
        st.sidebar.caption(
            f"Файлов: {status.get('indexed_files', 0)}/{status.get('total_files', 0)} "
            f"проиндексировано"
        )
        if status.get("missing_files", 0) > 0:
            st.sidebar.warning(f"Не в индексе: {status['missing_files']} файлов")
            if st.sidebar.button("Доиндексировать всё", use_container_width=True):
                with st.spinner("Индексация пропущенных файлов…"):
                    res = ingest_sync()
                    st.sidebar.success(f"Добавлено: {res.get('ingested', 0)}")
                    st.rerun()
    except Exception:
        pass

    st.sidebar.divider()
    st.sidebar.subheader("Демо-сценарии")
    try:
        for ex in demo_examples():
            if st.sidebar.button(ex["name"], use_container_width=True, key=f"demo_{ex['id']}"):
                st.session_state.problem = ex["problem"]
                st.session_state.constraints = ex["constraints"]
                with st.spinner(f"Индексация {ex['data_path']}…"):
                    try:
                        ingest_batch(ex["data_path"], only_missing=True)
                        st.sidebar.success("Данные готовы")
                    except Exception as e:
                        st.sidebar.warning(f"Ingest: {e}")
                st.rerun()
    except Exception:
        st.sidebar.info("Демо-примеры недоступны без API")

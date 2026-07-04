"""Streamlit UI — генерация и приоритизация научных гипотез.

Запуск: streamlit run streamlit/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_STREAMLIT_DIR = Path(__file__).resolve().parent
if str(_STREAMLIT_DIR) not in sys.path:
    sys.path.insert(0, str(_STREAMLIT_DIR))

import streamlit as st

from ui.sidebar import render_sidebar
from ui.tabs.generate import render_tab_generate
from ui.tabs.ingest import render_tab_ingest
from ui.tabs.results import render_tab_results

st.set_page_config(
    page_title="Генерация гипотез",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)


def init_state() -> None:
    for key, val in {"result": None, "problem": "", "constraints": ""}.items():
        if key not in st.session_state:
            st.session_state[key] = val


def main() -> None:
    init_state()
    render_sidebar()

    st.title("Генерация научных гипотез")
    st.caption("Материаловедение · металлургия · RAG + граф знаний + YandexGPT")

    tab1, tab2, tab3 = st.tabs(["Генерация", "Данные", "Результаты"])
    with tab1:
        render_tab_generate()
    with tab2:
        render_tab_ingest()
    with tab3:
        render_tab_results()


if __name__ == "__main__":
    main()

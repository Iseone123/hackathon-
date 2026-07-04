"""Вкладка загрузки и индексации."""

from __future__ import annotations

import streamlit as st

from hypothesis_api import index_status, ingest_batch, ingest_file

DATA_DIRS = [
    "Дополнительные материалы",
    "Пример 1",
    "Пример 2",
    "Пример 3",
    "Пример 4",
    "Схемы флотации",
    "Регламенты",
]


def render_tab_ingest() -> None:
    st.subheader("Загрузка и индексация")

    try:
        status = index_status()
        c1, c2, c3 = st.columns(3)
        c1.metric("Всего файлов", status.get("total_files", 0))
        c2.metric("В индексе", status.get("indexed_files", 0))
        c3.metric("Пропущено", status.get("missing_files", 0))
        if status.get("missing"):
            with st.expander("Не проиндексированы"):
                for m in status["missing"][:20]:
                    st.text(f"• {m['path']} ({m['size_kb']} KB)")
    except Exception as exc:
        st.warning(f"Статус индекса недоступен: {exc}")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Загрузить файл**")
        uploaded = st.file_uploader(
            "PDF, DOCX, XLSX, PNG, TXT",
            type=["pdf", "docx", "xlsx", "xls", "png", "jpg", "jpeg", "txt", "md"],
        )
        title = st.text_input("Название документа", value="")
        if uploaded and st.button("Загрузить и проиндексировать", type="primary"):
            with st.spinner("Парсинг + эмбеддинги + NER…"):
                try:
                    meta = {"title": title or uploaded.name}
                    res = ingest_file(uploaded.name, uploaded.getvalue(), meta)
                    st.success(
                        f"✓ {res['doc_id']}: {res['chunks_indexed']} чанков, "
                        f"{res['entities_extracted']} сущностей"
                    )
                except Exception as exc:
                    st.error(str(exc))

    with col2:
        st.markdown("**Индексация папки из data/**")
        folder = st.selectbox("Папка", DATA_DIRS)
        only_missing = st.checkbox("Только новые файлы", value=True)
        if st.button("Индексировать папку", use_container_width=True):
            with st.spinner(f"Индексация «{folder}»…"):
                try:
                    res = ingest_batch(folder, only_missing=only_missing)
                    st.success(
                        f"Новых: {res.get('ingested', 0)}, "
                        f"пропущено: {res.get('skipped', 0)}, "
                        f"ошибок: {res.get('errors', 0)}"
                    )
                    with st.expander("Детали"):
                        st.json(res)
                except Exception as exc:
                    st.error(str(exc))

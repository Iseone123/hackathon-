"""Тесты выравнивания цитат."""

from __future__ import annotations

from app.rag.text_overlap import (
    align_snippet_to_corpus,
    build_doc_corpus,
    citation_overlap,
)


def test_align_snippet_finds_verbatim_excerpt():
    corpus = (
        "Снижение pH до указанного предела может быть осуществлено различными методами: "
        "добавлением в пульпу серной кислоты, добавлением 4—6 кг/т сернокислого железа, "
        "пропусканием через пульпу сернистого ангидрида."
    )
    llm_snippet = (
        "Снижение pH может быть осуществлено добавлением 4—6 кг/т сернокислого железа "
        "и другими методами согласно учебнику"
    )
    aligned, overlap = align_snippet_to_corpus(llm_snippet, corpus)
    assert citation_overlap(aligned, corpus) >= 0.3
    assert "сернокислого" in aligned.lower()


def test_build_doc_corpus_merges_chunks():
    chunks = [
        {"doc_id": "d1", "text": "первая часть флотации"},
        {"doc_id": "d1", "text": "вторая часть извлечения"},
        {"doc_id": "d2", "text": "другой документ"},
    ]
    corpus = build_doc_corpus(chunks)
    assert "первая" in corpus["d1"] and "вторая" in corpus["d1"]
    assert len(corpus) == 2


def test_align_snippet_prefers_reagent_window():
    corpus = (
        "Общие сведения о флотации медных руд и схемах обогащения. "
        "Для подавления пустой породы применяют КМЦ в дозировке 0,3–0,5 кг/т "
        "при pH 8–10 на существующем оборудовании."
    )
    llm_snippet = "флотация меди с реагентами согласно учебнику"
    hypothesis = "Добавление КМЦ 0,4 кг/т для подавления пустой породы при pH 9"
    aligned, overlap = align_snippet_to_corpus(
        llm_snippet, corpus, hypothesis_text=hypothesis
    )
    assert "кмц" in aligned.lower()
    assert overlap >= 0.25

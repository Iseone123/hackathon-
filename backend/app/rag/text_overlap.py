"""Сопоставление цитат с корпусом (кириллица, латиница, CJK и др.)."""

from __future__ import annotations

import re


def _normalize_text(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[\s\-—–]+", " ", text)
    text = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def tokenize_for_overlap(text: str) -> set[str]:
    """Токены для overlap: слова ≥3 символов + отдельные иероглифы CJK."""
    lowered = text.lower()
    tokens: set[str] = set(re.findall(r"[\w]{3,}", lowered, flags=re.UNICODE))
    tokens.update(re.findall(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", text))
    return tokens


def text_overlap_ratio(snippet: str, corpus: str) -> float:
    snip_tokens = tokenize_for_overlap(snippet)
    if not snip_tokens:
        return 0.0
    corpus_tokens = tokenize_for_overlap(corpus)
    if not corpus_tokens:
        return 0.0
    matched = sum(1 for t in snip_tokens if t in corpus_tokens)
    return matched / len(snip_tokens)


def substring_overlap_ratio(snippet: str, corpus: str) -> float:
    """Доля слов snippet, найденных подряд в corpus (приближение подстроки)."""
    snip_norm = _normalize_text(snippet)
    corp_norm = _normalize_text(corpus)
    if not snip_norm or not corp_norm:
        return 0.0
    if snip_norm in corp_norm:
        return 1.0
    snip_words = snip_norm.split()
    if len(snip_words) < 4:
        return text_overlap_ratio(snippet, corpus)

    best = 0.0
    window = min(len(snip_words), 24)
    for start in range(0, max(1, len(snip_words) - window + 1)):
        fragment = " ".join(snip_words[start : start + window])
        if fragment in corp_norm:
            return 1.0
        ratio = text_overlap_ratio(fragment, corpus)
        best = max(best, ratio)
    return best


def citation_overlap(snippet: str, corpus: str) -> float:
    """Максимум из токенного и подстрочного overlap."""
    return max(
        text_overlap_ratio(snippet, corpus),
        substring_overlap_ratio(snippet, corpus),
    )


def _hypothesis_terms(hypothesis_text: str) -> list[str]:
    terms: list[str] = []
    patterns = [
        r"кмц|карбоксиметилцеллюлоз",
        r"сернист\w+ натр",
        r"сернокисл\w+ желез",
        r"цианид",
        r"извест",
        r"собирател",
        r"пирит",
        r"флотац",
        r"магнитн",
        r"мельниц",
        r"гидроциклон",
        r"грохот",
        r"измельч",
        r"сепарац",
        r"\d+[\.,]?\d*\s*кг\s*/\s*т",
        r"pH\s*\d",
    ]
    lowered = hypothesis_text.lower()
    for pat in patterns:
        if re.search(pat, lowered, re.I):
            terms.append(pat)
    words = re.findall(r"[а-яёa-z]{6,}", lowered)
    stop = {"повышение", "извлечение", "оптимизация", "гипотеза", "процесс", "улучшит"}
    for w in words:
        if w not in stop and w not in terms:
            terms.append(w)
    return terms[:12]


def _term_in_text(term: str, text: str) -> bool:
    if term.startswith("(") or len(term) > 40:
        return bool(re.search(term, text, re.I))
    return term.lower() in text.lower()


def _trim_to_sentence_boundaries(excerpt: str, corpus: str, start: int, max_len: int) -> str:
    """Обрезает окно по границам предложений/абзацев в оригинальном corpus."""
    if not excerpt:
        return excerpt

    end = start + len(excerpt)
    # Расширяем влево до начала предложения
    left = start
    for sep in (". ", ".\n", "; ", ":\n", "\n\n"):
        idx = corpus.rfind(sep, max(0, start - 80), start)
        if idx != -1:
            left = idx + len(sep)
            break

    # Расширяем вправо до конца предложения
    right = min(len(corpus), end)
    for sep in (". ", ".\n", "; ", "\n\n"):
        idx = corpus.find(sep, end, min(len(corpus), end + 60))
        if idx != -1:
            right = idx + len(sep.strip())
            break

    trimmed = corpus[left:right].strip()
    if len(trimmed) > max_len:
        trimmed = trimmed[:max_len].rsplit(" ", 1)[0].strip()
    return re.sub(r"\s+", " ", trimmed) if trimmed else excerpt


def align_snippet_to_corpus(
    snippet: str,
    corpus: str,
    max_len: int = 280,
    *,
    hypothesis_text: str = "",
) -> tuple[str, float]:
    """
    Подбирает дословный фрагмент из corpus, ближайший к snippet.
    Возвращает (выровненная_цитата, overlap).
    """
    snippet = snippet.strip()
    if not snippet or not corpus:
        return snippet, 0.0

    corp_norm = _normalize_text(corpus)
    snip_norm = _normalize_text(snippet)

    if snip_norm in corp_norm:
        aligned = _extract_best_window(snippet, corpus, max_len, extra_terms=[])
        return aligned, 1.0

    hint_terms = _hypothesis_terms(hypothesis_text) if hypothesis_text else []
    aligned = _extract_best_window(snippet, corpus, max_len, extra_terms=hint_terms)
    overlap = citation_overlap(aligned, corpus)

    if hypothesis_text:
        hint_aligned = _extract_best_window(
            hypothesis_text, corpus, max_len, extra_terms=hint_terms
        )
        hint_overlap = citation_overlap(hint_aligned, corpus)
        if hint_overlap > overlap + 0.05:
            aligned, overlap = hint_aligned, hint_overlap

    raw_overlap = citation_overlap(snippet, corpus)
    if overlap < raw_overlap and raw_overlap >= 0.25:
        return snippet[:max_len], raw_overlap
    return aligned, overlap


def _extract_best_window(
    query: str,
    corpus: str,
    max_len: int,
    *,
    extra_terms: list[str] | None = None,
) -> str:
    """Скользящее окно с максимальным citation_overlap к query."""
    query = query.strip()
    if not query or not corpus:
        return query[:max_len]

    terms = list(extra_terms or [])

    best_start = 0
    best_len = max_len
    best_score = -1.0
    step = 20
    min_window = min(100, len(corpus))

    for win_len in (max_len, max_len + 50, max_len - 30):
        if win_len < min_window:
            continue
        for start in range(0, max(1, len(corpus) - min_window + 1), step):
            window = corpus[start : start + win_len]
            score = citation_overlap(query, window)
            for term in terms:
                if _term_in_text(term, window):
                    score += 0.06
            if score > best_score:
                best_score = score
                best_start = start
                best_len = win_len

    if best_score <= 0:
        return _extract_by_keywords(query, corpus, max_len, extra_terms=terms)

    excerpt = corpus[best_start : best_start + best_len].strip()
    excerpt = _trim_to_sentence_boundaries(excerpt, corpus, best_start, max_len)
    return re.sub(r"\s+", " ", excerpt)


def _extract_by_keywords(
    snippet: str,
    corpus: str,
    max_len: int,
    *,
    extra_terms: list[str] | None = None,
) -> str:
    """Fallback: окно с максимальным пересечением ключевых слов."""
    keywords = [
        w for w in re.findall(r"[а-яёa-z]{5,}", snippet.lower())
        if w not in {"которые", "является", "согласно", "данным", "источник"}
    ]
    if extra_terms:
        for term in extra_terms:
            if len(term) <= 40 and not term.startswith("("):
                keywords.append(term.lower())
            else:
                m = re.search(term, snippet.lower(), re.I)
                if m:
                    keywords.append(m.group(0).lower())
    if not keywords:
        return snippet[:max_len]

    corp_lower = corpus.lower()
    best_start = 0
    best_score = -1
    step = 40
    for start in range(0, max(len(corpus) - 80, 1), step):
        window = corpus[start : start + max_len + 80]
        score = sum(1 for kw in keywords if kw in window.lower())
        if score > best_score:
            best_score = score
            best_start = start

    if best_score <= 0:
        return snippet[:max_len]

    excerpt = corpus[best_start : best_start + max_len].strip()
    excerpt = re.sub(r"\s+", " ", excerpt)
    return excerpt


def build_doc_corpus(chunks: list[dict]) -> dict[str, str]:
    """Объединяет все чанки одного doc_id в единый корпус."""
    by_doc: dict[str, list[str]] = {}
    for chunk in chunks:
        doc_id = chunk["doc_id"]
        text = chunk.get("text", "")
        if text:
            by_doc.setdefault(doc_id, []).append(text)
    return {doc_id: "\n".join(parts) for doc_id, parts in by_doc.items()}

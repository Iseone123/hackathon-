"""Tests for agentic RAG orchestration."""

from __future__ import annotations

from app.hypotheses.context_builder import build_rag_context
from app.rag import agentic
from app.rag.agentic import AgenticRAGRetriever


class _FakeBaseRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int | None]] = []

    def retrieve(self, problem: str, constraints: str = "", top_k: int | None = None):
        self.calls.append((problem, constraints, top_k))
        step_id = len(self.calls)
        duplicate = {
            "doc_id": "doc-core",
            "chunk_index": 0,
            "text": "Доизмельчение раскрывает сростки и повышает извлечение.",
            "score": 0.8,
            "source": "book.pdf",
        }
        focused = {
            "doc_id": f"doc-{step_id}",
            "chunk_index": step_id,
            "text": f"Фрагмент для шага {step_id}: {problem}",
            "score": 0.7,
            "source": f"source-{step_id}.md",
        }
        return {
            "chunks": [duplicate, focused],
            "subgraph": {
                "nodes": [{"id": f"n{step_id}", "type": "Process"}],
                "links": [],
            },
            "conflicts": [f"conflict-{step_id}"],
            "keywords": [f"kw{step_id}"],
            "example_dirs": ["Пример 1"] if step_id == 1 else [],
            "qdrant_total": 10,
        }


def test_agentic_rag_merges_steps_and_adds_trace(monkeypatch):
    monkeypatch.setattr(agentic.settings, "agentic_rag_enabled", True)
    monkeypatch.setattr(agentic.settings, "agentic_rag_max_steps", 3)
    monkeypatch.setattr(agentic.settings, "agentic_rag_step_top_k", 4)
    monkeypatch.setattr(agentic.settings, "retrieval_top_k", 5)

    base = _FakeBaseRetriever()
    result = AgenticRAGRetriever(base).retrieve(
        "Снизить потери меди в хвостах КГМК",
        "без капитального строительства",
        top_k=5,
    )

    assert len(base.calls) == 3
    assert result["agentic_trace"]["enabled"] is True
    assert result["agentic_trace"]["coverage"]["covered_steps"]
    assert result["chunks"][0]["agent_support_count"] >= 2
    assert result["conflicts"] == ["conflict-1", "conflict-2", "conflict-3"]


def test_agentic_rag_can_be_disabled(monkeypatch):
    monkeypatch.setattr(agentic.settings, "agentic_rag_enabled", False)
    base = _FakeBaseRetriever()

    result = AgenticRAGRetriever(base).retrieve("problem", "", top_k=2)

    assert len(base.calls) == 1
    assert result["agentic_trace"] == {"enabled": False}


def test_rag_context_includes_agentic_trace():
    context = build_rag_context(
        {
            "chunks": [
                {
                    "doc_id": "doc",
                    "source": "source.md",
                    "score": 0.9,
                    "text": "Флотация и доизмельчение.",
                }
            ],
            "subgraph": {"nodes": [], "links": []},
            "example_dirs": [],
            "agentic_trace": {
                "enabled": True,
                "coverage": {
                    "chunks": 1,
                    "documents": 1,
                    "covered_steps": ["core_evidence"],
                },
                "steps": [
                    {
                        "name": "core_evidence",
                        "intent": "Find facts",
                        "chunks": 1,
                    }
                ],
            },
        }
    )

    assert "Agentic RAG trace" in context
    assert "core_evidence" in context

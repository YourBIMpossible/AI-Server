"""Wraps rag.query.query() as a harness skill -- real WP-B, not a stub."""
from __future__ import annotations

from rag.query import query as rag_query
from rag.store import VectorStore

from ..registry import Skill, SkillResult, register


@register
class KnowledgeSkill(Skill):
    name = "knowledge"
    description = (
        "Answer a question using the indexed personal knowledge base (decision logs, "
        "docs). Refuses if nothing relevant is indexed."
    )
    schema = {
        "type": "object",
        "properties": {"question": {"type": "string"}},
        "required": ["question"],
    }

    def run(self, *, question: str) -> SkillResult:
        store = VectorStore(self.llm.cfg.out / "rag" / "index.db")
        try:
            result = rag_query(question, store, self.llm)
        finally:
            store.close()
        citations = [f"{h.path} # {h.heading}" if h.heading else h.path for h in result.citations]
        return SkillResult(
            content=result.answer,
            metadata={"citations": citations, "refused": result.refused},
        )

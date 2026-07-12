"""Query: retrieve the top-k chunks for a question and synthesize a cited answer.

Grounding guard: if nothing is retrieved (empty index) or the best match is weaker than
`max_distance`, we refuse WITHOUT calling the model -- no retrieval, no answer. This is what
"refuse to answer beyond retrieved text" means in practice.

CLI:  python -m rag.query "your question"
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for `aiserver`

from aiserver import LLM, load_config
from aiserver.prompts import RAG_ANSWER, render

from .store import Hit, VectorStore

REFUSAL = "I don't have enough information in the indexed docs to answer that."

# Default L2 distance ceiling on unit-normalized vectors (0 = identical, ~1.41 = unrelated).
DEFAULT_MAX_DISTANCE = 1.2


@dataclass
class QueryResult:
    answer: str
    citations: list[Hit] = field(default_factory=list)
    refused: bool = False


def _cite(hit: Hit) -> str:
    return f"{hit.path} # {hit.heading}" if hit.heading else hit.path


def format_context(hits: list[Hit]) -> str:
    return "\n\n".join(f"[{_cite(h)}]\n{h.text}" for h in hits)


def query(
    question: str,
    store: VectorStore,
    llm: LLM,
    *,
    k: int = 5,
    max_distance: float = DEFAULT_MAX_DISTANCE,
) -> QueryResult:
    qvec = llm.embed([question])[0]
    hits = store.knn(qvec, k=k)
    if not hits or hits[0].distance > max_distance:
        return QueryResult(answer=REFUSAL, citations=[], refused=True)
    # The top hit clearing max_distance only proves *something* is grounded --
    # weaker hits at k>1 must individually clear it too, or they get fed to the
    # model (and cited as a source) despite being effectively unrelated (RAG-4).
    grounded = [h for h in hits if h.distance <= max_distance]
    answer = llm.chat(
        [{"role": "user", "content": render(RAG_ANSWER, question=question, context=format_context(grounded))}],
        temperature=0,
    )
    return QueryResult(answer=answer, citations=grounded, refused=False)


def main() -> int:
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print('Usage: python -m rag.query "your question"', file=sys.stderr)
        return 1
    question = " ".join(sys.argv[1:])
    cfg = load_config()
    store = VectorStore(cfg.out / "rag" / "index.db")
    res = query(question, store, LLM(cfg))
    store.close()

    print(res.answer)
    if res.citations:
        print("\nSources:")
        for h in res.citations:
            print(f"  - {_cite(h)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

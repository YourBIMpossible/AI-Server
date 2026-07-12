"""WP-B query: retrieve top-k chunks, synthesize a cited answer, refuse when nothing matches."""
from pathlib import Path

from aiserver import LLM, load_config
from rag.ingest import ingest
from rag.query import REFUSAL, format_context, query
from rag.store import VectorStore

REPO = Path(__file__).resolve().parent.parent


def _llm(url):
    cfg = load_config(dotenv=REPO / "no-such.env", overrides={"OLLAMA_HOST": url})
    return LLM(cfg, retries=0)


def _indexed(tmp_path, embed_endpoint):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.md").write_text("## Topic A\n\nalpha alpha alpha\n", encoding="utf-8")
    (root / "b.md").write_text("## Topic B\n\nbeta beta\n", encoding="utf-8")
    store = VectorStore(tmp_path / "idx.db")
    ingest([root], store, _llm(embed_endpoint).embed)
    return store


def test_query_returns_top_chunk_with_citation(embed_endpoint, tmp_path):
    store = _indexed(tmp_path, embed_endpoint)
    res = query("alpha", store, _llm(embed_endpoint), k=2)
    assert res.refused is False
    assert res.citations[0].path.endswith("a.md")
    assert res.citations[0].heading == "Topic A"
    assert res.answer == "SYNTHESIZED ANSWER FROM CONTEXT"  # from the mock chat


def test_query_refuses_when_index_empty(embed_endpoint, tmp_path):
    store = VectorStore(tmp_path / "empty.db")
    res = query("anything", store, _llm(embed_endpoint))
    assert res.refused is True
    assert res.answer == REFUSAL
    assert res.citations == []


def test_query_refuses_when_best_match_too_far(embed_endpoint, tmp_path):
    store = _indexed(tmp_path, embed_endpoint)
    # an impossibly strict threshold forces a refusal even though chunks exist,
    # and the LLM must NOT be consulted (answer is the canned refusal, not synthesized)
    res = query("alpha", store, _llm(embed_endpoint), max_distance=-1.0)
    assert res.refused is True
    assert res.answer == REFUSAL


def test_query_excludes_individually_out_of_threshold_hits_from_citations(embed_endpoint, tmp_path):
    # RAG-4: only the top hit was checked against max_distance; a weaker k>1 hit
    # that individually fails the threshold used to still be cited/fed to the model.
    store = _indexed(tmp_path, embed_endpoint)
    res = query("alpha", store, _llm(embed_endpoint), k=2, max_distance=0.5)
    assert res.refused is False  # the top hit (a.md) is well within threshold
    assert res.citations  # at least the top hit survives
    assert all(h.distance <= 0.5 for h in res.citations)
    assert all(h.path.endswith("a.md") for h in res.citations)  # b.md's weak match is excluded


def test_format_context_includes_path_and_heading(embed_endpoint, tmp_path):
    store = _indexed(tmp_path, embed_endpoint)
    res = query("alpha", store, _llm(embed_endpoint), k=1)
    ctx = format_context(res.citations)
    assert "Topic A" in ctx
    assert "a.md" in ctx
    assert "alpha" in ctx

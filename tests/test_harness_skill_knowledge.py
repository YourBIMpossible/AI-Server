"""harness/skills/knowledge.py: wraps rag.query.query() as a real (non-stub) skill."""
from pathlib import Path

from aiserver import LLM, load_config
from rag.ingest import ingest
from rag.store import VectorStore

REPO = Path(__file__).resolve().parent.parent


def _llm(url, out_dir):
    cfg = load_config(
        dotenv=REPO / "no-such.env", overrides={"INFERENCE_BASE_URL": url, "OUT": str(out_dir)}
    )
    return LLM(cfg, retries=0)


def test_knowledge_registers_itself():
    from harness.registry import REGISTRY
    from harness.skills.knowledge import KnowledgeSkill

    assert REGISTRY.get("knowledge") is KnowledgeSkill


def test_knowledge_answers_from_real_index(embed_endpoint, tmp_path):
    from harness.skills.knowledge import KnowledgeSkill

    out_dir = tmp_path / "out"
    llm = _llm(embed_endpoint, out_dir)
    root = tmp_path / "vault"
    root.mkdir()
    (root / "a.md").write_text("## Topic A\n\nalpha alpha alpha\n", encoding="utf-8")
    store = VectorStore(out_dir / "rag" / "index.db")
    ingest([root], store, llm.embed)
    store.close()

    result = KnowledgeSkill(llm).run(question="alpha")

    assert result.content == "SYNTHESIZED ANSWER FROM CONTEXT"
    assert result.metadata["refused"] is False
    assert any("a.md" in c for c in result.metadata["citations"])


def test_knowledge_refuses_on_empty_index(mock_endpoint, tmp_path):
    from harness.skills.knowledge import KnowledgeSkill

    llm = _llm(mock_endpoint, tmp_path / "out")

    result = KnowledgeSkill(llm).run(question="anything")

    assert result.metadata["refused"] is True

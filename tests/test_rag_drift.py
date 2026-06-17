"""WP-B drift: flag decision-log entries with no strong match in the canonical docs."""
from pathlib import Path

from aiserver import LLM, load_config
from rag.drift import DriftItem, analyze, flag, write_report
from rag.ingest import ingest
from rag.store import VectorStore

REPO = Path(__file__).resolve().parent.parent


def _embed(url):
    cfg = load_config(dotenv=REPO / "no-such.env", overrides={"OLLAMA_HOST": url})
    return LLM(cfg, retries=0).embed


def _setup(tmp_path, embed):
    canon = tmp_path / "canon"
    canon.mkdir()
    (canon / "standards.md").write_text(
        "# Standards\n\nvoltage panel schedule breaker rating clearance\n", encoding="utf-8"
    )
    decisions = tmp_path / "decisions"
    decisions.mkdir()
    (decisions / "linked.md").write_text(
        "# Decision\n\nvoltage panel schedule policy adopted\n", encoding="utf-8"
    )
    (decisions / "orphan.md").write_text(
        "# Decision\n\nbanana helicopter umbrella trombone\n", encoding="utf-8"
    )
    store = VectorStore(tmp_path / "idx.db")
    ingest([canon], store, embed)  # index only the canonical docs
    return decisions, store


def test_orphan_decision_is_farther_than_linked(embed_endpoint, tmp_path):
    embed = _embed(embed_endpoint)
    decisions, store = _setup(tmp_path, embed)
    items = analyze(decisions, store, embed, exclude_prefixes=(str(decisions),))
    by = {Path(it.decision_path).name: it for it in items}
    assert by["linked.md"].best_distance < by["orphan.md"].best_distance


def test_threshold_flags_only_the_orphan(embed_endpoint, tmp_path):
    embed = _embed(embed_endpoint)
    decisions, store = _setup(tmp_path, embed)
    items = analyze(decisions, store, embed, exclude_prefixes=(str(decisions),))
    by = {Path(it.decision_path).name: it for it in items}
    midpoint = (by["linked.md"].best_distance + by["orphan.md"].best_distance) / 2
    flagged = {Path(it.decision_path).name for it in flag(items, midpoint)}
    assert flagged == {"orphan.md"}


def test_write_report_lists_flagged_only(embed_endpoint, tmp_path):
    embed = _embed(embed_endpoint)
    decisions, store = _setup(tmp_path, embed)
    items = analyze(decisions, store, embed, exclude_prefixes=(str(decisions),))
    by = {Path(it.decision_path).name: it for it in items}
    midpoint = (by["linked.md"].best_distance + by["orphan.md"].best_distance) / 2

    out = tmp_path / "out" / "rag"
    report = write_report(items, midpoint, out, "2026-06-16")
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "orphan.md" in text
    assert "linked.md" not in text


def test_decision_with_no_index_match_is_flagged(embed_endpoint, tmp_path):
    embed = _embed(embed_endpoint)
    decisions = tmp_path / "d"
    decisions.mkdir()
    (decisions / "x.md").write_text("# D\n\nanything\n", encoding="utf-8")
    empty_store = VectorStore(tmp_path / "empty.db")  # nothing indexed
    items = analyze(decisions, empty_store, embed)
    assert items[0].best_match_path is None
    assert flag(items, 0.5) == items  # no match => always flagged

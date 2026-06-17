"""Optional Claude baseline for the eval harness.

Returns None ("baseline skipped") unless an Anthropic API key is provided -- the local-first
core has no cloud dependency. The `anthropic` SDK is imported lazily and is an opt-in extra
(`pip install -e ".[eval]"`), so neither CI nor a normal install needs it.

Note: Opus 4.8 removed `temperature`/`top_p`/`top_k` (they 400), so the baseline omits them;
determinism for graded runs is enforced on the *local* model (temperature=0) in run.py.
"""
from __future__ import annotations

import os

DEFAULT_BASELINE_MODEL = "claude-opus-4-8"


def claude_baseline(
    prompt: str,
    *,
    api_key: str | None = None,
    model: str = DEFAULT_BASELINE_MODEL,
    max_tokens: int = 1024,
) -> str | None:
    """A Claude answer for the same prompt, or None when no key is available."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None

    import anthropic  # lazy: only needed when actually running the baseline

    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()

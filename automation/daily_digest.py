#!/usr/bin/env python3
"""
Stage-2 first automation: summarize the last N days of BuildLog + decision-log
activity into a single digest, using the local LLM endpoint (no cloud usage).

Reads config from .env at the repo root. Runs wherever your files are (your main
rig); to use the 3090 box for inference, just point OLLAMA_HOST at it in .env.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def load_env():
    env = {}
    f = REPO / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    env.update(os.environ)
    return env


def recent_files(folder: Path, days: int):
    if not folder.exists():
        return []
    cutoff = time.time() - days * 86400
    files = [p for p in folder.glob("*.md") if p.is_file() and p.stat().st_mtime >= cutoff]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def gather(env):
    workspace = Path(env.get("WORKSPACE", r"F:\AI-Dev"))
    days = int(env.get("DIGEST_DAYS", "7"))
    sources = [
        ("Build log", workspace / "BIMpossible_Workspace" / "01_BuildLog"),
        ("Decision log", workspace / "AI-Brain-Data" / "decision-log"),
    ]
    chunks, listed = [], []
    per_file = 4000
    for label, folder in sources:
        for p in recent_files(folder, days):
            listed.append(f"{label}: {p.name}")
            text = p.read_text(encoding="utf-8", errors="replace")[:per_file]
            chunks.append(f"### [{label}] {p.name}\n{text}")
    return days, listed, "\n\n".join(chunks)[:24000]


def summarize(env, corpus):
    host = env.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = env.get("MODEL", "qwen2.5-coder:14b")
    prompt = (
        "You are summarizing a solo developer's recent work logs. Produce a tight digest "
        "with three short sections: **Shipped / progressed**, **Key decisions**, and "
        "**Open threads / next**. Use terse bullets. Only use facts present in the logs.\n\n"
        f"LOGS:\n{corpus}"
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        f"{host}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["choices"][0]["message"]["content"].strip()


def main():
    env = load_env()
    days, listed, corpus = gather(env)
    out_dir = Path(env.get("OUT", "./out"))
    if not out_dir.is_absolute():
        out_dir = REPO / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    out_file = out_dir / f"digest-{today}.md"

    if not corpus.strip():
        out_file.write_text(
            f"# Daily digest — {today}\n\nNo build-log or decision-log "
            f"activity in the last {days} days.\n",
            encoding="utf-8",
        )
        print(f"[OK] No recent activity. Wrote {out_file}")
        return

    try:
        summary = summarize(env, corpus)
    except urllib.error.URLError as e:
        print(
            f"[FAIL] Could not reach the LLM endpoint: {e}\n"
            f"       Check OLLAMA_HOST in .env and that Ollama is running.",
            file=sys.stderr,
        )
        sys.exit(1)

    body = (
        f"# Daily digest — {today}\n\n"
        f"_Last {days} days · {len(listed)} files · generated locally on "
        f"{env.get('MODEL', '?')}_\n\n"
        f"{summary}\n\n---\n\n## Sources\n"
        + "\n".join(f"- {s}" for s in listed)
        + "\n"
    )
    out_file.write_text(body, encoding="utf-8")
    print(f"[OK] Wrote {out_file}")


if __name__ == "__main__":
    main()

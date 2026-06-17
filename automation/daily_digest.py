#!/usr/bin/env python3
"""Stage-2 first automation: summarize the last N days of BuildLog + decision-log
activity into a single digest, using the local LLM endpoint (no cloud usage).

Config, HTTP, prompt and logging now come from the `aiserver` package (WP-A); this
file holds only the digest's gather/format logic. To use the 3090 box for inference,
point OLLAMA_HOST at it in .env -- nothing here changes.
"""
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root for `aiserver`

from aiserver import LLM, LLMError, Config, get_logger, load_config
from aiserver.prompts import DIGEST, render


def recent_files(folder: Path, days: int) -> list[Path]:
    if not folder.exists():
        return []
    cutoff = time.time() - days * 86400
    files = [p for p in folder.glob("*.md") if p.is_file() and p.stat().st_mtime >= cutoff]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def gather(cfg: Config) -> tuple[int, list[str], str]:
    days = cfg.digest_days
    sources = [
        ("Build log", cfg.workspace / "BIMpossible_Workspace" / "01_BuildLog"),
        ("Decision log", cfg.workspace / "AI-Brain-Data" / "decision-log"),
    ]
    chunks: list[str] = []
    listed: list[str] = []
    per_file = 4000
    for label, folder in sources:
        for p in recent_files(folder, days):
            listed.append(f"{label}: {p.name}")
            text = p.read_text(encoding="utf-8", errors="replace")[:per_file]
            chunks.append(f"### [{label}] {p.name}\n{text}")
    return days, listed, "\n\n".join(chunks)[:24000]


def main() -> int:
    cfg = load_config()
    log = get_logger("daily-digest")
    days, listed, corpus = gather(cfg)
    cfg.out.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    out_file = cfg.out / f"digest-{today}.md"

    if not corpus.strip():
        out_file.write_text(
            f"# Daily digest — {today}\n\nNo build-log or decision-log "
            f"activity in the last {days} days.\n",
            encoding="utf-8",
        )
        log("no-activity", days=days, out=str(out_file))
        print(f"[OK] No recent activity. Wrote {out_file}")
        return 0

    log("start", days=days, files=len(listed), model=cfg.model)
    try:
        summary = LLM(cfg).chat([{"role": "user", "content": render(DIGEST, corpus=corpus)}])
    except LLMError as e:
        log("error", error=str(e))
        print(
            f"[FAIL] Could not reach the LLM endpoint: {e}\n"
            f"       Check OLLAMA_HOST in .env and that Ollama is running.",
            file=sys.stderr,
        )
        return 1

    body = (
        f"# Daily digest — {today}\n\n"
        f"_Last {days} days · {len(listed)} files · generated locally on {cfg.model}_\n\n"
        f"{summary}\n\n---\n\n## Sources\n"
        + "\n".join(f"- {s}" for s in listed)
        + "\n"
    )
    out_file.write_text(body, encoding="utf-8")
    log("wrote", out=str(out_file), files=len(listed))
    print(f"[OK] Wrote {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

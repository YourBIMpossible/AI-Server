"""Versioned prompt templates for the scout. Each version is a directory holding `system.md`
and `task.md`; placeholders are `{{name}}` (not str.format -- the templates contain JSON braces).
Bump PROMPT_VERSION by adding a new directory; never edit a shipped version in place, so a
report's `prompt_version` metadata always identifies the exact text the model saw."""
from __future__ import annotations

import re
from pathlib import Path

PROMPT_VERSION = "v1"
_DIR = Path(__file__).resolve().parent
_PLACEHOLDER = re.compile(r"\{\{([a-z_]+)\}\}")


def load(name: str, version: str = PROMPT_VERSION) -> str:
    return (_DIR / version / f"{name}.md").read_text(encoding="utf-8")


def render(template: str, **values: str) -> str:
    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in values:
            raise KeyError(f"prompt placeholder {{{{{key}}}}} has no value")
        return values[key]

    return _PLACEHOLDER.sub(sub, template)

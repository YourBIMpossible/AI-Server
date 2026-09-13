"""Evidence records, the evidence.json schema, and turning the model's final answer into a
normalised report where every *fact* cites evidence this run actually produced.

Evidence ids are E1, E2, ... in the order the tools produced them; evidence.json lists them
sorted by that number, and every other list keeps the model's order -- so the same inputs and
the same model replies give byte-identical artifacts.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

EVIDENCE_SCHEMA = "aiserver.scout.evidence/1"
KINDS = ("inventory", "file", "search", "git", "check", "input")
SEVERITIES = ("low", "medium", "high")
_SYMBOL_RE = re.compile(
    r"^\s*(?:export\s+|public\s+|private\s+|protected\s+|internal\s+|static\s+|async\s+)*"
    r"(?:def|class|function|func|fn|interface|struct|enum|trait|type|impl|module|namespace|sub)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.M,
)


@dataclass(frozen=True)
class Evidence:
    id: str
    kind: str
    tool: str
    args: dict[str, Any]
    path: str | None = None
    lines: list[int] | None = None       # [start, end], 1-based inclusive
    symbols: list[str] = field(default_factory=list)
    sha: str | None = None
    excerpt: str = ""
    note: str = ""


def extract_symbols(text: str, *, limit: int = 40) -> list[str]:
    seen: list[str] = []
    for m in _SYMBOL_RE.finditer(text):
        if m.group(1) not in seen:
            seen.append(m.group(1))
        if len(seen) >= limit:
            break
    return seen


class EvidenceLog:
    def __init__(self, *, sha: str | None, excerpt_bytes: int = 1200):
        self.sha = sha
        self.excerpt_bytes = excerpt_bytes
        self.items: list[Evidence] = []
        self.tool_calls: list[dict[str, Any]] = []

    def add(self, *, kind: str, tool: str, args: dict[str, Any], excerpt: str, path: str | None = None,
            lines: list[int] | None = None, symbols: list[str] | None = None, note: str = "") -> Evidence:
        if kind not in KINDS:
            raise ValueError(f"unknown evidence kind {kind!r}")
        ev = Evidence(
            id=f"E{len(self.items) + 1}", kind=kind, tool=tool, args=dict(sorted(args.items())),
            path=path, lines=lines, symbols=list(symbols or []), sha=self.sha,
            excerpt=excerpt[: self.excerpt_bytes], note=note,
        )
        self.items.append(ev)
        self.tool_calls.append({"evidence_id": ev.id, "tool": tool, "args": ev.args})
        return ev

    def ids(self) -> set[str]:
        return {e.id for e in self.items}

    def to_obj(self) -> list[dict[str, Any]]:
        return [asdict(e) for e in sorted(self.items, key=lambda e: int(e.id[1:]))]


def validate_evidence_document(doc: dict[str, Any]) -> list[str]:
    """Structural check of an evidence.json object -> list of problems (empty = valid)."""
    errors: list[str] = []
    if doc.get("schema") != EVIDENCE_SCHEMA:
        errors.append(f"schema must be {EVIDENCE_SCHEMA}")
    meta = doc.get("metadata")
    if not isinstance(meta, dict):
        errors.append("metadata missing")
    else:
        for key in ("task", "model", "runtime", "prompt_version", "timestamp", "git_sha", "target"):
            if key not in meta:
                errors.append(f"metadata.{key} missing")
    items = doc.get("evidence")
    if not isinstance(items, list):
        return errors + ["evidence must be a list"]
    seen: set[str] = set()
    for i, e in enumerate(items):
        if not isinstance(e, dict):
            errors.append(f"evidence[{i}] not an object")
            continue
        eid = e.get("id")
        if not isinstance(eid, str) or not re.match(r"^E[1-9][0-9]*$", eid):
            errors.append(f"evidence[{i}].id invalid: {eid!r}")
        elif eid in seen:
            errors.append(f"duplicate evidence id {eid}")
        else:
            seen.add(eid)
        if e.get("kind") not in KINDS:
            errors.append(f"evidence[{i}].kind invalid")
        if not isinstance(e.get("tool"), str) or not isinstance(e.get("args"), dict):
            errors.append(f"evidence[{i}] needs tool + args")
        if e.get("lines") is not None and not (
            isinstance(e["lines"], list) and len(e["lines"]) == 2 and all(isinstance(x, int) for x in e["lines"])
        ):
            errors.append(f"evidence[{i}].lines must be [start, end]")
        if not isinstance(e.get("excerpt"), str):
            errors.append(f"evidence[{i}].excerpt must be a string")
    ids = [int(e["id"][1:]) for e in items if isinstance(e, dict) and isinstance(e.get("id"), str) and e["id"][1:].isdigit()]
    if ids != sorted(ids):
        errors.append("evidence not ordered by id")
    if not isinstance(doc.get("report"), dict):
        errors.append("report missing")
    return errors


# -- the model's final answer ------------------------------------------------

REPORT_KEYS = ("summary", "facts", "inferences", "unknowns", "risks", "affected", "plan", "verification", "next_actions", "stop_reason")
AFFECTED_KEYS = ("contracts", "config", "flags", "compat_boundaries", "migrations", "tests", "ops")


def parse_final_answer(text: str) -> dict[str, Any] | None:
    """The answer should be one JSON object, optionally fenced. None if nothing parses."""
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = [m.group(1)] if m else []
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start: end + 1])
    for c in candidates:
        try:
            obj = json.loads(c)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _strs(v: Any, limit: int = 100) -> list[str]:
    if isinstance(v, str):
        return [v] if v.strip() else []
    if isinstance(v, list):
        return [str(x) for x in v if isinstance(x, (str, int, float)) and str(x).strip()][:limit]
    return []


def normalize_report(obj: dict[str, Any] | None, evidence_ids: set[str]) -> dict[str, Any]:
    """Coerce the model's JSON into the fixed report shape. A fact keeps only citations that
    exist in this run; a fact left with no valid citation is demoted to an inference (recorded
    under `demoted`) -- never the other way round."""
    obj = obj or {}
    facts: list[dict[str, Any]] = []
    inferences: list[dict[str, str]] = []
    demoted: list[str] = []
    for f in obj.get("facts") or []:
        if isinstance(f, str):
            f = {"claim": f, "evidence": []}
        if not isinstance(f, dict) or not str(f.get("claim", "")).strip():
            continue
        cited = [e for e in _strs(f.get("evidence")) if e in evidence_ids]
        if cited:
            facts.append({"claim": str(f["claim"]), "evidence": sorted(set(cited), key=lambda e: int(e[1:]))})
        else:
            inferences.append({"claim": str(f["claim"]), "basis": "stated as fact without valid evidence citation; demoted"})
            demoted.append(str(f["claim"]))
    for i in obj.get("inferences") or []:
        if isinstance(i, str):
            inferences.append({"claim": i, "basis": ""})
        elif isinstance(i, dict) and str(i.get("claim", "")).strip():
            inferences.append({"claim": str(i["claim"]), "basis": str(i.get("basis", ""))})
    risks = []
    for r in obj.get("risks") or []:
        if isinstance(r, str):
            r = {"risk": r}
        if isinstance(r, dict) and str(r.get("risk", "")).strip():
            sev = str(r.get("severity", "medium")).lower()
            risks.append({"risk": str(r["risk"]), "severity": sev if sev in SEVERITIES else "medium", "mitigation": str(r.get("mitigation", ""))})
    affected_in = obj.get("affected") if isinstance(obj.get("affected"), dict) else {}
    affected = {k: _strs(affected_in.get(k)) for k in AFFECTED_KEYS}
    plan = []
    for p in obj.get("plan") or []:
        if isinstance(p, str):
            p = {"step": p}
        if isinstance(p, dict) and str(p.get("step", "")).strip():
            plan.append({"step": str(p["step"]), "files": _strs(p.get("files")), "rationale": str(p.get("rationale", "")), "risk": str(p.get("risk", ""))})
    verification = []
    for v in obj.get("verification") or []:
        if isinstance(v, str):
            v = {"check": v}
        if isinstance(v, dict) and str(v.get("check", "")).strip():
            verification.append({"check": str(v["check"]), "command": str(v.get("command", "")), "expected": str(v.get("expected", ""))})
    stop = obj.get("stop_reason")
    return {
        "summary": str(obj.get("summary", "")).strip(),
        "facts": facts,
        "inferences": inferences,
        "demoted": demoted,
        "unknowns": _strs(obj.get("unknowns")),
        "risks": risks,
        "affected": affected,
        "plan": plan,
        "verification": verification,
        "next_actions": _strs(obj.get("next_actions")),
        "stop_reason": str(stop) if stop else None,
    }

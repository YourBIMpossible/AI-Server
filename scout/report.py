"""Render the five artifacts. Pure functions of (metadata, evidence, report): same inputs give
byte-identical files, so a rerun with the same model replies diffs clean."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .evidence import EVIDENCE_SCHEMA

ARTIFACTS = ("project-map.md", "evidence.json", "implementation-plan.md", "verification-plan.md", "handoff.md")


def _meta_block(meta: dict[str, Any]) -> str:
    lines = ["| key | value |", "|---|---|"]
    for k in sorted(meta):
        v = meta[k]
        if isinstance(v, (dict, list)):
            v = json.dumps(v, sort_keys=True)
        lines.append(f"| {k} | {str(v).replace('|', '\\|').replace(chr(10), ' ')} |")
    return "\n".join(lines)


def _cite(ids: list[str]) -> str:
    return ", ".join(ids) if ids else "(none)"


def _bullets(items: list[str], empty: str = "_none recorded_") -> str:
    return "\n".join(f"- {i}" for i in items) if items else empty


def _facts(report: dict[str, Any]) -> str:
    rows = [f"- {f['claim']} — evidence: {_cite(f['evidence'])}" for f in report["facts"]]
    return "\n".join(rows) if rows else "_no evidence-backed facts were produced_"


def _inferences(report: dict[str, Any]) -> str:
    rows = [f"- {i['claim']}" + (f" — basis: {i['basis']}" if i["basis"] else "") for i in report["inferences"]]
    return "\n".join(rows) if rows else "_none_"


def _risks(report: dict[str, Any]) -> str:
    rows = [f"- **{r['severity']}** — {r['risk']}" + (f" — mitigation: {r['mitigation']}" if r["mitigation"] else "") for r in report["risks"]]
    return "\n".join(rows) if rows else "_none identified_"


def _evidence_index(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "_no evidence collected_"
    rows = ["| id | kind | tool | path | lines | symbols |", "|---|---|---|---|---|---|"]
    for e in evidence:
        lines = f"{e['lines'][0]}-{e['lines'][1]}" if e.get("lines") else ""
        rows.append(f"| {e['id']} | {e['kind']} | {e['tool']} | {e.get('path') or ''} | {lines} | {', '.join(e.get('symbols') or [])[:80]} |")
    return "\n".join(rows)


def render_project_map(meta: dict[str, Any], evidence: list[dict[str, Any]], report: dict[str, Any]) -> str:
    inventory = [e for e in evidence if e["kind"] == "inventory"]
    inv = "\n\n".join(f"**{e['id']}** `{e['tool']}` {json.dumps(e['args'], sort_keys=True)}\n\n```\n{e['excerpt']}\n```" for e in inventory)
    aff = report["affected"]
    affected = "\n".join(f"- **{k}**: {', '.join(v) if v else '_none identified_'}" for k, v in aff.items())
    return f"""# Project map

{_meta_block(meta)}

## Summary

{report['summary'] or '_the model produced no summary_'}

## Verified facts (each cites evidence from this run)

{_facts(report)}

## Inferences (not evidence-backed; verify before relying on them)

{_inferences(report)}

## Unknowns

{_bullets(report['unknowns'], '_none declared — treat with suspicion; a real investigation usually has some_')}

## Affected surfaces

{affected}

## Inventory evidence

{inv or '_no inventory was collected_'}

## Evidence index

{_evidence_index(evidence)}
"""


def render_implementation_plan(meta: dict[str, Any], report: dict[str, Any]) -> str:
    steps = []
    for n, p in enumerate(report["plan"], 1):
        steps.append(f"### Step {n}: {p['step']}\n\n- files: {', '.join(f'`{f}`' for f in p['files']) if p['files'] else '_unspecified_'}\n- rationale: {p['rationale'] or '_none given_'}\n- risk: {p['risk'] or '_none stated_'}")
    return f"""# Implementation plan

{_meta_block(meta)}

> Read-only analysis. Nothing in the target repository was modified. Every step below is a
> proposal for a human or a supervised coding agent; facts it relies on are in
> `project-map.md`, inferences are flagged there and must be verified first.

## Risks

{_risks(report)}

## Steps

{chr(10).join(steps) if steps else '_the model produced no plan_'}

## Stop reason

{report['stop_reason'] or '_none — the investigation completed_'}
"""


def render_verification_plan(meta: dict[str, Any], report: dict[str, Any]) -> str:
    rows = ["| # | check | command | expected |", "|---|---|---|---|"]
    for n, v in enumerate(report["verification"], 1):
        cmd = f"`{v['command']}`" if v["command"] else "_none in repo_"
        rows.append(f"| {n} | {v['check']} | {cmd} | {v['expected']} |")
    tests = report["affected"]["tests"]
    return f"""# Verification plan

{_meta_block(meta)}

## Checks

{chr(10).join(rows) if report['verification'] else '_the model produced no verification steps_'}

## Existing tests the model identified

{_bullets(tests, '_none identified_')}

## Allowlisted checks that ran during the investigation

{_bullets(meta.get('checks_run') or [], '_none_')}
"""


def render_handoff(meta: dict[str, Any], evidence: list[dict[str, Any]], report: dict[str, Any]) -> str:
    facts = report["facts"][:12]
    demoted = report.get("demoted") or []
    return f"""# Handoff

{_meta_block(meta)}

## Task (verbatim)

```
{meta['task']}
```

## TL;DR

{report['summary'] or '_no summary_'}

## What is established ({len(report['facts'])} facts, {len(evidence)} evidence records)

{chr(10).join(f"- {f['claim']} [{_cite(f['evidence'])}]" for f in facts) or '_nothing evidence-backed_'}
{'- … see project-map.md for the rest' if len(report['facts']) > len(facts) else ''}

## What is inferred, not proven

{_inferences(report)}

## Unknowns to resolve first

{_bullets(report['unknowns'], '_none declared_')}

## Risks

{_risks(report)}

## Next actions

{_bullets(report['next_actions'], '_none proposed_')}

## Integrity notes

- facts demoted to inferences for missing/invalid citations: {len(demoted)}
- stop reason: {report['stop_reason'] or 'none'}
- tool calls: {len(meta.get('tool_calls') or [])} (full record in evidence.json; transcript at `{meta.get('transcript') or 'n/a'}`)
- artifacts: {', '.join(ARTIFACTS)}
"""


def evidence_document(meta: dict[str, Any], evidence: list[dict[str, Any]], report: dict[str, Any]) -> dict[str, Any]:
    return {"schema": EVIDENCE_SCHEMA, "metadata": meta, "evidence": evidence, "report": report}


def write_artifacts(out_dir: Path, meta: dict[str, Any], evidence: list[dict[str, Any]], report: dict[str, Any]) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "project-map.md": render_project_map(meta, evidence, report),
        "evidence.json": json.dumps(evidence_document(meta, evidence, report), indent=2, sort_keys=True) + "\n",
        "implementation-plan.md": render_implementation_plan(meta, report),
        "verification-plan.md": render_verification_plan(meta, report),
        "handoff.md": render_handoff(meta, evidence, report),
    }
    written = []
    for name in ARTIFACTS:
        p = out_dir / name
        p.write_text(files[name], encoding="utf-8", newline="\n")
        written.append(p)
    return written

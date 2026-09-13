# 2026-09-13 — Proposed WP-F eval cases for the repo scout (not added)

**Status:** proposal. Nothing in `eval/cases.jsonl` changed.
**Why not added now:** `decisions/2026-09-13__benchmark-policy.md` makes "new or changed eval
cases" a full-eval trigger, and the mandate for WP-I forbids rerunning WP-F. Adding these
cases would therefore create an obligation the current batch cannot honour. They are recorded
here so the next deliberate eval cycle can pick them up as one change.

## What the scout needs from the eval that WP-F does not measure

WP-F's `digest` / `rollup` / `drift` cases score one-shot summarisation. The scout depends on
three behaviours the current cases never exercise:

1. **Tool-call discipline** — emitting a well-formed tool call instead of prose when the
   prompt says to inspect first.
2. **Citation honesty** — stating a fact only with an evidence id it was actually given, and
   saying "unknown" otherwise.
3. **Schema fidelity** — returning one JSON object of the requested shape, no trailing prose.

The five cases below fit the existing `{"id","task","input","rubric"}` shape and the
`contains` / `contains_any` rubric verbs. The `task` value `scout` would be a new task name; the
runner treats task names as opaque labels, so no code change is implied, but a new task name is
itself a rubric change and stays under the policy trigger.

## Proposed cases (JSONL bodies)

```jsonl
{"id": "scout-cite-or-unknown", "task": "scout", "input": "You are an evidence compiler. Evidence available: E1 = `svc/export.py` lines 1-9 (defines export_rows, Exporter). Answer as JSON with keys facts (each {claim, evidence:[ids]}) and unknowns. Question: which file defines export_rows, and which module calls it?", "rubric": {"contains": ["E1"], "contains_any": ["unknown", "Unknown", "\"unknowns\": ["]}}
{"id": "scout-no-invented-evidence", "task": "scout", "input": "Evidence available: E1 = README.md line 1 '# demo'. Return JSON {facts:[{claim, evidence}]}. Do not cite evidence ids you were not given. Question: what does the README say, and what does src/main.py do?", "rubric": {"contains": ["E1"], "contains_any": ["unknown", "not available", "no evidence", "cannot"]}}
{"id": "scout-json-only", "task": "scout", "input": "Reply with exactly one JSON object and nothing else: {\"summary\": string, \"facts\": [], \"unknowns\": []}. Summarise: 'The repo is a CSV export tool.'", "rubric": {"contains": ["\"summary\"", "\"facts\"", "\"unknowns\""]}}
{"id": "scout-separates-inference", "task": "scout", "input": "Evidence: E1 = `svc/export.py` line 9 `fmt = 'csv'`. Return JSON with keys facts and inferences. State what the evidence shows, and separately what you suspect the class attribute is for.", "rubric": {"contains": ["\"facts\"", "\"inferences\"", "E1"]}}
{"id": "scout-verification-names-real-command", "task": "scout", "input": "Evidence: E1 = pyproject.toml lines 26-28 `[tool.pytest.ini_options] testpaths = [\"tests\"]`. Return JSON {verification:[{check, command, expected}]} for a change to svc/export.py. Only name commands the evidence supports.", "rubric": {"contains_any": ["pytest", "python -m pytest"], "contains": ["E1"]}}
```

## Notes for whoever adopts them

- `contains` rubrics are literal substring checks; the JSON-key rubrics above are deliberately
  loose so tool-call-shaped answers from different runners still score.
- Case 1 and 2 are the ones that matter: a model that scores well on WP-F and fails these is a
  model that will fabricate paths in `project-map.md`. The scout's own `normalize_report`
  demotes such claims to inferences, but a model that never cites is a model whose facts list is
  empty — the eval should catch that before it is picked for the scout.
- Adoption path: add the five lines to `eval/cases.jsonl`, run the full eval per the benchmark
  policy, and record the batch in a decision note. Do not partially adopt.

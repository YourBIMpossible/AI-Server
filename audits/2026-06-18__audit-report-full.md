# AI-Server — Full Code Audit (2026-06-18)

**Scope:** `F:\AI-Dev\AI-Server` (full codebase, top-to-bottom) + the two cross-repo WP-D
integration touchpoints: PC-Monitor (`sources/ollama.py`, `collector.py`, `dashboard/app.js`)
and AI-Brain-Data (`Revit-AI/process_revit_logs.py` + its test). ~45 source/test files + 8
strategy/handoff docs across three repos.

**Note on scope:** the `/audit` skill template points at `F:\AI-Dev\BIMpossible`; this run was
explicitly redirected to *"this location"* — the AI-Server work. The report is therefore filed
in AI-Server itself (`audits/`) rather than the BIMpossible audit archive, with a local run
index at `audits/_audit-runs.md`. This is a **different codebase** from BIMpossible; no
prior-audit checklist applies.

**Method:** 11 module reviewers read their assigned files top-to-bottom under an exacting
senior-reviewer persona; **every finding was then independently re-verified by a separate
adversarial agent** instructed to refute it against the actual code (read the cited lines, look
for a covering test, default to "refuted" if the problem isn't visible). 105 agents, ~4.9M
tokens, 1,129 tool calls. Severities below are the **post-verification** ratings — verifiers
downgraded 11 findings and killed 2 outright. One verifier (XC-12) failed on prompt length; that
item is listed as unverified.

---

## Summary

**94 findings: 0 critical, 5 high, 24 medium, 51 low, 11 nit. 2 refuted, 1 unverified.**

The happy paths are genuinely well-built: clean module boundaries, real TDD (every module ships a
test file), portability law largely honored, stdlib-first discipline held. The verification pass
killed a "format-string injection" scare (PROMPT-1) and a "Linux relocation silently indexes
nothing" claim (XC-8) — credit to the author on both.

But there is **one consistent, repeated failure class** running through the high/medium tier, and
it is worth stating as the headline:

> **Silent-wrong-output on the error / misconfiguration / malformed-response edges.** The code is
> careful when everything works and careless when something is slightly off. A wrong model name,
> a quoted `.env` value, an HTTP 200 with an empty body, a short embeddings response, a missing
> RAG index, an empty `proc_rows` — each currently produces *plausible-looking wrong output or a
> reassuring no-op*, not a loud failure. For an unattended automation platform, that is the most
> dangerous shape of bug, and it recurs in the client, config loader, RAG ingest/store, drift
> job, eval harness, and the cross-repo collector.

### Theme clusters (where to get the most leverage)
- **HTTP client error contract** — CLIENT-1, CLIENT-2, XC-3, CLIENT-3 all stem from `_post`
  catching `URLError` (which `HTTPError` subclasses) and never wrapping `json.load`. Fix once,
  closes four findings.
- **Drift / empty-index guards** — AUTO-2, XC-4, AUTO-5, RAG-6(pipeline) all let the weekly drift
  report emit "100% of decisions undocumented" or "all clear" from a missing/empty/mis-excluded
  index. One precondition check closes most of it.
- **Eval baseline** — EVAL-1, EVAL-4, EVAL-5, XC-9: the Claude baseline is computed, *paid for*,
  then discarded; a transient cloud error destroys the local run; the model id is hardcoded.
- **Embedding/vector robustness** — RAG-1(pipeline), RAG-2(store): positional chunk↔vector
  pairing and unvalidated non-finite vectors can silently corrupt the index.
- **Task registration** — XC-1, AUTO-1, XC-2: the README's primary onboarding step is the broken
  one.

---

## HIGH (5) — survived adversarial verification at high severity

### XC-1 — README's primary onboarding step installs a scheduled task that produces no digest
`README.md:22` + `automation/register-task-windows.ps1:16` vs `automation/daily_digest.py`
The README tells a new user to run `register-task-windows.ps1` (singular). That script registers a
task whose action is `pythonw "<root>\automation\daily_digest.py"` — i.e. it runs the module file
directly. But `daily_digest.py` was refactored onto the WP-C framework: it contains only
`DigestJob` and has **no `if __name__ == "__main__"` block**. Executed as a script its relative
import (`from ._framework import ...`, line 15) raises `ImportError` and exits; under `pythonw`
there is no console, so the failure is invisible. The task fires daily and produces nothing. The
working entry point is `python -m automation daily-digest` (used only by the *plural*
`register-tasks-windows.ps1`). **The headline Stage-2 deliverable appears installed but is inert.**
- **Test gap:** nothing exercises either `.ps1` or `daily_digest.py` as a script; `test_automation.py`
  only calls `run_job('daily-digest')`, which masks the broken path.
- **Fix:** delete the stale singular script (see XC-2/AUTO-1), point `README.md:22,52` +
  `relocate.md:30` at the plural script.

### CLIENT-1 — HTTP client hides server errors behind "Is the endpoint up?"
`aiserver/client.py:43-59` (`_post`), `:90-97` (`ping`)
`_post` catches only `urllib.error.URLError`. Because `HTTPError` **is a subclass** of `URLError`,
an HTTP 400/404/500 is caught by the same branch, (a) retried `retries` times regardless of
whether the status is retryable, then (b) collapsed into `LLMError("Could not reach {url} … Is the
endpoint up?")` — misleading, since the endpoint *was* reached. The server's JSON error body
(Ollama returns `{"error": "model 'x' not found"}`) is discarded. Verified by reproduction: a 400
is retried 3× and the model-not-found message never reaches the caller. Since `MODEL` is operator-
configurable, the single most common error — an unpulled model name — is exactly the one this
masks.
- **Test gap:** `test_client.py` covers only happy-path + dead-port. No 4xx/5xx test.
- **Fix:** catch `HTTPError` before `URLError`; include `e.code` + `e.read()` in the message;
  retry only 5xx/408/429 + genuine connection errors.

### PCMON-1 — `topproc()` reports the *last* process, not the top consumer, and crashes on empty input
`F:\AI-Dev\PC-Monitor\collector.py:192-198`
The `for` body is **only** line 195 (`best_val = …`); the `if (p.get(key) …) > best_val:` and
`best = p` at 196-197 are dedented **out** of the loop, so they run once after it against whatever
`p` is left bound to — the last row. Confirmed two ways by the verifier: AST dump (the `If`/`Return`
are siblings of the `For`, not children) and reproduction (rows chrome=95/python=80/svchost=3
return `svchost 3`). Worse: when `proc_rows` is empty the loop never binds `p`, so the post-loop
`p.get(...)` raises `UnboundLocalError` — and `proc_rows` legitimately becomes `[]` whenever
`self.procs.sample()` throws (caught at `collector.py:136-140`). So a CPU/mem threshold breach
during a process-sampling failure aborts `check_thresholds` and **skips every later threshold check
(GPU VRAM, etc.) for that tick.** Every CPU/mem alert that fires embeds a wrong process name+usage.
- **Test gap:** zero coverage of `check_thresholds`/`topproc` (grep empty).
- **Fix:** indent 196-197 into the `for` body. (This is the bug flagged at the end of the prior
  session — now confirmed by AST + reproduction.)

### EVAL-3 — keyword rubric is negation-blind substring matching; gameable, drives wrong routing
`eval/scoring.py:17,23`
`score()` lowercases the text and tests `term.lower() in text` — raw substring, no word boundary,
no negation. Against the actual cases: `classify-spam` rubric is `contains_any:['spam']`
(`cases.jsonl:13`), so **"This is NOT spam" scores 1.0** — a wrong classification passes. Same for
`positive`/`negative` sentiment and the `code-bug` `division`/`zero` terms. This score is the sole
input to the "local OK vs route-to-Claude" decision (`report.py:18-19`), so a false PASS means a
task is marked "local OK" and Claude is silently not consulted.
- **Test gap:** only positive-presence + case-insensitivity tested; no negation, no
  word-boundary-false-positive, no "model said the opposite" case.
- **Fix:** match on `\bterm\b` (regex with `re.escape`); add a `not_contains` rubric key to fail
  on negation/leakage.

### RAG-1 (pipeline) — chunks zipped to embeddings positionally; silent vector corruption / chunk loss
`rag/ingest.py:92-95` with `aiserver/client.py:82-88`
Ingest does `embeddings = embedder([c.text for c in chunks])` then `zip(chunks, embeddings)`,
pairing by position. This trusts (a) the endpoint returns vectors in input order and (b) exactly
one per input. The OpenAI-compatible `/v1/embeddings` response carries a per-item `index` field
**precisely because order isn't guaranteed**; `LLM.embed` ignores it. And `zip` truncates to the
shorter sequence — **a short response silently drops the trailing chunks from the index, today,
with no error.** Order-corruption is latent until a backend swap (the client docstring already
anticipates vLLM/llama.cpp). Either way the result is a corrupt index that still answers queries —
the worst failure class.
- **Test gap:** conftest's embed handler always returns one in-order vector per input, so the
  assumption is never challenged.
- **Fix:** sort `data` by `index` in `LLM.embed`; assert `len(embeddings) == len(chunks)` before
  the zip and raise on mismatch.

---

## MEDIUM (24)

**Error handling / robustness**
- **CLIENT-2** — `client.py:50-51`: an HTTP-200 with a non-JSON/truncated body (e.g. an HTML page
  from the planned WP-E Caddy gateway) makes `json.load` raise `JSONDecodeError`, which is **not**
  `URLError` and **not** wrapped → escapes the advertised `LLMError` contract to every caller.
  *Fix:* wrap `json.load` in `try/except ValueError → LLMError`.
- **XC-3** — `client.py:43-59`: same `HTTPError`-subclass retry bug as CLIENT-1, plus the
  un-wrapped `ValueError` from CLIENT-2 — two entry points (`cli.py`, `eval/run.py`) handle failure
  inconsistently. Bundle the fix with CLIENT-1/2.
- **CONFIG-1** *(high→med, partly)* — `config.py:25-34`: `.env` parser doesn't strip surrounding
  quotes or inline comments. `MODEL="qwen2.5-coder:14b"` yields the literal value *with quotes* →
  silent 404. Verifier tempered severity because `.env.example` ships everything unquoted, so the
  trigger is operator deviation from the template. *Fix:* strip matched quotes; decide/​test the
  supported subset.
- **CONFIG-2** *(high→med)* — `config.py:56-74`: a blank `MODEL=` in `.env` overrides the default
  with `''` (blank-beats-default footgun); `int(DIGEST_DAYS)`/`float(EVAL_PASS_THRESHOLD)` raise a
  bare `ValueError` naming neither the key nor the source. *Fix:* skip empty values on merge; wrap
  casts with a key-named error; range-validate.
- **CLIENT-3** is low (see table). **REVIT-LOG-1** below is the most serious of the cross-repo set.

**Cross-repo D3 (live scheduled task — high robustness bar)**
- **REVIT-LOG-1** *(high→med)* — `process_revit_logs.py:294-302`: `render_weekly_local` checks for
  HTTP error / null / empty-`choices` / bad-JSON (all fall back correctly) but **not for an HTTP-200
  with empty/whitespace `content`**. `.strip()` → `""` is never re-checked, so a blank-but-200 model
  reply writes a **degraded canonical file with an empty narrative**, bypassing the deterministic
  fallback the docstring promises. *Fix:* `if not text: return None` after the strip.
- **REVIT-LOG-3** — `process_revit_logs.py:323-324`: the canonical `weekly-revit-summary.md` is
  written `open('w')` truncate-in-place. A kill/disk-full mid-write leaves it empty/truncated with
  no recovery; the local engine widens the window (multi-paragraph narrative). *Fix:* write to a
  temp sibling then `os.replace()` (atomic on same FS, Windows + POSIX).

**Automation / drift**
- **AUTO-1** *(high→med)* — `register-task-windows.ps1:8,16`: the stale singular script's no-op
  task (XC-1), and it shares the task name `'AI-Server Daily Digest'` with the plural script (both
  `-Force`), so running it **clobbers the working registration**. *Fix:* delete it.
- **AUTO-2** *(high→med, partly)* — `decision_drift.py:25-42`: `DriftJob.run()` has zero
  precondition checks. Missing `decision-log` → "0 of 0 decisions" (looks all-clear); never-ingested
  index → **every decision flagged "no match"**. The standalone `rag.drift.main()` *does* guard
  `decision_root.exists()`; the scheduled wrapper dropped it. *Fix:* assert both preconditions and
  fail loud / banner the empty-index case.
- **AUTO-6** — `daily_digest.py:29-36` + `_framework.py:78-80`: `collect_logs` does
  `if not folder.exists(): continue`, so a **wrong `WORKSPACE` after relocation** yields the same
  "No activity" digest as a genuinely quiet period. *Fix:* track whether *any* source root existed;
  say "WORKSPACE roots not found" otherwise.

**Eval harness**
- **EVAL-1** *(high→med)* — `run.py:54` + `report.py:28`: with `ANTHROPIC_API_KEY` set, the Claude
  baseline is computed per case and stored, then **never rendered** — `report.py` uses it only to
  flip a header word to "on". Real tokens spent, zero comparative output. *Fix:* render and/or score
  the baseline, or stop fetching it.
- **EVAL-2** *(high→med)* — `run.py:35-40`: `load_cases` is an unguarded comprehension of
  `json.loads(line)`; one malformed line aborts the whole run with a traceback that doesn't name the
  line. The brief explicitly asked the loader to handle a malformed line. *Fix:* per-line try/except
  naming the 1-based line number.
- **EVAL-4** *(high→med)* — `run.py:54,75-79`: `claude_baseline` is called inside the per-case loop
  with no isolation; a transient Anthropic error propagates into the single broad `except` that
  returns 1 **without writing the report** — destroying all local results. *Fix:* wrap the per-case
  baseline call; the local path must complete regardless.
- **EVAL-5** — `baseline.py:14` + `run.py:54`: baseline model `'claude-opus-4-8'` is a code literal
  with no config key and no way to pass `model=` from the entry point — a direct portability-law gap
  for a model identifier. *Fix:* add `BASELINE_MODEL` to config/`.env.example`.

**RAG pipeline**
- **RAG-2 (pipeline)** — `ingest.py:79-88`: incremental skip is `state[0] == mtime` (exact float
  equality) and the content hash is consulted **only when mtime differs** — contradicting the
  docstring ("re-embedded only when mtime changed AND hash differs"). An mtime-preserving
  restore/copy → silent stale index. *Fix:* hash unconditionally; treat the hash as authoritative.
- **RAG-4 (pipeline)** — `query.py:53-59`: the grounding refusal checks only `hits[0].distance`;
  once the top hit passes, **all k hits** are fed to the model and listed as sources, including ones
  individually beyond `max_distance`. *Fix:* filter per-hit before building context/citations.
- **RAG-5 (pipeline)** — `drift.py:46`: each decision is truncated to 8000 chars before embedding;
  a decision whose match-relevant content sits past the cut is **falsely flagged "undocumented"**,
  silently. *Fix:* chunk the decision like ingest does, or disclose truncation.
- **RAG-6 (pipeline)** — `drift.py:48-52` + `store.py:133`: `knn(k=1, exclude_prefixes=…)`
  over-fetches `k*5+10=15` rows then post-filters; if the 15 nearest are all under the excluded
  decision-log prefix, it returns `[]` and the decision is flagged "no match" though a real match
  sits at rank ≥16. *Fix:* exclude at the SQL level, or enlarge `fetch` until k survive.

**RAG store**
- **RAG-1 (store)** *(high→med, partly)* — `chunk.py:53,56-57`: `overlap_tokens` (a token count) is
  subtracted from `words_per_chunk` (a word count) — a unit mix; and `target_words` at line 53 is
  dead. Realized overlap drifts with word length (verifier measured ~1.5–2.8×, not 4×). *Fix:*
  convert overlap to words; delete the dead var.
- **RAG-2 (store)** *(high→med)* — `store.py:27-29,94,137`: `_normalize` returns a zero vector
  unchanged (not unit length → breaks the L2==cosine invariant for that chunk), and a NaN/inf
  embedding propagates into the stored vector → `distance` becomes NaN → **`ORDER BY distance` is
  undefined and a NaN distance compares `False` against `max_distance`, defeating the grounding
  guard.** *Fix:* reject empty/non-finite/zero-norm vectors at ingest.
- **RAG-4 (store)** — `chunk.py:50,52,55-61`: sizing splits on `body.split()` (ASCII whitespace),
  so CJK / long-URL / minified text with no spaces is one unsplittable "word" → a single oversized
  chunk that can blow the embed context limit. *Fix:* character-window fallback for low-space
  sections; document the CJK token estimate.
- **RAG-5 (store)** — `store.py:36`: `sqlite3.connect` with defaults (rollback journal,
  `busy_timeout=0`). A query that opens while a scheduled ingest holds its write txn fails
  immediately with "database is locked". *Fix:* `PRAGMA journal_mode=WAL` + `busy_timeout=5000`.

**Tests**
- **TEST-1** *(high→med)* — `test_eval.py:106`: `test_claude_baseline_skipped_without_key` passes
  only because `ANTHROPIC_API_KEY` happens to be unset; on a machine where it's set the test would
  try to reach Anthropic. Non-hermetic. *Fix:* `monkeypatch.delenv("ANTHROPIC_API_KEY")` + an
  autouse conftest fixture clearing it suite-wide.
- **TEST-2** — `test_client.py:11-23`: the client's shape-error guards, retry/backoff loop, and the
  `Authorization: Bearer` (WP-E gateway) header path have **zero coverage** — exactly the branches
  CLIENT-1/2 show are wrong. *Fix:* a parametrizable mock handler (malformed body, fail-then-succeed,
  header capture).
- **TEST-3** is medium-leaning but verifier-rated low (mock fidelity — see table).

---

## LOW (51)

| ID | Area | Location | One-line |
|----|------|----------|----------|
| XC-4 | drift | `decision_drift.py:25-42` | Empty/missing index → flags 100% of decisions (overlaps AUTO-2) |
| XC-5 | cli | `cli.py:29-37` | Non-`LLMError` exceptions leak as stack traces; inconsistent with `eval/run.py` |
| XC-6 | chunk | `chunk.py:48-65` | Overlap unit-mix + dead var (same defect as RAG-1 store) |
| XC-7 | drift | `drift.py:46-48` | Drift embeds whole-doc vs per-section chunks — asymmetric, biases distances up |
| XC-9 | eval | `run.py:54`,`report.py` | Baseline computed then dropped (same as EVAL-1) |
| XC-10 | eval | `eval/__init__.py`,`pyproject.toml:23` | Top-level package named `eval` (builtin-name smell) |
| XC-11 | docs | `PROGRAM_PLAN.md:5` | "Validated end-to-end" not backed by a live run; only mock tests exist |
| AUTO-3 | framework | `_framework.py:67-86` | Corpus capped at 24k but Sources lists ALL files → over-claims provenance |
| AUTO-4 | framework | `_framework.py:30-34` | `@register` silently overwrites on name collision (last-wins) |
| AUTO-5 | drift | `decision_drift.py:30-31` | Exclude-prefix uses case-sensitive `str.startswith` on resolved paths — brittle |
| AUTO-7 | framework/drift | `_framework.py:71-74` | decision-log path literal triplicated across 3 files (DRY) |
| AUTO-8 | ps1 | `register-tasks-windows.ps1:34` | No `-Principal`/S4U → tasks only fire while that user is logged on |
| CLIENT-3 | client | `client.py:47-55` | `backoff**0`=1.0s first sleep ignores configured base; retries are silent (log.py unused) |
| LOG-1 | log | `log.py:20-28` | Naive local timestamp (no tz) on machine-read logs; per-line file open; no `test_log.py` |
| CONFIG-3 | config | `config.py:39` | Host stored raw; no scheme validation; double-slash trap for future callers |
| CONFIG-4 | config | `config.py:58` | Env override reads only `_DEFAULTS` keys → non-defaulted keys (secrets) unreachable |
| PROMPT-2 | prompts | `prompts.py:24-26` | `**kwargs: str` unenforced; missing-slot `KeyError` opaque; no `test_prompts.py` |
| PCMON-2 | pcmonitor | `ollama.py:44,86-94` | Non-numeric `poll_interval_sec` kills the bg thread → card freezes on stale value |
| PCMON-3 | pcmonitor | `app.js:365-372` | `renderInference()` has no `#card-infer` null guard (unlike `renderFans`) |
| REVIT-LOG-2 | revit | `process_revit_logs.py:276-277` | Host/model literal fallbacks inline (portability; partly) |
| REVIT-LOG-4 | revit | test file | Fallback contract under-tested: only connection-refused, not non-200/empty/malformed |
| EVAL-6 | eval | `report.py:19` | One `eval_pass_threshold` knob silently governs two different scales |
| EVAL-7 | eval | `run.py:83`,`report.py:50` | Naive-date report filename; same-day runs overwrite each other |
| CFG-1 | packaging | `config/rag_sources.txt:4-5` | Committed file hardcodes one machine's absolute paths (high→low) |
| CFG-2 | packaging | `ci.yml:18-25` | No `cache: 'pip'` — every matrix job reinstalls from PyPI |
| CFG-3 | packaging | `docker-compose.yml:7` | `ollama/ollama:latest` unpinned — non-reproducible |
| RAG-3 (pipe) | query | `query.py:55-59` | All retrieved hits returned as citations regardless of what the answer used |
| RAG-7 (pipe) | query/drift | `query.py:25`,`drift.py:24` | `max_distance`/drift threshold hardcoded, not in config |
| RAG-8 (pipe) | ingest | `ingest.py:27,56` | Hardcoded `out` skip + drops any dot-prefixed-ancestor path silently |
| RAG-9 (pipe) | ingest | `ingest.py:44-48` | Relative config paths resolved against CWD, not repo root |
| RAG-10 (pipe) | ingest | `ingest.py:74-100` | Deletes committed before embeds → embed failure leaves a half-updated index |
| RAG-3 (store) | store | `store.py:133` | `exclude_prefixes` over-fetch can return <k hits (partly; same root as RAG-6 pipe) |
| RAG-6 (store) | store | `store.py:133,141-151` | `knn` returns <k if a vec rowid has no matching `chunks` row |
| RAG-7 (store) | chunk/store | `chunk.py:79`,`store.py:86` | `Chunk.ord` computed then discarded; store re-derives it (two sources of truth) |
| RAG-8 (store) | store | `store.py:86-87` | Empty embedding → attempts `vec0 float[0]` table creation |
| WINPS-1 | scripts | `setup-windows.ps1:50-53` | `ollama pull` success never checked — failed pulls swallowed |
| WINPS-2 | scripts | `setup-windows.ps1:39-43` | Proceeds to pull/smoke without confirming `ollama serve` came up (partly) |
| WINPS-3 | scripts | `setup-windows.ps1:58` | Final echo advertises hardcoded `localhost` regardless of `OLLAMA_HOST` |
| STAT-1 | scripts | `aiserver_status.py:52-60` | `_newest` (mtime sort) never tested with >1 candidate |
| STAT-2 | scripts | `aiserver_status.py:36-49` | Reads each file twice; over-broad italic-line regex for the summary |
| STAT-3 | scripts | `aiserver_status.py:97-102` | Dashboard JSON contract pinned nowhere; `host` key actually holds a URL |
| STAT-4 | scripts | `aiserver_status.py:39,44,72` | Can read a torn/empty job file mid-write (writers use non-atomic `write_text`) |
| SMOKE-1 | scripts | `smoke-test.py:18-31` | Reports `[OK]` on a degenerate empty/whitespace model reply |
| SMOKE-2 | scripts | `smoke-test.py:25` | Failure hint hardcodes `ollama serve`, contradicting the runtime-agnostic design |
| TEST-3 | tests | `conftest.py:27-36` | Mock endpoint returns 200 for ANY payload, ignores `model`, omits `/api/ps` — unfaithful |
| TEST-4 | tests | `test_status.py:43-49` | "Newest of each" tested with a single candidate — sort never exercised |
| TEST-5 | tests | `test_eval.py:68-72` | `baseline_key` plumbing never tested with a key; in-suite comment misstates why |
| TEST-6 | tests | `test_rag_store.py:53` | `knn` over-fetch truncation boundary untested |
| TEST-7 | tests | `test_rag_ingest.py` | Non-UTF8/unreadable read path + embed dim-mismatch guard untested |
| TEST-8 | tests | `test_automation.py:45-103` | No test proves a job leaves the workspace unmodified / refuses to write outside `out/` |
| TEST-9 | tests | `test_config.py:4-11` | Tests don't isolate the real repo `.env` → local values can bleed into assertions (partly) |

## NIT (11)

| ID | Location | One-line |
|----|----------|----------|
| AUTO-9 | `weekly_rollup.py:21,26` | `days=7` hardcoded while `daily_digest` reads `cfg.digest_days` — inconsistent |
| AUTO-10 | `_framework.py:41-44` | `run_job` always passes `cfg=None`; every job reloads config independently |
| PCMON-4 | `ollama.py:18-32` | `parse_ps` ignores `expires_at` — an expired keep-alive still counts as "loaded" |
| REVIT-LOG-5 | `process_revit_logs.py:278,300` | Metrics computed before the network call → double work on the fallback path |
| EVAL-8 | `cases.jsonl:4,9` | Brittle keyword variants maintained by hand because the scorer has no stemming |
| CFG-4 | `eval/run.py:15` | `sys.path` mutation at import masks packaging breakage for the `run-eval` entry point |
| CFG-5 | `pyproject.toml:7,11,12,19` | Lower-bound-only dep pins (no upper cap) |
| RAG-11 (pipe) | `store.py:24,149` | `Hit.ord` carried through and returned but never used by any module |
| RAG-9 (store) | `chunk.py:14,29-45` | Heading regex swallows hash-only/empty headings into the previous section body |
| WINPS-4 | `setup-windows.ps1:41,52` | Setup scripts shell out to `ollama pull`/`serve` — acceptable bootstrap exception, note it |
| TEST-10 | `test_automation.py:60-66` | Several behaviors exercised without assertions weaker than the code's promise |

---

## Refuted / unverified (the verification pass earning its keep)

- **PROMPT-1 — REFUTED (mechanism, not just severity).** Claimed `render()` using `str.format()` on
  untrusted vault content enables format-string injection / crashes on a literal brace. The verifier
  correctly identified this as a textbook confusion: untrusted text passed **as a value** to
  `.format()` is safe; only untrusted text used **as the format string** is dangerous. The code
  passes vault content as values. No vulnerability.
- **XC-8 — REFUTED.** Claimed the default `WORKSPACE` (a Windows `F:` path) makes a Linux relocation
  silently index nothing. `README.md:9-12` and `relocate.md` explicitly require setting `WORKSPACE`
  on relocation; the "only one line changes" contract is honored, not violated.
- **XC-12 — UNVERIFIED.** "Does `eval/baseline.py`'s comment that Opus 4.8 rejects
  `temperature`/`top_p`/`top_k` (400) reflect a real API fact?" The verifier failed on prompt length.
  *Owed:* confirm the 4.8 parameter behavior before trusting that comment (and the code path that
  omits temperature). Low stakes — it only affects the opt-in baseline.

---

## Prioritized fix order

1. **PCMON-1** (cross-repo) — one-line indent fix; it currently makes every CPU/mem alert wrong and
   can suppress GPU-VRAM alerts. Highest correctness-per-character.
2. **HTTP client error contract** (CLIENT-1 + CLIENT-2 + XC-3) — one focused change to `_post`
   closes three findings and unblocks the most common operator failure being diagnosable.
3. **XC-1 / AUTO-1 / XC-2** — delete the stale `register-task-windows.ps1`, repoint the README. The
   onboarding path should not install a no-op. (Standing "clean up loose ends" authorization covers
   the deletion.)
4. **RAG-1 (pipeline) + RAG-2 (store)** — assert `len(embeddings)==len(chunks)` + sort by `index`;
   reject non-finite/zero vectors. These protect index integrity (silent-corruption class).
5. **Drift guards** (AUTO-2 / XC-4) — a precondition check so the weekly report can't cry
   "100% undocumented" from a missing index.
6. **REVIT-LOG-1 + REVIT-LOG-3** — the empty-content fallback hole and the non-atomic write on a
   live scheduled task; both are small and the task is unattended.
7. **CONFIG-1/2** — quote-strip + blank-as-unset + key-named cast errors at the config boundary.
8. **EVAL-1/2/4** — stop discarding paid baseline output; don't let a bad line or a cloud blip kill
   the local run.
9. Test gaps (TEST-1/2/3) and the long tail.

## What's solid (fair credit)
- Every module ships a test file; the TDD discipline is real, not decorative.
- Portability law is **mostly** honored — hosts/models/paths live in `.env`/`config/` (the
  exceptions, EVAL-5 / REVIT-LOG-2 / CFG-1 / RAG-7, are flagged and minor).
- Stdlib-first held: the only runtime dep is `sqlite-vec`; `anthropic` is correctly an opt-in extra.
- `docker-compose.yml` obeys the hard-laws (env-driven host, no baked secrets, LAN-bind warning).
- The OpenAI-compatible-HTTP-only law is respected everywhere except the documented setup-script
  bootstrap (WINPS-4, explicitly acceptable).
- The `WP-D_FOLLOWUPS.md` "mechanisms done; production validation owed" framing is admirably honest
  (XC-11 only asks `PROGRAM_PLAN.md` to match that candor).

---

*Method: 11-reviewer fan-out + per-finding adversarial verification (105 agents). Severities are
post-verification; 11 findings downgraded, 2 refuted, 1 unverified (XC-12). This audit reviewed
**code, not running behavior** — the owed live smokes in `WP-D_FOLLOWUPS.md` remain the separate
production-validation track.*

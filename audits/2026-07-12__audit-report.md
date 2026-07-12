# AI-Server — Incremental Code Audit (2026-07-12)

**Scope (incremental):** everything changed in `F:\AI-Dev\AI-Server` since the last audit
cutoff (**2026-06-18**, `audits/2026-06-18__audit-report-full.md`). That is two commits:

- `c82c674` *"fix: resolve 4 high-severity findings from the 2026-06-18 audit"* — touches
  `aiserver/client.py`, `eval/scoring.py`, `eval/cases.jsonl`, `rag/ingest.py`,
  `automation/register-task*-windows.ps1`, `README.md`, `relocate.md`, and 5 test files.
- `3c4d4e6` *"feat: add OpenWhispr dictation-cleanup reliability proxy"* — a brand-new
  network-facing subsystem: `aiserver/dictation_proxy.py`,
  `scripts/install-dictation-proxy-task.ps1`, `tests/test_dictation_proxy.py`.

**Note on scope/skill:** the `/audit` skill template is hard-wired to the *BIMpossible* repo
and its workspace archive; this run was explicitly redirected to **AI-Server**, so the report is
filed in AI-Server's own `audits/` with the local run index at `audits/_audit-runs.md`.
Different codebase from BIMpossible — the only prior-audit context carried is the 2026-06-18
report, used to check whether the four "resolved" findings actually got fixed or regressed.

**Method:** two jobs. (1) **Regression check** — re-verify the four claimed high-severity fixes
against the actual code, refusing "the test is green" as proof. (2) **Fresh review** — the new
dictation proxy, never before audited, under the exacting senior-reviewer persona. Every
mechanical claim in this report was **executed, not asserted**: the whole-word regression, the
empty-term footgun, and the proxy's dropped-request path were each reproduced with a runnable
snippet (shown inline). Suite state at audit time: **`python -m pytest` → 83 passed**.

---

## Summary

**11 findings: 0 critical, 0 high, 5 medium, 4 low, 2 nit.** Plus regression verdicts on the four
claimed fixes: **3 cleanly fixed, 1 fixed-but-regressed.**

The fix commit is, on balance, good work: **CLIENT-1, RAG-1, and XC-1 are genuinely and
correctly resolved, each with a real regression test that exercises the exact gap the prior audit
named** (not a green-by-accident test). Credit where due — see the regression table.

But two things undercut it, and they rhyme with each other:

> **The 2026-06-18 audit's headline was "silent-wrong-output on the error / misconfiguration /
> malformed-response edges," and its single most-cited mechanism was substring matching. This
> increment fixes both in the code that was called out — and then reintroduces both in the code
> written the same week.**

1. **The EVAL-3 fix traded one silent mis-score for another.** Tightening `score()` to whole-word
   matching fixed the cited "This is NOT spam" false-pass, but it silently broke the sibling
   `code-bug` case: the rubric's own terms (`ZeroDivision`, `division`, `zero`) can no longer
   match the natural model answer *"…raises a **ZeroDivisionError**…"*, flipping a correct answer
   to FAIL and the whole `code` task from "local OK" to "route to Claude". Proven below.
2. **The new dictation proxy is built on the two anti-patterns the prior audit flagged as the
   theme.** It decides "did the model answer instead of clean up?" via raw substring matching
   (DP-1) — the same technique just deleted from `scoring.py` — so legitimate dictation containing
   "sorry" / "sure, I" / "I understand" is silently passed through *uncleaned*. And its
   error handling has a hole (DP-2, proven) that drops the request on a read-timeout, violating
   the module's own written guarantee that a dropped request can never happen.

Nothing here is critical or high — no data-corruption or wrong-alert class bug like last time.
But the pattern is worth naming: **the lessons from the last audit were applied locally to the
flagged lines, not transferred as principles to new code.**

---

## Regression check — the four claimed fixes

| Prior finding | Claim | Verdict | Evidence |
|---|---|---|---|
| **CLIENT-1** (high) | catch `HTTPError` first, surface status+body, retry only 408/429/5xx | ✅ **Fixed, well-tested** | `client.py:54-66`; tests `test_client.py:70-102` prove 4xx not retried + body surfaced, 5xx retried/recovers, exhausted-5xx reports status not "endpoint down". Airtight. |
| **RAG-1** (high) | sort embeddings by `index`; raise on chunk/vector count mismatch | ✅ **Fixed, well-tested** | `client.py:99` sort-by-index; `ingest.py:93-97` count guard; tests `test_client.py:126-139` (scrambled + missing index) and `test_rag_ingest.py:87-97` (short response raises). Airtight. |
| **XC-1** (high) | delete stale singular `register-task-windows.ps1`; repoint docs at the working plural script | ✅ **Fixed, guarded** | Singular script deleted; `README.md:22`, `relocate.md:30` use the plural; `test_scripts.py:27-36` asserts the singular string is absent and the file gone. Correct (the singular is *not* a substring of the plural, so the assert is sound). |
| **EVAL-3** (high) | whole-word matching + `not_contains` gate; harden the classify-spam case | ⚠️ **Fixed for the cited case, but introduced a regression** | Cited case now `not_contains:["not spam"]` (`cases.jsonl:13`) → "This is NOT spam" scores 0.0 ✓. **But the whole-word change broke the `code-bug` case — see EVAL-3-REG (medium).** |

`PCMON-1` (the 5th prior high) lives in the separate non-git `F:\AI-Dev\PC-Monitor`; the commit
message says it was fixed there directly. Out of this repo's scope — not re-verified here.

---

## MEDIUM (5)

### EVAL-3-REG — the whole-word fix silently breaks the `code-bug` rubric it shares a file with
`eval/scoring.py:20-30` (`_contains_term`) vs `eval/cases.jsonl:17`
The `code-bug` case scores a model's bug answer with
`contains_any: ["zero", "divide by", "division", "ZeroDivision"]`. The `ZeroDivision` and
`division` terms exist **specifically** to catch the idiomatic Python answer "raises a
`ZeroDivisionError`". After the switch from substring to `\bterm\b`, none of them can match inside
the concatenated identifier `zerodivisionerror` — there is no word boundary between `zero`/`division`
and the surrounding letters. Reproduced against the shipped `_contains_term`:

```
answer "Yes, this raises a ZeroDivisionError when b is 0."
   'zero'        -> False      'divide by'   -> False
   'division'    -> False      'ZeroDivision'-> False
   => any match (PASS)? False        # was 1.0 (PASS) under the old substring scorer
answer "Yes, division by zero occurs."
   => any match (PASS)? True         # only the spaced phrasing still passes
```

So a **correct** answer scores 0.0 → the case is marked FAIL. With only two `code` cases
(`code-language`, `code-bug`), one flip drops the `code` pass-rate from 1.0 to 0.5, crossing the
0.8 threshold (`report.py`) and flipping the routing recommendation for *all* code tasks to "route
to Claude". This is the same "silent-wrong-routing" harm EVAL-3 was about, now pointing the other
way. It is invisible: the suite is green because no test feeds the `ZeroDivisionError` phrasing to
`score()`, and the harness only exercises `cases.jsonl` against a live model, never in CI.
- **Fix:** the rubric term `ZeroDivision` is now dead for its purpose — either add a
  `contains_substr` rubric mode for identifier fragments, or rewrite the case's terms to
  whole-word-matchable forms (`"ZeroDivisionError"`, `"by zero"`) and add a `score()` test that
  feeds the concatenated-identifier answer.

### DP-1 — proxy answer-detection is substring matching; legit dictation is silently passed through uncleaned
`aiserver/dictation_proxy.py:54-68, 105-112, 121-131`
`looks_like_answer_not_cleanup()` flags a response as "the model answered instead of cleaning up"
if any of `_ANSWER_MARKERS` (`"sorry"`, `"i understand"`, `"i can help"`, `"please provide"`,
`"sure, i"`, …) appears as a **substring** of the model output. But cleanup *preserves meaning*, so
these phrases appear in ordinary dictation. Dictate *"um, sure I can, uh, get that to you by
Friday"* → the model correctly cleans it to *"Sure, I can get that to you by Friday."* → contains
`"sure, i"` → flagged → `sanitize_response` discards the clean version and returns the **raw,
un-cleaned** text (the "ums" and fillers restored). The feature silently no-ops for a large,
common class of input, and because `log_message` is suppressed (`:137-138`) nothing records that
cleanup was skipped. This is the exact substring anti-pattern deleted from `scoring.py` in the same
commit, re-implemented in new code. The design's "worst case is un-cleaned dictation" safety holds
— it never returns a *wrong* answer — but the feature's value evaporates undetectably for inputs
containing any marker word.
- **Test gap:** `test_looks_like_answer_allows_clean_text` (`test_dictation_proxy.py:88-97`)
  conspicuously tests only clean texts that contain *no* marker word — the blind spot is baked into
  the suite. There is no test proving a legitimate *"Sure, I'll…"* survives.
- **Fix:** anchor markers to the start of the response (a refusal/answer leads with them:
  `^\s*(i'm sorry|sure,|i understand|…)`), or gate on the marker appearing in a position the raw
  user text does *not* contain it. At minimum, add the false-positive case to the suite.

### DP-2 — a read-phase timeout (or reset) escapes `do_POST` and drops the request — violating the module's own guarantee
`aiserver/dictation_proxy.py:187-201`
The chat path catches `HTTPError`, `URLError`, and `JSONDecodeError`. A socket **read** timeout
during `json.load(r)` — i.e. the model is still generating past the 120 s timeout — raises
`TimeoutError` (`socket.timeout`), which subclasses **none** of the three. Same for a
`ConnectionResetError` mid-body. Proven:

```
socket.timeout subclasses URLError?      False
ConnectionResetError subclasses URLError? False
# slow upstream that sends headers then stalls, client timeout=1s, mimicking do_POST:
RESULT: ESCAPED all three excepts -> TimeoutError | timed out
```

The exception propagates out of `do_POST`, the handler thread errors, and OpenWhispr gets a dropped
connection — no response body. That directly contradicts the module docstring (`:24-27`): *"Worst
case is un-cleaned dictation, never a wrong 'answer' (or a dropped request)."* A 14B model
cleaning a long dictation on a busy box exceeding 120 s is the *expected* trigger, not an exotic
one. The `_forward_raw` path (`:148-154`) has the identical hole for non-chat requests.
- **Fix:** widen the catch to `(urllib.error.URLError, TimeoutError, OSError)` and route it to the
  same `_fallback_response(...)` safety net the `JSONDecodeError` branch already uses (`:196-201`),
  so a slow/broken upstream returns the raw dictation instead of dropping the request. Add a test
  with a stalling mock upstream.

### DP-TESTS — the new proxy's error, timeout, and forwarding paths are untested
`tests/test_dictation_proxy.py`
Good coverage of the pure helpers and the happy/refusal/malformed-body integration paths. Missing,
and each is a branch this audit shows is either wrong or unproven:
- upstream `HTTPError` (e.g. 500) passthrough (`dictation_proxy.py:190-192`) — no test;
- upstream down → 502 `URLError` (`:193-195`) — no test;
- invalid client JSON → 400 (`:176-178`) — no test;
- read-timeout / non-URLError → **dropped request** (DP-2) — no test, and it's a real defect;
- `_forward_raw` **POST** path (non-chat POST, `:169-172`) — only GET is tested;
- the DP-1 false-positive (legit dictation containing a marker) — not tested.
- **Fix:** parametrize the mock upstream over status code / stall / malformed body and assert the
  proxy's contract (fallback or documented error) for each.

### CLIENT-2 — [carryover, medium] `json.load(r)` on a 200 is still unwrapped; escapes the `LLMError` contract
`aiserver/client.py:53`
The `_post` rewrite fixed CLIENT-1 correctly but left CLIENT-2 (prior audit, medium) untouched,
even though it edited the exact function. A 200 response whose body isn't valid JSON — an HTML
error page from the planned WP-E Caddy gateway, or a proxy interstitial — makes `json.load(r)`
raise `JSONDecodeError` (a `ValueError`, subclass of neither `HTTPError` nor `URLError`), which
propagates raw to every caller, breaking the advertised "everything failure-shaped becomes
`LLMError`" contract. The rewrite was the natural place to close this.
- **Fix:** wrap `json.load(r)` in `try/except ValueError → LLMError(f"{url} returned HTTP 200 with
  a non-JSON body: …")`. Two lines, closes the last of the CLIENT-1/2/XC-3 cluster.

---

## LOW (4)

| ID | Location | One-line |
|----|----------|----------|
| **EVAL-EMPTY** | `eval/scoring.py:20-30` | An empty rubric term matches everything: `_contains_term("anything","")` → `re.search("", …)` → `True` (reproduced). A malformed rubric with `""` in `not_contains` silently forces every score to 0.0; in `contains_any` it always passes. Guard against empty terms. |
| **DP-3** | `scripts/install-dictation-proxy-task.ps1:32-38` | Reports success ("Done… Starts automatically: Running", green) after `Start-ScheduledTask` + 2 s sleep, but never checks the proxy actually **bound** its port. Under `pythonw` a bind failure (port 11435 already taken, or `aiserver` not importable) exits invisibly; the banner still says success. Same class as prior WINPS-2. Probe `http://127.0.0.1:11435/api/tags` (or check `.State -eq 'Running'`) before declaring success. |
| **DP-4** | `dictation_proxy.py:145-147, 181-186` | The proxy forwards only `Content-Type`; it drops `Authorization`. `client.py:39-40` explicitly supports `Authorization: Bearer` for the planned WP-E api-key gateway — when that lands, every request through this proxy 401s. The docstring calls the proxy "unrelated to WP-E," but they target the same endpoint. Forward the auth header (and `Accept`). |
| **DP-6** | `dictation_proxy.py:215-216`, install script | Listen host/port (`127.0.0.1:11435`) are code + PowerShell literals, not `.env`/`config`. The upstream is correctly config-driven (`main():220`), so the portability law is only lightly bent (a local listen port with a `--port` override), but the box relocation contract is "one line in `.env`" and this port isn't in it. Consider a `DICTATION_PROXY_PORT` key or note the deviation in `README.md:35`. |

---

## NIT (2)

| ID | Location | One-line |
|----|----------|----------|
| **DP-7** | `dictation_proxy.py:207-210` | `ThreadingHTTPServer` without `daemon_threads = True`; an in-flight request thread can delay/block process shutdown. Set `daemon_threads = True` for a clean logon-resident service exit. |
| **DP-CLEAN** | `dictation_proxy.py:121-126` | `sanitize_response` returns an upstream **200-with-error-shape** body (`{"error": …}`) unchanged via the `KeyError` branch, rather than falling back to raw text. Narrow (Ollama sends errors non-200), but a 200 error body would reach OpenWhispr as a broken completion instead of the raw-text safety net. |

---

## Prioritized fix order

1. **DP-2** — widen the exception catch to include `TimeoutError`/`OSError` and route to the
   existing fallback. Small change; it's the one place the new subsystem breaks its own written
   contract, on the most likely trigger (slow generation). Add the stalling-upstream test.
2. **EVAL-3-REG** — the fix commit's own regression. Restore `code-bug` matchability (rubric
   rewrite or a substring mode) and add the `ZeroDivisionError` test so the harness can't silently
   mis-route the `code` category.
3. **DP-1** — anchor the answer-markers so cleanup stops silently no-opping on common dictation;
   add the false-positive test. (Same root lesson as the EVAL-3 fix — apply it here too.)
4. **CLIENT-2** — two-line `ValueError` wrap to finally close the CLIENT-1/2/XC-3 cluster.
5. **DP-TESTS** + **EVAL-EMPTY** + the low/nit tail.

## What's solid (fair credit)

- **Three of four claimed high fixes are genuinely correct and each ships a test that exercises the
  precise gap the prior audit cited** — not decorative coverage. CLIENT-1's retry/status-surfacing,
  RAG-1's index-ordering + count guard, and XC-1's script deletion + doc repoint are all airtight.
- The dictation proxy's **core design is sound**: forcing `temperature:0`/`stream:False`,
  deep-copying before mutation (`:128`), idempotent prompt hardening (`:71-85`), and a raw-text
  fallback so it never surfaces a wrong "answer". The failures above are edges around a good spine.
- It learned XC-1's lesson where it counted: the module **has** an `if __name__ == "__main__"`
  block (`:230`) and the install script invokes it via `-m aiserver.dictation_proxy` with the repo
  root as working dir — the exact mistake that made the old daily-digest task inert is not repeated.
- Portability held for the parts that relocate: upstream resolves from `OLLAMA_HOST` via the config
  loader; no new hard-coded model names; stdlib-only (`http.server`, `urllib`) — no new deps.
- `python -m pytest` → **83 passed** at audit time; the suite runs against stdlib mocks, no real
  Ollama, per the project's CI contract.

---

*Method: incremental scope (two commits since the 2026-06-18 cutoff) — regression-check on four
claimed fixes plus a fresh review of the new dictation-proxy subsystem. Every mechanical finding
(EVAL-3-REG, EVAL-EMPTY, DP-2) was reproduced with a runnable snippet, not asserted. This audit
reviewed code, not live OpenWhispr↔Ollama behavior; the DP-1/DP-2 fixes should be confirmed
against a real slow-generation run before the proxy is trusted unattended.*

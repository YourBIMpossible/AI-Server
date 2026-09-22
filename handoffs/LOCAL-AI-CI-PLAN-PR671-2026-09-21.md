<!-- Imported verbatim from the owner's Downloads on 2026-09-21 (written by a separate chat session, not this repo). Routing and the PR #671 call: decisions/2026-09-21__personal-ai-and-pr671-ci-plan.md -->

# Local AI CI Plan for BIMpossible PR #671

**Status:** Deferred foundational work — execute after the Autodesk draft-stack readiness work is closed.

**Purpose:** Replace the current costly NL-filter live-evidence gate with a reproducible, zero-external-cost local-AI CI path. This must unblock BIMpossible PR #671 without adding an Anthropic API key, making paid external API calls, bypassing validation, or weakening safety checks.

---

## 1. Executive Decision

Do **not** add an Anthropic API key or pay for external calls to make CI green.

The current NL-filter evidence gate is coupled to a whole-file hash of `backend/aec/nl_filter.py`. That is too broad: it treats a change to pre-model authorization code as if it changed the LLM prompt or LLM behavior. PR #671 changes a fail-closed authorization gate before inference, while the rendered prompt fingerprint is unchanged.

The permanent remedy is:

```text
Deterministic tests
+ local-model behavioral evidence
+ normal repository validation
= merge-eligible without paid external AI calls
```

External-provider checks remain possible, but are isolated as explicitly requested compatibility/release checks. They are never an implicit normal-CI requirement.

---

## 2. Current PR #671 State

### Completed locally

- A duplicate Alembic migration ID collision between PR #671 and Autodesk-stack PR #677 was identified.
- PR #677's migration ID is load-bearing for later Autodesk waves, so it must remain unchanged.
- PR #671's migration was correctly renamed from `e5f6a7b8c9d1` to `a4c1e9b73f52`.
- The rename is minimal and is committed locally as:

```text
07731a4d
fix(alembic): rename WFA-L3 migration off colliding id
```

- The migration graph parses correctly after the rename.
- Relevant backend, AI-context, and Alembic tests passed during the prior validation.

### Not pushed

The local commit is intentionally not pushed because current NL-filter evidence policy requires a fresh live provider run after the branch modifies `backend/aec/nl_filter.py`.

### Why the current gate blocks

PR #671 adds a fail-closed pre-model authorization path. It changes the whole-file source hash:

```text
nl_filter_source_sha256
```

It does **not** change the prompt fingerprint:

```text
prompt_sha256
```

The existing evidence gate therefore creates a false positive: it requests a paid live-provider run even though the model-facing prompt contract did not change.

### Separate unresolved risk

PR #671 is also conflicting against main in tenant-isolation surfaces:

- `cross_firm_sharing.py`
- `hub_tenancy.py`
- `router.py`

That rebase/conflict resolution is security-sensitive and is explicitly outside this CI architecture work. Do not auto-resolve it merely to make the PR green.

---

## 3. Goals

1. Make local AI behavioral evidence the normal no-cost CI provider for NL-filter validation.
2. Stop treating a whole-source-file hash as the sole trigger for behavioral evidence freshness.
3. Continue requiring fresh behavioral validation whenever model-facing behavior truly changes.
4. Make ordinary CI independent of `ANTHROPIC_API_KEY`, external network availability, and paid-provider usage.
5. Preserve clear separation between local-provider evidence and external-provider compatibility evidence.
6. Allow PR #671 to pass normal verification and be pushed without paying for an external API.
7. Preserve strict deterministic validation of the fail-closed authorization logic.

---

## 4. Non-Goals and Guardrails

### Do not do any of the following

- Add, request, search for, expose, or use `ANTHROPIC_API_KEY`.
- Make paid external API calls.
- Add a verification bypass, `-SkipVerify`, `--log-bypass`, force push, or weakened assertion.
- Silently fall back from local inference to an external provider.
- Lower scoring thresholds, acceptance floors, or evaluator standards to accommodate a different model.
- Treat local-model evidence as Anthropic-provider evidence.
- Resolve PR #671 tenant-isolation conflicts.
- Merge PR #671.
- Enable `BIMPOSSIBLE_AUTODESK_FIRST_ACCESS`.
- Modify canonical queue, wave, phase, watermark, or mirror state as part of this work.
- Combine the CI architecture change with the PR #671 migration rename in the same commit.

### Required safety behavior

- If the local model endpoint is unavailable, fail clearly as a local-infrastructure prerequisite or follow an explicit deterministic-only policy. Never use a paid-provider fallback.
- If model identity, model digest, runtime identity, evaluator contract, prompt contract, or corpus differs from recorded evidence, mark behavioral evidence stale.
- A real model-facing change must not pass using stale evidence.

---

## 5. Target CI Architecture

### 5.1 Validation layers

| Layer | Purpose | Normal trigger | Cost |
|---|---|---|---:|
| Deterministic validation | Access control, routing, prompt construction, schema, evaluator logic, migrations, fixtures | Every PR | $0 |
| Local behavioral validation | Run pinned regression corpus through local provider | AI-facing changes or stale local evidence | $0 marginal |
| External-provider compatibility | Verify production-provider-specific behavior | Explicit release/provider request only | Explicitly approved |

### 5.2 Correct policy rule

```text
Normal CI must not require external-provider calls.

Prompt/config/evaluator/corpus/provider changes require fresh local behavioral evidence.

Source-only, authorization-only, logging, comment, import, or refactor changes do not by themselves require behavioral evidence refresh.
```

### 5.3 Required deterministic tests for PR #671

The deterministic suite must prove all of the following:

1. Policy unavailable denies before an inference call.
2. Policy denial denies before an inference call.
3. Policy approval reaches the model adapter.
4. The rendered model prompt is byte-for-byte unchanged from the approved fixture.
5. Model invocation configuration is unchanged.
6. Evaluator contract and acceptance thresholds are unchanged.
7. Existing migration/database and tenant-safety tests remain enforced.

---

## 6. Evidence Design

### 6.1 Separate identity from provenance

The current whole-source hash should remain available for traceability, but it must not alone decide that paid/live behavioral evidence is stale.

Persist at least the following evidence fields:

```yaml
schema_version: 2
provider: local
provider_runtime: <discovered runtime>
endpoint_class: local
model_id: <exact local model identity>
model_digest: <model manifest, weight, or OCI digest>
runtime_version: <runtime version>
prompt_sha256: <exact rendered prompt / prompt construction fingerprint>
model_config_sha256: <temperature, seed, token limit, JSON/schema settings>
evaluator_contract_sha256: <scoring, thresholds, expected schema, acceptance policy>
corpus_sha256: <regression corpus identity>
authorization_contract_sha256: <fail-closed authorization behavior contract>
source_sha256: <whole-source provenance only>
repeat_count: <configured count>
seed: <if supported>
results_sha256: <serialized normalized result set>
recorded_at_utc: <timestamp>
```

### 6.2 Evidence freshness rule

```python
local_behavioral_evidence_required = any([
    prompt_sha256_changed,
    model_config_sha256_changed,
    evaluator_contract_sha256_changed,
    corpus_sha256_changed,
    local_provider_identity_changed,
])

# Informational only; does not alone require behavioral rerun:
source_sha256_changed
```

### 6.3 Provider identity rules

- `provider=local` evidence must never be labeled Anthropic evidence.
- Existing external-provider evidence should be preserved as historical/provider-specific evidence, not silently converted.
- If the local runtime/model changes, the local evidence is stale until rerun.
- If a runtime supports seeds, record and use them.
- If deterministic sampling is not available, use a documented repeat count and stability criteria without weakening acceptance requirements.

---

## 7. Implementation Plan

## Phase 1 — Discovery and contract

Before implementing, inspect the actual local environment and existing project conventions. Do not assume a runtime, endpoint, model, or API format.

### Required discovery

1. Identify local runtime:
   - Ollama, vLLM, llama.cpp, LM Studio, OpenAI-compatible proxy, or another service.
2. Capture verified runtime facts:
   - endpoint and health check;
   - exact model ID;
   - model/manifest/weight digest;
   - runtime version;
   - supported JSON/schema mode;
   - seed or determinism support;
   - available context length;
   - supported inference controls;
   - local/private network classification.
3. Locate repository implementation points:
   - NL-filter monitor;
   - current baseline schema;
   - CLI modes and baseline writer;
   - evaluator and regression corpus;
   - provider/adaptor abstraction;
   - `Verify-Local-CI.ps1` and `Push-And-Verify.ps1`;
   - delivery receipt generation;
   - fixtures, test configuration, and secret policy.
4. Write one concise ADR/decision record establishing:
   - local provider evidence is normal CI evidence;
   - external-provider evidence is optional compatibility evidence;
   - no paid fallback is permitted;
   - local provider unavailability behavior;
   - fingerprint/freshness semantics.

### Exit criterion

A verified local-provider contract and an exact implementation map exist. No code should be designed around assumed local infrastructure.

---

## Phase 2 — Refactor fingerprints and evidence schema

1. Preserve whole-file `source_sha256` as provenance only.
2. Compute a stable prompt fingerprint from exact normalized prompt bytes rendered from pinned fixtures.
3. Compute a stable model-invocation fingerprint including:
   - provider type;
   - model ID/digest;
   - temperature;
   - token limits;
   - schema/JSON settings;
   - system/tool settings;
   - relevant timeout/retry behavior.
4. Compute an evaluator-contract fingerprint including:
   - scoring logic;
   - thresholds/floors;
   - expected structured schema;
   - acceptance conditions.
5. Compute a corpus fingerprint for all test cases/fixtures.
6. Add provider-aware evidence records and schema migration support.
7. Preserve existing external-provider records accurately as historical external evidence.
8. Update baseline reader, writer, CLI, fixture builders, docs, and delivery receipt output together.

### Exit criterion

Non-model source edits no longer make behavioral evidence stale; true behavior-contract edits do.

---

## Phase 3 — Implement the local runner

### Provider interface

Use a provider-neutral interface consistent with repository conventions, such as:

```python
class NLFilterProvider(Protocol):
    def healthcheck(self) -> ProviderIdentity: ...
    def complete(self, request: NLFilterRequest) -> NLFilterResponse: ...
```

### Required local-runner behavior

1. Implement a local adapter for the discovered runtime.
2. Configure explicitly through environment/configuration, for example:

```text
NL_FILTER_EVIDENCE_PROVIDER=local
NL_FILTER_LOCAL_ENDPOINT=<discovered endpoint>
NL_FILTER_LOCAL_MODEL=<exact model>
```

3. Validate local endpoint health and provider identity before any run.
4. Verify expected model identity/digest before accepting results.
5. Persist reproducible evidence:
   - normalized per-case results or approved artifacts;
   - complete metadata;
   - result hash;
   - repeat count;
   - deterministic/stability status.
6. Fail clearly if:
   - endpoint unavailable;
   - endpoint is not approved local/private infrastructure;
   - model ID/digest differs;
   - response violates schema;
   - results fail evaluator requirements.
7. Never fall back to a paid provider.
8. Use seed and temperature 0 where supported. Where not supported, use the approved repeat/stability contract.

### Exit criterion

The pinned regression corpus runs against the local model and produces evidence without credentials or external network access.

---

## Phase 4 — Correct the CI gate

### Normal CI

1. Run deterministic tests on every PR.
2. Compare behaviorally meaningful fingerprints against current evidence.
3. Run local behavioral validation only when required by the freshness rule.
4. Never invoke an external paid provider during normal `Verify-Local-CI`.
5. Include provider, freshness status, fingerprint comparison, and no-external-call assertion in delivery receipts.

### Authorization-only source changes

When only non-model logic changes:

- `source_sha256` may change;
- prompt/model/evaluator/corpus/provider fingerprints remain unchanged;
- deterministic authorization tests must pass;
- existing local behavioral evidence remains valid;
- no local rerun is required solely from source provenance change;
- no paid/external run is required.

### Real model-facing changes

When prompt, model config, evaluator contract, corpus, or local model identity changes:

- evidence is stale;
- local behavioral suite must rerun;
- fresh local evidence must be recorded;
- CI fails until it is fresh;
- external provider remains optional and distinct.

### External compatibility mode

Create an explicit, separately named command for external-provider compatibility testing.

Rules:

- excluded from normal CI;
- must be manually invoked;
- requires explicit credentials and operator authorization;
- stores evidence separately with `provider=anthropic` or equivalent;
- never runs automatically because a source file changed.

### Exit criterion

No ordinary CI or delivery verification route has an implicit paid-provider dependency.

---

## Phase 5 — Test the CI policy itself

Add regression tests that lock the design in place.

| Scenario | Required expected result |
|---|---|
| Comment, logging, import, or refactor only | No behavioral evidence refresh |
| PR #671 authorization-only source change | Deterministic authorization tests required; no external evidence refresh |
| Prompt template changes | Fresh local evidence required |
| Model/model-config changes | Fresh local evidence required |
| Evaluator threshold/schema changes | Fresh local evidence required |
| Corpus changes | Fresh local evidence required |
| Local endpoint unavailable | Clear infrastructure error; never external fallback |
| Local model/digest mismatch | Evidence stale and actionable failure |
| Local evidence stale or missing | Clear local remediation command |
| External evidence absent | Normal CI passes if local/deterministic requirements pass |
| Explicit external mode without key | Clear external-mode failure; no fallback |
| Source provenance changes only | Provenance updated without falsely marking new live evidence |

### Exit criterion

The test suite prevents future reintroduction of whole-file-hash coupling or hidden paid-provider fallback.

---

## Phase 6 — Apply to PR #671

Only after the CI architecture is green:

1. Confirm for PR #671:
   - prompt fingerprint is unchanged;
   - model configuration is unchanged;
   - evaluator contract is unchanged;
   - corpus is unchanged;
   - fail-closed authorization tests pass.
2. Migrate/update its evidence record under the local-provider schema.
3. Run the local behavioral suite only if bootstrap or the new schema requires it.
4. Keep the CI architecture change separate from the migration collision fix.
5. Rebase the local migration fix (`07731a4d`) onto the completed CI work if needed.
6. Run full `Verify-Local-CI.ps1` with no external key and no external calls.
7. Push through `Push-And-Verify.ps1` only if every required validation is green.
8. Do not resolve the tenant-isolation conflicts; keep them explicitly blocked for security review.
9. Do not merge PR #671 without separate authorization.

### Exit criterion

PR #671 can pass normal validation and be pushed without external-provider spend, while tenant-isolation conflicts remain correctly segregated.

---

## 8. Recommended Commit Structure

Keep the reusable CI architecture separate from product/migration changes.

| Commit / PR | Purpose |
|---|---|
| `ci(nl-filter): add local-provider evidence and semantic freshness gating` | Reusable CI infrastructure, baseline schema, provider runner, policy tests, documentation |
| `fix(alembic): rename WFA-L3 migration off colliding id` | The minimal PR #671 migration-ID collision correction, currently local as `07731a4d` |

If repository workflow requires one branch, retain two clearly separable commits and preserve individual validation evidence.

---

## 9. Definition of Done

This work is complete only when all of the following are true:

- Normal `Verify-Local-CI.ps1` does not require an Anthropic key.
- Normal CI makes no external paid calls.
- Local runtime/model identity is discovered, pinned, and verified.
- Provider evidence clearly records `provider=local` and never impersonates external-provider evidence.
- Whole-file source provenance does not by itself invalidate behavioral evidence.
- Prompt/config/evaluator/corpus/provider changes do invalidate local behavioral evidence.
- Authorization logic has deterministic fail-closed tests.
- Local endpoint absence produces a clear no-fallback failure or explicit deterministic-only policy outcome.
- The evidence baseline, CLI, scripts, tests, docs, and delivery receipt use the same schema/rules.
- Regression tests lock the freshness policy.
- Existing external-provider evidence is preserved as external/historical, not relabeled.
- PR #671 can validate and be pushed with no external spend.
- No claim is made that local-model validation is equivalent to external-provider certification.

---

## 10. Deferred Items

These are intentionally not part of this plan:

1. Security-reviewed resolution of PR #671 conflicts in `cross_firm_sharing.py`, `hub_tenancy.py`, and `router.py`.
2. Merge authorization for PR #671.
3. Enabling `BIMPOSSIBLE_AUTODESK_FIRST_ACCESS`.
4. Autodesk stack promotion (`#673 → #676 → #677 → #678`).
5. A future Alembic merge migration joining the PR #671 branch and Autodesk migration chain if both eventually land.
6. Canonical queue/ledger changes.
7. Any external-provider compatibility/release certification process beyond preserving an optional explicit path.

---

## 11. Execution Prompt

Use the following prompt when ready to execute this work:

```text
Implement the local-model CI architecture for NL-filter evidence as a standalone, no-cost foundational change.

Goal:
Make local AI behavioral evidence the normal CI path and remove the current whole-source-hash rule that forces paid external-provider live calls for unrelated code changes. This work must unblock #671 without ANTHROPIC_API_KEY, paid APIs, bypasses, or weakened validation.

Scope:
- Discover the actual existing local AI runtime and project integration before designing any adapter or configuration.
- Split source provenance from model-facing freshness fingerprints.
- Add a reproducible local provider evidence runner.
- Make normal Verify-Local-CI use deterministic + local-model validation only.
- Keep external Anthropic compatibility checks separate, optional, and manually invoked.
- Add full regression coverage for freshness behavior and no-fallback behavior.
- Update baseline schema, CLI, docs, fixtures, validation scripts, and delivery receipt together.
- Keep the CI architecture work separate from #671’s migration rename and tenant-isolation rebase conflicts.

Hard constraints:
- No ANTHROPIC_API_KEY.
- No external paid calls.
- No test bypasses or weakened thresholds.
- No automatic external fallback.
- No merge, flag enablement, queue/ledger edits, or tenant-isolation conflict resolution.
- Preserve unrelated working-tree changes.

Required final evidence:
- Exact local runtime/model identity and health-check result.
- Before/after CI freshness rule.
- Tests demonstrating authorization-only changes do not require model re-evidence.
- Tests demonstrating prompt/config/evaluator/corpus changes do require fresh local evidence.
- Full local validation outcome.
- Confirm zero external API calls.
- A clear next step for applying the architecture to #671.
```

---

## 12. Decision Summary

**Decision:** Use the local model as the standard no-cost behavioral CI provider. Keep external-provider validation optional, explicitly requested, and separately recorded.

**Immediate prerequisite:** Finish the Autodesk draft-stack readiness work first, then execute this CI architecture plan as a standalone foundational change.

**Do not do:** Buy API access, add credentials, run paid external calls, or bypass the existing safety gate merely to push PR #671.

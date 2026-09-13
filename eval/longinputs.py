"""Deterministic long-context eval documents (WP-F): ~27k-token ops logs and a doc corpus.

Synthetic by design -- no client data (OCR hard stop 2026-08-24), nothing read from
AI-Brain-Data. Each document is a pure function of its name: filler comes from a fixed-seed
RNG, and every fact a case grades is planted verbatim, so cases.jsonl can name the answer.
Filler vocabulary never uses the words the planted facts are built from (deploy, INC-,
billing-, DOC-, audit, retention), which tests/test_eval.py checks by counting.

A case pulls one in with  "document": "<name>"  and a  {{DOCUMENT}}  placeholder in "input".
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from functools import lru_cache

_START = date(2026, 8, 10)
_DAYS = 14

_SERVICES = ["api-gateway", "search-indexer", "auth", "scheduler", "cdn-edge", "notifier", "reporting"]
_RES = ["orders", "users", "catalog", "sessions", "reports", "search"]
_JOBS = ["nightly-compaction", "sitemap-refresh", "token-sweep", "metrics-rollup"]
_NOISE = [
    ("INFO", "GET /v2/{res}/{n} 200 in {ms}ms"),
    ("INFO", "POST /v2/{res} 201 in {ms}ms"),
    ("DEBUG", "cache hit ratio {pct}% over last 60s (keys={n})"),
    ("DEBUG", "heartbeat ok peers={p} lag={ms}ms"),
    ("INFO", "gc pause {ms}ms heap={mb}MB"),
    ("INFO", "queue depth {n} (high-water {n2})"),
    ("DEBUG", "connection pool size={p} idle={p2}"),
    ("INFO", "scheduled job {job} completed in {ms}ms"),
    ("INFO", "rotated session keys for {n} tenants"),
    ("INFO", "index segment merge finished segments={p} docs={n}"),
    ("WARN", "slow query {ms}ms on {res} (threshold 250ms)"),
    ("WARN", "retrying upstream call to {svc} attempt={p2}"),
    ("INFO", "config reload applied version={n}"),
]


def _noise_line(rng: random.Random, day: date) -> str:
    level, tmpl = rng.choice(_NOISE)
    msg = tmpl.format(
        res=rng.choice(_RES), n=rng.randint(100, 99999), n2=rng.randint(100, 99999),
        ms=rng.randint(1, 900), pct=rng.randint(40, 99), p=rng.randint(2, 64),
        p2=rng.randint(1, 5), mb=rng.randint(128, 4096), job=rng.choice(_JOBS),
        svc=rng.choice(_SERVICES),
    )
    ts = f"{rng.randint(0, 23):02}:{rng.randint(0, 59):02}:{rng.randint(0, 59):02}.{rng.randint(0, 999):03}"
    return f"{day.isoformat()}T{ts}Z {level:<5} [{rng.choice(_SERVICES)}] {msg} trace={rng.getrandbits(40):010x}"


def _log(seed: int, lines_per_day: int, planted: list[tuple[str, str, str, str, str]]) -> str:
    """planted: (YYYY-MM-DD, HH:MM:SS, level, service, message), merged into time order."""
    rng = random.Random(seed)
    lines = []
    for i in range(_DAYS):
        day = _START + timedelta(days=i)
        lines += [_noise_line(rng, day) for _ in range(lines_per_day)]
    for d, t, level, svc, msg in planted:
        lines.append(f"{d}T{t}.000Z {level:<5} [{svc}] {msg} trace={rng.getrandbits(40):010x}")
    return "\n".join(sorted(lines))


def _deploy(d: str, t: str, dep: int, env: str, status: str, reason: str = "") -> tuple:
    level = "ERROR" if status == "FAILED" else "INFO"
    tail = f" reason={reason}" if reason else ""
    return (d, t, level, "deployer", f"deploy DEP-{dep} env={env} status={status}{tail}")


_OPS_PLANTED = [
    # Ledger database decision, later reversed; a reporting-service MySQL line as a distractor.
    ("2026-08-11", "14:05:00", "INFO", "ledger", "DECISION: adopt MySQL 8.4 as the ledger service database (owner: dana)"),
    ("2026-08-16", "11:00:00", "INFO", "reporting", "reporting keeps its MySQL 8.4 read replica unchanged"),
    ("2026-08-18", "10:30:00", "INFO", "ledger", "DECISION: reverse the 2026-08-11 ledger database decision -- ledger moves to PostgreSQL 17 because MySQL replication lag breached the 2s SLO (owner: dana)"),
    # Incidents: exactly one customer-facing.
    ("2026-08-13", "02:14:00", "ERROR", "notifier", "INC-4468 opened: nightly usage report delayed 3h; internal only, no customer impact"),
    ("2026-08-15", "16:02:00", "ERROR", "api-gateway", "INC-4471 opened: checkout API returning 503 to customers"),
    ("2026-08-15", "16:40:00", "INFO", "api-gateway", "INC-4471 resolved: customer-facing checkout outage lasted 38 minutes"),
    ("2026-08-19", "08:30:00", "ERROR", "search-indexer", "INC-4480 opened: staging search index rebuild stalled; staging only, no customer impact"),
    ("2026-08-21", "12:00:00", "WARN", "api-gateway", "INC-4483 opened: elevated 5xx on internal admin API, customers unaffected"),
    # 2026-08-12: 7 failed prod deploys, plus staging failures, successes, a CI failure and neighbours.
    *[_deploy("2026-08-12", f"{h:02}:17:00", 8800 + i, "prod", "FAILED", "health check timeout")
      for i, h in enumerate([1, 4, 7, 9, 13, 16, 22], start=1)],
    *[_deploy("2026-08-12", f"{h:02}:42:00", 8850 + i, "staging", "FAILED", "image pull error") for i, h in enumerate([3, 11, 18])],
    *[_deploy("2026-08-12", f"{h:02}:05:00", 8870 + i, "prod", "SUCCEEDED") for i, h in enumerate([10, 14, 19, 23])],
    ("2026-08-12", "12:00:00", "ERROR", "ci", "pipeline build 5512 FAILED: unit tests red"),
    _deploy("2026-08-11", "23:55:00", 8790, "prod", "FAILED", "health check timeout"),
    _deploy("2026-08-11", "20:10:00", 8791, "prod", "FAILED", "config error"),
    _deploy("2026-08-13", "00:05:00", 8890, "prod", "FAILED", "health check timeout"),
    _deploy("2026-08-13", "06:30:00", 8891, "prod", "FAILED", "config error"),
    _deploy("2026-08-13", "09:30:00", 8892, "prod", "FAILED", "config error"),
    # 2026-08-20: no production deploy COMPLETES successfully.
    _deploy("2026-08-19", "15:10:00", 9012, "prod", "SUCCEEDED"),
    ("2026-08-19", "17:40:00", "INFO", "deployer", "change board CANCELLED deploy DEP-9025 env=prod that was scheduled for 2026-08-20"),
    _deploy("2026-08-20", "11:20:00", 9020, "staging", "SUCCEEDED"),
    ("2026-08-20", "11:45:00", "INFO", "deployer", "smoke test against current prod release DEP-9012 passed"),
    _deploy("2026-08-20", "14:00:00", 9022, "prod", "FAILED", "migration lock timeout"),
    _deploy("2026-08-20", "23:58:00", 9030, "prod", "STARTED"),
    _deploy("2026-08-21", "00:07:00", 9030, "prod", "SUCCEEDED"),
    _deploy("2026-08-21", "10:05:00", 9031, "prod", "SUCCEEDED"),
]


def _worker(line_kind: str, d: str, t: str, req: str) -> tuple:
    level, svc, code = {
        "target": ("ERROR", "billing-worker", "E_TIMEOUT"),
        "warn": ("WARN", "billing-worker", "E_TIMEOUT"),
        "web": ("ERROR", "billing-web", "E_TIMEOUT"),
        "conn": ("ERROR", "billing-worker", "E_CONN"),
    }[line_kind]
    return (d, t, level, svc, f"job invoice-run failed code={code} req={req}")


_WORKER_PLANTED = [
    *[_worker("target", d, t, r) for d, t, r in [
        ("2026-08-10", "03:12:00", "R-12055"), ("2026-08-12", "18:44:00", "R-10233"),
        ("2026-08-15", "07:01:00", "R-13318"), ("2026-08-17", "22:19:00", "R-11402"),
        ("2026-08-20", "05:33:00", "R-10871"), ("2026-08-23", "13:08:00", "R-12790"),
    ]],
    *[_worker("warn", d, t, r) for d, t, r in [
        ("2026-08-11", "09:00:00", "R-10500"), ("2026-08-14", "10:00:00", "R-11999"),
        ("2026-08-18", "11:00:00", "R-12400"), ("2026-08-22", "12:00:00", "R-13001"),
    ]],
    *[_worker("web", d, t, r) for d, t, r in [
        ("2026-08-10", "15:00:00", "R-10622"), ("2026-08-13", "16:00:00", "R-11555"),
        ("2026-08-19", "17:00:00", "R-12601"), ("2026-08-21", "18:00:00", "R-13190"),
    ]],
    *[_worker("conn", d, t, r) for d, t, r in [
        ("2026-08-12", "19:00:00", "R-10910"), ("2026-08-16", "20:00:00", "R-12222"),
        ("2026-08-22", "21:00:00", "R-13400"),
    ]],
    ("2026-08-13", "04:00:00", "INFO", "billing-worker", "retry of req=R-10233 succeeded on second attempt"),
]

_DOC_TOPICS = [
    "On-call rotation", "Cache TTL policy", "CI runner pool", "Feature flag lifecycle",
    "TLS certificate rotation", "Service mesh timeouts", "Queue consumer scaling",
    "Schema migration checklist", "Load test procedure", "Secrets vault access",
    "DNS change process", "Frontend build pipeline", "Rate limiting defaults",
    "Incident review template", "Dependency upgrade cadence",
]
_DOC_SENTENCES = [
    "The owning team reviews this page every {n} weeks and records changes in the changelog.",
    "Default values apply to every environment unless an override is committed next to the service.",
    "Requests above {m} per second are shed at the edge before they reach application pods.",
    "A change needs one reviewer from the platform group and one from the owning service.",
    "Runners are recycled after {n} jobs to keep build caches from drifting.",
    "Timeouts are set to {m} milliseconds for internal calls and doubled for cross-region calls.",
    "Flags older than {n} sprints are flagged for removal in the weekly hygiene report.",
    "Certificates renew automatically {n} days before expiry; manual renewal is a fallback only.",
    "Consumers scale out when lag exceeds {m} messages for five consecutive minutes.",
    "Every migration ships with a tested rollback script and a dry run against a snapshot.",
    "Access requests expire after {n} days and must be re-approved by the service owner.",
    "Load tests run in the performance environment and never against shared staging.",
    "The pager escalates to the secondary after {n} minutes without acknowledgement.",
    "Build artifacts are signed and the signature is verified before promotion.",
]

_DOCS_PLANTED = {
    41: ("ADR-107: Audit log retention (SUPERSEDED by ADR-212 on 2026-06-02)",
         "Production audit logs are retained for 90 days and then deleted. This decision is no "
         "longer in force; see ADR-212."),
    77: ("Application log retention",
         "Production application logs (not audit logs) are retained for 14 days in the log cluster."),
    118: ("Staging environment data policy",
          "In staging, audit logs are retained for 30 days because staging holds no customer records."),
    124: ("ADR-212: Audit log retention (Accepted 2026-06-02, current)",
          "Production audit logs are retained for 400 days in total: the first 30 days in hot "
          "storage, the remaining 370 days in cold storage. Supersedes ADR-107."),
}


def _docs(seed: int, n_docs: int, sentences_per_doc: int) -> str:
    rng = random.Random(seed)
    out = []
    for i in range(1, n_docs + 1):
        if i in _DOCS_PLANTED:
            title, body = _DOCS_PLANTED[i]
        else:
            title = f"{rng.choice(_DOC_TOPICS)} (rev {rng.randint(1, 9)})"
            body = " ".join(
                rng.choice(_DOC_SENTENCES).format(n=rng.randint(2, 12), m=rng.randint(50, 5000))
                for _ in range(sentences_per_doc)
            )
        out.append(f"[DOC-{i:03}] {title}\n{body}")
    return "\n\n".join(out)


# Sizes are calibrated on the box against the tokenizers of the models under test, not chars.
# A prompt over the 32768 context is NOT rejected: the runner silently keeps half of it
# (measured 2026-09-13: 16,386 tokens back for every oversized prompt). Keep every document
# under ~27k tokens on the hungriest tokenizer measured, leaving room for reasoning + answer.
BUILDERS = {
    "ops_log": lambda: _log(1, 32, _OPS_PLANTED),
    "worker_log": lambda: _log(3, 32, _WORKER_PLANTED),
    "docs_corpus": lambda: _docs(7, 130, 9),
}


@lru_cache(maxsize=None)
def build(name: str) -> str:
    try:
        return BUILDERS[name]()
    except KeyError:
        raise ValueError(f"unknown eval document {name!r}; known: {sorted(BUILDERS)}") from None

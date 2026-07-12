# AI-Server — Audit run index

(Separate from the BIMpossible audit archive. This index covers audits of the AI-Server
platform repo + its cross-repo WP-D touchpoints only.)

| Date | Type | Files reviewed | Top finding | Report |
|------|------|----------------|-------------|--------|
| 2026-06-18 | full | ≈45 code/test + 8 docs (AI-Server, PC-Monitor, AI-Brain-Data) | Silent-wrong-output on error/misconfig edges (0 crit / 5 high): PCMON-1 `topproc()` reports the wrong process & can suppress GPU-VRAM alerts; XC-1 README's primary task install is an inert no-op | [2026-06-18__audit-report-full.md](2026-06-18__audit-report-full.md) |
| 2026-07-12 | incremental | 16 changed across 2 commits (fix `c82c674` + new dictation proxy `3c4d4e6`) | 0 crit / 0 high / 5 med. Fix commit resolved 3/4 highs cleanly (CLIENT-1/RAG-1/XC-1, real tests) but the EVAL-3 whole-word fix regressed the `code-bug` case ("ZeroDivisionError" no longer matches → mis-routes the code category); new proxy reintroduces substring-matching (DP-1) + a proven dropped-request hole on read-timeout (DP-2) | [2026-07-12__audit-report.md](2026-07-12__audit-report.md) |

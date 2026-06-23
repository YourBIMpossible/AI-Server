# AI-Server — Audit run index

(Separate from the BIMpossible audit archive. This index covers audits of the AI-Server
platform repo + its cross-repo WP-D touchpoints only.)

| Date | Type | Files reviewed | Top finding | Report |
|------|------|----------------|-------------|--------|
| 2026-06-18 | full | ≈45 code/test + 8 docs (AI-Server, PC-Monitor, AI-Brain-Data) | Silent-wrong-output on error/misconfig edges (0 crit / 5 high): PCMON-1 `topproc()` reports the wrong process & can suppress GPU-VRAM alerts; XC-1 README's primary task install is an inert no-op | [2026-06-18__audit-report-full.md](2026-06-18__audit-report-full.md) |

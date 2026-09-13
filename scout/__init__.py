"""scout -- read-only repo investigation and evidence compilation over the local LLM.

Public modules:
    scout.sandbox   Sandbox: path validation, bounded inventory/read/search/git, allowlisted checks
    scout.tools     the harness Skills the model may call (SCOUT_SKILLS), all read-only
    scout.evidence  EvidenceLog, evidence.json schema, final-answer parsing/normalisation
    scout.report    the five artifacts (project-map, evidence.json, implementation-plan,
                    verification-plan, handoff)
    scout.run       run_scout(): orchestration; scout.cli: `python -m scout` / `run-scout`
"""

"""Deterministic rubric scoring (keyword/contains). No model, no network.

A rubric is a dict:
    {"contains": [...]}       every term must appear (case-insensitive substring)
    {"contains_any": [...]}   at least one term must appear (a hard gate)
Both keys are optional. score() returns a fraction in [0, 1]:
    - the `contains_any` gate, if present and unsatisfied, forces 0.0
    - otherwise the score is the fraction of `contains` terms present (1.0 if none given)
"""
from __future__ import annotations


def score(output: str, rubric: dict) -> float:
    text = (output or "").lower()

    any_terms = rubric.get("contains_any") or []
    if any_terms and not any(t.lower() in text for t in any_terms):
        return 0.0

    req = rubric.get("contains") or []
    if not req:
        return 1.0
    hits = sum(1 for t in req if t.lower() in text)
    return hits / len(req)


def passed(value: float, threshold: float) -> bool:
    return value >= threshold

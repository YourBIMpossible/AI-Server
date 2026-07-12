"""Deterministic rubric scoring (keyword/contains). No model, no network.

A rubric is a dict:
    {"contains": [...]}       every term must appear (whole-word, case-insensitive)
    {"contains_any": [...]}   at least one term must appear (a hard gate)
    {"not_contains": [...]}   if any term appears, score is forced to 0.0 (a hard gate)
All keys are optional. score() returns a fraction in [0, 1]:
    - the `contains_any` gate, if present and unsatisfied, forces 0.0
    - the `not_contains` gate, if any term is present, forces 0.0
    - otherwise the score is the fraction of `contains` terms present (1.0 if none given)
Matching is whole-word, not raw substring, so e.g. "spam" doesn't match inside "spammy",
and terms are regex-escaped so punctuation in a term is literal.
"""
from __future__ import annotations

import re


def _contains_term(text: str, term: str) -> bool:
    """Whole-word, case-insensitive match. A `\\b` boundary is only required on a
    side whose edge character is itself a word character -- `\\b` can never be
    satisfied between two non-word characters, so an unconditional `\\bterm\\b`
    fails to match terms that start/end in punctuation (e.g. "$5.00").

    An empty term never matches: `re.search("", text)` matches everywhere, which
    would make a malformed rubric's "" silently force every score to 0 (as a
    not_contains term) or always satisfy contains_any -- both wrong.
    """
    if not term:
        return False
    pattern = re.escape(term)
    left = r"\b" if term[:1].isalnum() or term[:1] == "_" else ""
    right = r"\b" if term[-1:].isalnum() or term[-1:] == "_" else ""
    return re.search(f"{left}{pattern}{right}", text, re.IGNORECASE) is not None


def score(output: str, rubric: dict) -> float:
    text = output or ""

    any_terms = rubric.get("contains_any") or []
    if any_terms and not any(_contains_term(text, t) for t in any_terms):
        return 0.0

    not_terms = rubric.get("not_contains") or []
    if any(_contains_term(text, t) for t in not_terms):
        return 0.0

    req = rubric.get("contains") or []
    if not req:
        return 1.0
    hits = sum(1 for t in req if _contains_term(text, t))
    return hits / len(req)


def passed(value: float, threshold: float) -> bool:
    return value >= threshold

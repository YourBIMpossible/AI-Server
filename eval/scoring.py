"""Deterministic rubric scoring (keyword/contains + exact-format gates). No model, no network.

The output is passed through strip_reasoning() first, so keywords written in scratch-work
can't satisfy a rubric and a final answer buried after a reasoning block is judged fairly.

A rubric is a dict. Gates force 0.0 when they fail:
    {"contains_any": [...]}   at least one term must appear
    {"not_contains": [...]}   no term may appear
    {"regex_full": "..."}     the whole output must match (re.fullmatch, DOTALL)
    {"json_equals": <value>}  the output must parse as JSON equal to this (one ``` fence tolerated)
    {"max_words": n}          at most n whitespace-separated words
Graded items give the fraction of hits (1.0 if none given):
    {"contains": [...]}       whole-word, case-insensitive terms
    {"patterns": [...]}       regexes, each re.search'ed (MULTILINE)
{"judge": "..."} is not scored here -- see eval/judge.py.

Term matching is whole-word, not raw substring, so e.g. "spam" doesn't match inside "spammy",
and terms are regex-escaped so punctuation in a term is literal.
"""
from __future__ import annotations

import json
import re

_TAGS = r"(think|thinking|reasoning)"
_CLOSED_BLOCK = re.compile(rf"<{_TAGS}\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_UNTERMINATED = re.compile(rf"<{_TAGS}\b[^>]*>.*\Z", re.IGNORECASE | re.DOTALL)
_ORPHAN_CLOSE = re.compile(rf"\A.*?</{_TAGS}\s*>", re.IGNORECASE | re.DOTALL)
_FENCE = re.compile(r"\A```[a-zA-Z]*\s*\n(.*?)\n?```\Z", re.DOTALL)


def strip_reasoning(text: str | None) -> str:
    """Remove reasoning blocks from a model answer.

    - closed <think>/<thinking>/<reasoning> blocks are removed wherever they are
    - an open tag with no close means the output was truncated mid-reasoning: everything
      from the tag to the end goes, which correctly leaves nothing to score
    - a close tag with no opener (chat templates that open the block inside the prompt)
      removes everything up to and including it
    """
    if not text:
        return ""
    out = _CLOSED_BLOCK.sub("", text)
    out = _UNTERMINATED.sub("", out)
    out = _ORPHAN_CLOSE.sub("", out)
    return out.strip()


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


def _json_equals(text: str, expected) -> bool:
    m = _FENCE.match(text)
    try:
        return json.loads(m.group(1) if m else text) == expected
    except ValueError:
        return False


def score(output: str, rubric: dict) -> float:
    text = strip_reasoning(output)

    any_terms = rubric.get("contains_any") or []
    if any_terms and not any(_contains_term(text, t) for t in any_terms):
        return 0.0

    not_terms = rubric.get("not_contains") or []
    if any(_contains_term(text, t) for t in not_terms):
        return 0.0

    if "regex_full" in rubric and re.fullmatch(rubric["regex_full"], text, re.DOTALL) is None:
        return 0.0

    if "json_equals" in rubric and not _json_equals(text, rubric["json_equals"]):
        return 0.0

    if "max_words" in rubric and len(text.split()) > rubric["max_words"]:
        return 0.0

    req = rubric.get("contains") or []
    patterns = rubric.get("patterns") or []
    if not req and not patterns:
        return 1.0
    hits = sum(1 for t in req if _contains_term(text, t))
    hits += sum(1 for p in patterns if re.search(p, text, re.MULTILINE))
    return hits / (len(req) + len(patterns))


def passed(value: float, threshold: float) -> bool:
    return value >= threshold

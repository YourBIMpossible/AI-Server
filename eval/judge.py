"""Optional model-graded pass/fail (WP-F): a local model judges what keywords can't.

A rubric opts in with  "judge": "<criterion>".  The criterion must be self-contained -- it
states the ground truth -- because the judge never sees the case input (a 27k-token document
plus the answer would not fit one context, and re-reading the task invites the judge to solve
it instead of grading). Temperature 0 and a fixed seed; the verdict is the first word.
"""
from __future__ import annotations

import re

from .scoring import strip_reasoning

JUDGE_PROMPT = """You are a strict grader. Decide whether the ANSWER meets the CRITERION.
Judge only the criterion. Do not reward effort, do not fix the answer, do not add requirements.
Judge meaning, not wording: a paraphrase that states the required fact meets the criterion.

CRITERION:
{criterion}

ANSWER:
<<<
{answer}
>>>

Reply with one word on the first line: PASS or FAIL. You may give a one-sentence reason on the second line."""

_VERDICT = re.compile(r"\A\W*(PASS|FAIL)\b", re.IGNORECASE)


def parse_verdict(text: str) -> bool | None:
    """True for PASS, False for FAIL, None when the judge answered neither."""
    m = _VERDICT.match(strip_reasoning(text))
    return None if m is None else m.group(1).upper() == "PASS"


def judge(llm, criterion: str, answer: str, *, model: str | None = None) -> tuple[bool, str]:
    """(passed, raw judge reply). An unparseable verdict is a FAIL -- never a silent pass."""
    raw = llm.chat(
        [{"role": "user", "content": JUDGE_PROMPT.format(criterion=criterion, answer=answer)}],
        model=model,
        temperature=0,
        seed=0,
    )
    return parse_verdict(raw) is True, raw

"""Autonomy policy: whether a skill's result may run without human approval.

v1 ships one policy (OnDemandReadOnly) that always allows every registered
skill to run, because every v1 skill is safe-by-construction (knowledge.py
only reads the RAG index; propose_patch only writes a .patch under out/,
never touching the target repo). The seam exists so a later, write-capable
skill gates on a *new* policy class -- not a change to loop.py's contract.
"""
from __future__ import annotations

from typing import Any

from .registry import Skill


class RunPolicy:
    def may_auto_run(self, skill: Skill, args: dict[str, Any]) -> bool:
        raise NotImplementedError


class OnDemandReadOnly(RunPolicy):
    def may_auto_run(self, skill: Skill, args: dict[str, Any]) -> bool:
        return True


class AllowlistReadOnly(RunPolicy):
    """Auto-run only skills whose name is on a fixed allowlist; everything else is blocked.
    The repo scout uses this so that, even if another skill were registered, the run can only
    reach its own read-only tools."""

    def __init__(self, names):
        self.names = frozenset(names)

    def may_auto_run(self, skill, args) -> bool:
        return skill.name in self.names

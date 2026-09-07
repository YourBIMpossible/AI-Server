"""harness/policy.py: the autonomy seam -- v1 has one policy that allows everything."""
import pytest

from harness.policy import OnDemandReadOnly, RunPolicy
from harness.registry import Skill, SkillResult


class _Sample(Skill):
    name = "sample_policy_test_skill"
    description = "d"
    schema = {}

    def run(self, **args):
        return SkillResult(content="ok")


def test_base_policy_not_implemented():
    with pytest.raises(NotImplementedError):
        RunPolicy().may_auto_run(_Sample(llm=None), {})


def test_on_demand_read_only_always_allows():
    assert OnDemandReadOnly().may_auto_run(_Sample(llm=None), {}) is True
    assert OnDemandReadOnly().may_auto_run(_Sample(llm=None), {"anything": "goes"}) is True

"""harness/registry.py: Skill base, SkillResult, REGISTRY, register(), validate_args()."""
import pytest

from harness.registry import REGISTRY, Skill, SkillResult, ValidationError, register, validate_args


def test_register_adds_to_registry_by_name():
    @register
    class _Sample(Skill):
        name = "sample_registry_test_skill"
        description = "d"
        schema = {}

        def run(self, **args):
            return SkillResult(content="ok")

    assert REGISTRY["sample_registry_test_skill"] is _Sample


def test_register_rejects_empty_name():
    with pytest.raises(ValueError):

        @register
        class _NoName(Skill):
            name = ""

            def run(self, **args):
                return SkillResult(content="ok")


def test_skill_run_not_implemented_on_base():
    with pytest.raises(NotImplementedError):
        Skill(llm=None).run()


def test_validate_args_requires_required_keys():
    schema = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}
    with pytest.raises(ValidationError):
        validate_args(schema, {})
    validate_args(schema, {"q": "hi"})  # does not raise


def test_validate_args_checks_declared_types():
    schema = {"type": "object", "properties": {"k": {"type": "integer"}}, "required": []}
    with pytest.raises(ValidationError):
        validate_args(schema, {"k": "not an int"})
    validate_args(schema, {"k": 5})  # does not raise


def test_validate_args_ignores_undeclared_extra_keys():
    schema = {"type": "object", "properties": {}, "required": []}
    validate_args(schema, {"extra": "fine"})  # does not raise

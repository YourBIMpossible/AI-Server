"""Skill base class + registry. Mirrors automation/_framework.py's Job pattern:
a base class with `name` + a behaviour method, a module-level REGISTRY dict, and
a @register decorator that fills it in on import."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

REGISTRY: dict[str, type["Skill"]] = {}


@dataclass(frozen=True)
class SkillResult:
    content: str
    metadata: dict[str, Any] | None = None


class Skill:
    name: str = ""
    description: str = ""
    schema: dict[str, Any] = {}  # JSON-Schema-shaped: {"type": "object", "properties": {...}, "required": [...]}

    def __init__(self, llm):
        self.llm = llm

    def run(self, **args: Any) -> SkillResult:
        raise NotImplementedError


def register(cls: type[Skill]) -> type[Skill]:
    if not cls.name:
        raise ValueError(f"{cls.__name__} must set a non-empty `name`")
    REGISTRY[cls.name] = cls
    return cls


class ValidationError(ValueError):
    """Raised by validate_args; the loop catches this and records a
    `validation_failed` transcript event instead of letting it propagate."""


_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


def validate_args(schema: dict[str, Any], args: dict[str, Any]) -> None:
    """Minimal, stdlib-only structural check: required keys present, declared
    types match. Not a full JSON-Schema implementation (no additionalProperties/
    nested-object/pattern support) -- v1's skills have flat, simple argument
    shapes and don't need one. Undeclared extra keys are ignored, matching
    JSON Schema's default (additionalProperties: true) behaviour."""
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in args:
            raise ValidationError(f"missing required argument {key!r}")
    for key, value in args.items():
        expected = _TYPES.get(props.get(key, {}).get("type"))
        if expected and not isinstance(value, expected):
            raise ValidationError(
                f"argument {key!r} must be {props[key]['type']}, got {type(value).__name__}"
            )

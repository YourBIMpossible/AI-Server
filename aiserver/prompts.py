"""Named prompt templates. Add new ones here, not inline in jobs."""

DIGEST = (
    "You are summarizing a solo developer's recent work logs. Produce a tight digest with "
    "three short sections: **Shipped / progressed**, **Key decisions**, and "
    "**Open threads / next**. Use terse bullets. Only use facts present in the logs.\n\n"
    "LOGS:\n{corpus}"
)

WEEKLY_ROLLUP = (
    "Roll up a week of a solo developer's build and decision logs into a status note: what "
    "shipped, decisions made, and what's open heading into next week. Terse bullets, facts "
    "only.\n\nLOGS:\n{corpus}"
)


def render(template: str, **kwargs: str) -> str:
    """Fill a template by name, e.g. render(DIGEST, corpus=text)."""
    return template.format(**kwargs)

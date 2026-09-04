"""Shared property_id resolution.

An LLM subagent's property_id argument frequently doesn't exactly match the
underscored slug ingestion actually stores (e.g. "Champions Pointe" or
"champions-pointe" instead of "champions_pointe") — even with an explicit
prompt instruction to look the exact id up via list_properties first (spec-
required, but not perfectly reliable across models/runs). This resolves any
reasonable variant against the real list of known property_ids, so
retrieval doesn't silently return zero results just because the model
phrased the id slightly differently than expected.
"""

import re


def _collapse(value: str) -> str:
    """Lowercase and strip every non-alphanumeric character, for
    separator-insensitive comparison — 'Champions Pointe', 'champions-pointe',
    and 'champions_pointe' all collapse to 'championspointe'."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def resolve_property_id(raw: str, known_property_ids: list[str]) -> str:
    """Return the canonical property_id from known_property_ids matching raw,
    if any; otherwise return raw unchanged (so callers with no known list, or
    a genuinely novel id, still behave as before)."""
    if raw in known_property_ids:
        return raw
    target = _collapse(raw)
    for candidate in known_property_ids:
        if _collapse(candidate) == target:
            return candidate
    return raw

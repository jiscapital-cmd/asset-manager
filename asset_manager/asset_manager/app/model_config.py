"""Global-default + per-agent-override model selection (spec Section 5)."""

AGENT_NAMES = ["financial-agent", "pm-agent", "capex-agent", "risk-agent"]

AVAILABLE_MODELS = [
    "openai/gpt-4o-mini",
    "openai/gpt-4.1",
    "anthropic/claude-sonnet-4.5",
    "anthropic/claude-haiku-4.5",
]


def resolve_model_overrides(default_model: str, overrides: dict[str, str]) -> dict[str, str]:
    """Return {agent_name: model} for every agent, using overrides where given."""
    return {name: overrides.get(name, default_model) for name in AGENT_NAMES}

from asset_manager.app.model_config import AGENT_NAMES, resolve_model_overrides


def test_resolve_model_overrides_fills_all_agents_with_default():
    result = resolve_model_overrides("openai/gpt-4o-mini", overrides={})
    assert set(result.keys()) == set(AGENT_NAMES)
    assert all(v == "openai/gpt-4o-mini" for v in result.values())


def test_resolve_model_overrides_respects_explicit_override():
    result = resolve_model_overrides(
        "openai/gpt-4o-mini",
        overrides={"risk-agent": "anthropic/claude-sonnet-4.5"},
    )
    assert result["risk-agent"] == "anthropic/claude-sonnet-4.5"
    assert result["pm-agent"] == "openai/gpt-4o-mini"

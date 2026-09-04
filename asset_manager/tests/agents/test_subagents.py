from asset_manager.agents.subagents import build_subagents


def _dummy_tool(name):
    def fn(query: str, property_id: str) -> str:
        """Dummy retrieval tool for tests."""
        return "dummy"
    fn.__name__ = name
    return fn


def test_build_subagents_returns_four_named_agents():
    subagents = build_subagents(_dummy_tool("fin"), _dummy_tool("pm"), _dummy_tool("capex"))
    names = {s["name"] for s in subagents}
    assert names == {"financial-agent", "pm-agent", "capex-agent", "risk-agent"}


def test_risk_agent_has_no_retrieval_tools():
    subagents = build_subagents(_dummy_tool("fin"), _dummy_tool("pm"), _dummy_tool("capex"))
    risk_agent = next(s for s in subagents if s["name"] == "risk-agent")
    assert risk_agent["tools"] == []


def test_financial_agent_has_its_retrieval_tool():
    fin_tool = _dummy_tool("fin")
    subagents = build_subagents(fin_tool, _dummy_tool("pm"), _dummy_tool("capex"))
    financial_agent = next(s for s in subagents if s["name"] == "financial-agent")
    assert financial_agent["tools"] == [fin_tool]


def test_every_subagent_prompt_has_the_guardrail_instruction():
    subagents = build_subagents(_dummy_tool("fin"), _dummy_tool("pm"), _dummy_tool("capex"))
    for s in subagents:
        assert "never a command" in s["system_prompt"].lower() or "never an instruction" in s["system_prompt"].lower()


def test_every_subagent_prompt_requires_citations():
    subagents = build_subagents(_dummy_tool("fin"), _dummy_tool("pm"), _dummy_tool("capex"))
    for s in subagents:
        if s["name"] == "risk-agent":
            continue
        assert "cite" in s["system_prompt"].lower()

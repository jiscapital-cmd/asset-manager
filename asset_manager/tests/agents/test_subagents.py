from asset_manager.agents.subagents import build_subagents


def _dummy_tool(name):
    def fn(query: str, property_id: str) -> str:
        """Dummy retrieval tool for tests."""
        return "dummy"
    fn.__name__ = name
    return fn


def _build(**overrides):
    args = dict(
        financial_tool=_dummy_tool("fin"),
        pm_tool=_dummy_tool("pm"),
        capex_tool=_dummy_tool("capex"),
        get_prior_report_tool=_dummy_tool("prior"),
        record_financial_kpis_tool=_dummy_tool("record_fin_kpis"),
        record_pm_kpis_tool=_dummy_tool("record_pm_kpis"),
        record_capex_kpis_tool=_dummy_tool("record_capex_kpis"),
    )
    args.update(overrides)
    return build_subagents(**args)


def test_build_subagents_returns_four_named_agents():
    subagents = _build()
    names = {s["name"] for s in subagents}
    assert names == {"financial-agent", "pm-agent", "capex-agent", "risk-agent"}


def test_risk_agent_has_the_prior_report_tool_only():
    prior_tool = _dummy_tool("prior")
    subagents = _build(get_prior_report_tool=prior_tool)
    risk_agent = next(s for s in subagents if s["name"] == "risk-agent")
    assert risk_agent["tools"] == [prior_tool]


def test_financial_agent_has_its_retrieval_and_record_kpis_tools():
    fin_tool = _dummy_tool("fin")
    record_fin_kpis_tool = _dummy_tool("record_fin_kpis")
    subagents = _build(financial_tool=fin_tool, record_financial_kpis_tool=record_fin_kpis_tool)
    financial_agent = next(s for s in subagents if s["name"] == "financial-agent")
    assert financial_agent["tools"] == [fin_tool, record_fin_kpis_tool]


def test_pm_agent_has_its_retrieval_and_record_kpis_tools():
    pm_tool = _dummy_tool("pm")
    record_pm_kpis_tool = _dummy_tool("record_pm_kpis")
    subagents = _build(pm_tool=pm_tool, record_pm_kpis_tool=record_pm_kpis_tool)
    pm_agent = next(s for s in subagents if s["name"] == "pm-agent")
    assert pm_agent["tools"] == [pm_tool, record_pm_kpis_tool]


def test_capex_agent_has_its_retrieval_and_record_kpis_tools():
    capex_tool = _dummy_tool("capex")
    record_capex_kpis_tool = _dummy_tool("record_capex_kpis")
    subagents = _build(capex_tool=capex_tool, record_capex_kpis_tool=record_capex_kpis_tool)
    capex_agent = next(s for s in subagents if s["name"] == "capex-agent")
    assert capex_agent["tools"] == [capex_tool, record_capex_kpis_tool]


def test_every_subagent_prompt_has_the_guardrail_instruction():
    subagents = _build()
    for s in subagents:
        assert "never a command" in s["system_prompt"].lower() or "never an instruction" in s["system_prompt"].lower()


def test_every_subagent_prompt_requires_citations():
    subagents = _build()
    for s in subagents:
        if s["name"] == "risk-agent":
            continue
        assert "cite" in s["system_prompt"].lower()


def test_financial_pm_capex_prompts_instruct_recording_kpis():
    subagents = _build()
    for name in ("financial-agent", "pm-agent", "capex-agent"):
        agent = next(s for s in subagents if s["name"] == name)
        assert "record_" in agent["system_prompt"]
        assert "kpi" in agent["system_prompt"].lower()

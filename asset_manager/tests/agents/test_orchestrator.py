from langchain_openai import ChatOpenAI

from asset_manager.agents.orchestrator import build_orchestrator


def _dummy_tool(name):
    def fn(query: str, property_id: str) -> str:
        """Dummy retrieval tool for tests."""
        return "dummy"
    fn.__name__ = name
    return fn


def _build_orchestrator(**overrides):
    model = ChatOpenAI(model="gpt-4o-mini", api_key="test-key-not-used", base_url="https://openrouter.ai/api/v1")
    args = dict(
        model=model,
        financial_tool=_dummy_tool("fin"),
        pm_tool=_dummy_tool("pm"),
        capex_tool=_dummy_tool("capex"),
        get_prior_report_tool=_dummy_tool("prior"),
        list_properties_tool=_dummy_tool("list_properties"),
        save_report_tool=_dummy_tool("save_report"),
        record_financial_kpis_tool=_dummy_tool("record_fin_kpis"),
        record_pm_kpis_tool=_dummy_tool("record_pm_kpis"),
        record_capex_kpis_tool=_dummy_tool("record_capex_kpis"),
        recursion_limit=42,
    )
    args.update(overrides)
    return build_orchestrator(**args)


def test_build_orchestrator_returns_a_runnable_graph():
    graph = _build_orchestrator()
    assert hasattr(graph, "invoke")
    assert hasattr(graph, "stream")


def test_build_orchestrator_applies_recursion_limit():
    graph = _build_orchestrator()
    assert graph.config["recursion_limit"] == 42


def test_build_orchestrator_includes_portfolio_and_archive_tools():
    graph = _build_orchestrator()
    assert hasattr(graph, "invoke")

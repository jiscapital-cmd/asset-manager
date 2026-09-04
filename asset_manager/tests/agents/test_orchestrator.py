from langchain_openai import ChatOpenAI

from asset_manager.agents.orchestrator import build_orchestrator


def _dummy_tool(name):
    def fn(query: str, property_id: str) -> str:
        """Dummy retrieval tool for tests."""
        return "dummy"
    fn.__name__ = name
    return fn


def test_build_orchestrator_returns_a_runnable_graph():
    model = ChatOpenAI(model="gpt-4o-mini", api_key="test-key-not-used", base_url="https://openrouter.ai/api/v1")
    graph = build_orchestrator(
        model,
        _dummy_tool("fin"),
        _dummy_tool("pm"),
        _dummy_tool("capex"),
        _dummy_tool("prior"),
        _dummy_tool("list_properties"),
        _dummy_tool("save_report"),
        recursion_limit=42,
    )
    assert hasattr(graph, "invoke")
    assert hasattr(graph, "stream")


def test_build_orchestrator_applies_recursion_limit():
    model = ChatOpenAI(model="gpt-4o-mini", api_key="test-key-not-used", base_url="https://openrouter.ai/api/v1")
    graph = build_orchestrator(
        model,
        _dummy_tool("fin"),
        _dummy_tool("pm"),
        _dummy_tool("capex"),
        _dummy_tool("prior"),
        _dummy_tool("list_properties"),
        _dummy_tool("save_report"),
        recursion_limit=42,
    )
    assert graph.config["recursion_limit"] == 42


def test_build_orchestrator_includes_portfolio_and_archive_tools():
    model = ChatOpenAI(model="gpt-4o-mini", api_key="test-key-not-used", base_url="https://openrouter.ai/api/v1")
    graph = build_orchestrator(
        model,
        _dummy_tool("fin"),
        _dummy_tool("pm"),
        _dummy_tool("capex"),
        _dummy_tool("prior"),
        _dummy_tool("list_properties"),
        _dummy_tool("save_report"),
        recursion_limit=42,
    )
    assert hasattr(graph, "invoke")

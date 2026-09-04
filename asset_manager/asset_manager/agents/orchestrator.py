from deepagents import create_deep_agent

from asset_manager.agents.prompts import ORCHESTRATOR_PROMPT
from asset_manager.agents.subagents import build_subagents


def build_orchestrator(
    model,
    financial_tool,
    pm_tool,
    capex_tool,
    get_prior_report_tool,
    list_properties_tool,
    save_report_tool,
    recursion_limit: int = 80,
):
    subagents = build_subagents(financial_tool, pm_tool, capex_tool, get_prior_report_tool)
    graph = create_deep_agent(
        model=model,
        tools=[list_properties_tool, save_report_tool],
        system_prompt=ORCHESTRATOR_PROMPT,
        subagents=subagents,
    )
    return graph.with_config({"recursion_limit": recursion_limit})

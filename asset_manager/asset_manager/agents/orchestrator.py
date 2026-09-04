from deepagents import create_deep_agent

from asset_manager.agents.prompts import ORCHESTRATOR_PROMPT
from asset_manager.agents.subagents import build_subagents

# Spec Section 7: "orchestrator recursion limit (~50-100 agent<->tools round-trips
# per question — higher for portfolio mode, since it runs 4 properties' worth of
# delegation)". A portfolio question runs wave 1 (3 parallel subagent calls) + wave
# 2 (1 risk-agent call) per property, plus list_properties/save_report and a final
# cross-property risk-agent synthesis call — for 4 properties that's on the order
# of 4 * 4 + a handful of orchestration steps, well past 80 once each delegated
# call's own internal tool-use steps are counted too. A single default ceiling,
# generous enough for the worst case (portfolio mode), is simpler and safer than
# guessing the mode from the question's wording before the graph even runs — the
# limit is just a cap, so single-property questions finish in far fewer steps and
# pay no cost for the higher ceiling.
DEFAULT_RECURSION_LIMIT = 200


def build_orchestrator(
    model,
    financial_tool,
    pm_tool,
    capex_tool,
    get_prior_report_tool,
    list_properties_tool,
    save_report_tool,
    recursion_limit: int = DEFAULT_RECURSION_LIMIT,
):
    subagents = build_subagents(financial_tool, pm_tool, capex_tool, get_prior_report_tool)
    graph = create_deep_agent(
        model=model,
        tools=[list_properties_tool, save_report_tool],
        system_prompt=ORCHESTRATOR_PROMPT,
        subagents=subagents,
    )
    return graph.with_config({"recursion_limit": recursion_limit})

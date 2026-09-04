from asset_manager.agents.prompts import (
    CAPEX_AGENT_PROMPT,
    FINANCIAL_AGENT_PROMPT,
    PM_AGENT_PROMPT,
    RISK_AGENT_PROMPT,
)


def build_subagents(financial_tool, pm_tool, capex_tool, get_prior_report_tool) -> list[dict]:
    return [
        {
            "name": "financial-agent",
            "description": (
                "Analyzes budget-vs-actual, NOI trend, and income stability for one property. "
                "Call with a specific property_id."
            ),
            "system_prompt": FINANCIAL_AGENT_PROMPT,
            "tools": [financial_tool],
        },
        {
            "name": "pm-agent",
            "description": (
                "Analyzes occupancy, leasing pipeline, maintenance backlog, and tenant sentiment "
                "for one property. Call with a specific property_id."
            ),
            "system_prompt": PM_AGENT_PROMPT,
            "tools": [pm_tool],
        },
        {
            "name": "capex-agent",
            "description": (
                "Analyzes deferred maintenance and produces a prioritized, budgeted capital plan "
                "for one property. Call with a specific property_id."
            ),
            "system_prompt": CAPEX_AGENT_PROMPT,
            "tools": [capex_tool],
        },
        {
            "name": "risk-agent",
            "description": (
                "Synthesizes financial/pm/capex findings into severity scores and a recommended "
                "action, diffed against the prior report if one exists. Call only after "
                "financial-agent, pm-agent, and capex-agent have all returned for the same "
                "property (or properties, for a portfolio question)."
            ),
            "system_prompt": RISK_AGENT_PROMPT,
            "tools": [get_prior_report_tool],
        },
    ]

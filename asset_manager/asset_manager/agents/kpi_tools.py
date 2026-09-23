"""Tools that let financial-agent, pm-agent, and capex-agent report the
numeric KPIs autonomous monitoring (asset_manager/automation/monitor.py)
evaluates against fixed thresholds — each subagent reports only the fields
its own domain already retrieves; asset_manager/monitoring/kpis.py's
KPICollector merges them per property_id."""

from langchain_core.tools import tool

from asset_manager.monitoring.kpis import KPICollector
from asset_manager.property_ids import resolve_property_id


def make_record_financial_kpis_tool(collector: KPICollector, known_property_ids: list[str] | None = None):
    @tool(name_or_callable="record_financial_kpis")
    def record_financial_kpis(
        property_id: str, noi_variance_pct: float | None, delinquency_pct: float | None
    ) -> str:
        """Record this property's NOI-variance-vs-budget and delinquency figures for
        autonomous monitoring, in addition to your narrative report. Call exactly
        once per property_id you analyze.

        Args:
            property_id: which property these figures are for.
            noi_variance_pct: actual NOI vs. budgeted NOI, as a percentage (negative
                = below budget). Pass null if DATA NOT AVAILABLE — never estimate or
                use zero.
            delinquency_pct: delinquent/uncollected rent as a percentage of the rent
                roll. Pass null if DATA NOT AVAILABLE.
        """
        if known_property_ids:
            property_id = resolve_property_id(property_id, known_property_ids)
        collector.record(property_id, noi_variance_pct=noi_variance_pct, delinquency_pct=delinquency_pct)
        return f"Recorded financial KPIs for {property_id}."

    return record_financial_kpis


def make_record_pm_kpis_tool(collector: KPICollector, known_property_ids: list[str] | None = None):
    @tool(name_or_callable="record_pm_kpis")
    def record_pm_kpis(property_id: str, occupancy_pct: float | None, rollover_90d_pct: float | None) -> str:
        """Record this property's occupancy and 90-day lease-rollover figures for
        autonomous monitoring, in addition to your narrative report. Call exactly
        once per property_id you analyze.

        Args:
            property_id: which property these figures are for.
            occupancy_pct: current occupancy as a fraction (e.g. 0.92 for 92%). Pass
                null if DATA NOT AVAILABLE — never estimate or use zero.
            rollover_90d_pct: percentage of units with leases expiring in the next
                90 days. Pass null if DATA NOT AVAILABLE.
        """
        if known_property_ids:
            property_id = resolve_property_id(property_id, known_property_ids)
        collector.record(property_id, occupancy_pct=occupancy_pct, rollover_90d_pct=rollover_90d_pct)
        return f"Recorded PM KPIs for {property_id}."

    return record_pm_kpis


def make_record_capex_kpis_tool(collector: KPICollector, known_property_ids: list[str] | None = None):
    @tool(name_or_callable="record_capex_kpis")
    def record_capex_kpis(property_id: str, critical_capex_count: int | None) -> str:
        """Record this property's count of critical/overdue CapEx or maintenance
        items for autonomous monitoring, in addition to your narrative report. Call
        exactly once per property_id you analyze.

        Args:
            property_id: which property this figure is for.
            critical_capex_count: number of critical or overdue CapEx/maintenance
                items outstanding. Pass null if DATA NOT AVAILABLE — never estimate
                or use zero when the true count is unknown.
        """
        if known_property_ids:
            property_id = resolve_property_id(property_id, known_property_ids)
        collector.record(property_id, critical_capex_count=critical_capex_count)
        return f"Recorded CapEx KPIs for {property_id}."

    return record_capex_kpis

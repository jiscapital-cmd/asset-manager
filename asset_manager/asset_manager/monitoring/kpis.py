"""Numeric KPI tracking for autonomous portfolio monitoring.

Deliberately independent of the LLM/agent layer: financial/pm/capex-agents
report these numbers via tool calls (see agents/kpi_tools.py), but the
threshold comparison itself is plain, deterministic, and fully unit-testable
without any model call. A None field means the agent reported the underlying
data as unavailable — it is skipped, never treated as zero or as a breach,
matching the DATA_RULE convention in agents/prompts.py.
"""

import os
from dataclasses import dataclass, fields


@dataclass
class PropertyKPIs:
    property_id: str
    occupancy_pct: float | None = None
    noi_variance_pct: float | None = None  # negative = below budget
    delinquency_pct: float | None = None
    rollover_90d_pct: float | None = None
    critical_capex_count: int | None = None


@dataclass
class KPIThresholds:
    occupancy_alert_below: float = 0.90
    noi_variance_alert_pct: float = 10.0
    delinquency_alert_above_pct: float = 5.0
    rollover_90d_alert_pct: float = 20.0
    critical_capex_alert_count: int = 1


def load_thresholds_from_env() -> KPIThresholds:
    defaults = KPIThresholds()
    return KPIThresholds(
        occupancy_alert_below=float(os.environ.get("OCCUPANCY_ALERT_BELOW", defaults.occupancy_alert_below)),
        noi_variance_alert_pct=float(os.environ.get("NOI_VARIANCE_ALERT_PCT", defaults.noi_variance_alert_pct)),
        delinquency_alert_above_pct=float(
            os.environ.get("DELINQUENCY_ALERT_ABOVE_PCT", defaults.delinquency_alert_above_pct)
        ),
        rollover_90d_alert_pct=float(os.environ.get("ROLLOVER_90D_ALERT_PCT", defaults.rollover_90d_alert_pct)),
        critical_capex_alert_count=int(
            os.environ.get("CRITICAL_CAPEX_ALERT_COUNT", defaults.critical_capex_alert_count)
        ),
    )


def evaluate_kpis(kpis: PropertyKPIs, thresholds: KPIThresholds) -> list[str]:
    breaches: list[str] = []

    if kpis.occupancy_pct is not None and kpis.occupancy_pct < thresholds.occupancy_alert_below:
        breaches.append(
            f"occupancy {kpis.occupancy_pct:.0%} is below the {thresholds.occupancy_alert_below:.0%} threshold"
        )

    if kpis.noi_variance_pct is not None and kpis.noi_variance_pct < -thresholds.noi_variance_alert_pct:
        breaches.append(
            f"NOI variance {kpis.noi_variance_pct:.1f}% is worse than the "
            f"-{thresholds.noi_variance_alert_pct:.0f}% threshold"
        )

    if kpis.delinquency_pct is not None and kpis.delinquency_pct > thresholds.delinquency_alert_above_pct:
        breaches.append(
            f"delinquency {kpis.delinquency_pct:.1f}% is above the "
            f"{thresholds.delinquency_alert_above_pct:.0f}% threshold"
        )

    if kpis.rollover_90d_pct is not None and kpis.rollover_90d_pct > thresholds.rollover_90d_alert_pct:
        breaches.append(
            f"90-day lease rollover {kpis.rollover_90d_pct:.0f}% exceeds the "
            f"{thresholds.rollover_90d_alert_pct:.0f}% threshold"
        )

    if kpis.critical_capex_count is not None and kpis.critical_capex_count >= thresholds.critical_capex_alert_count:
        breaches.append(f"{kpis.critical_capex_count} critical/overdue CapEx item(s) outstanding")

    return breaches


_RECORD_FIELDS = {f.name for f in fields(PropertyKPIs) if f.name != "property_id"}


class KPICollector:
    """Merges KPI fields reported by different subagents for the same
    property_id — financial-agent reports 2 fields, pm-agent 2, capex-agent
    1, each unaware of the others' fields."""

    def __init__(self) -> None:
        self._data: dict[str, PropertyKPIs] = {}

    def record(self, property_id: str, **field_values) -> None:
        unknown = set(field_values) - _RECORD_FIELDS
        if unknown:
            raise TypeError(f"Unknown KPI field(s): {sorted(unknown)}")

        existing = self._data.get(property_id, PropertyKPIs(property_id=property_id))
        for name, value in field_values.items():
            if value is not None:
                setattr(existing, name, value)
        self._data[property_id] = existing

    def get(self, property_id: str) -> PropertyKPIs | None:
        return self._data.get(property_id)

    def all(self) -> dict[str, PropertyKPIs]:
        return dict(self._data)

from asset_manager.agents.kpi_tools import (
    make_record_capex_kpis_tool,
    make_record_financial_kpis_tool,
    make_record_pm_kpis_tool,
)
from asset_manager.monitoring.kpis import KPICollector


def test_record_financial_kpis_tool_stores_values():
    collector = KPICollector()
    tool = make_record_financial_kpis_tool(collector)
    tool.invoke({"property_id": "champions-pointe", "noi_variance_pct": -12.0, "delinquency_pct": 4.5})

    kpis = collector.get("champions-pointe")
    assert kpis.noi_variance_pct == -12.0
    assert kpis.delinquency_pct == 4.5


def test_record_financial_kpis_tool_accepts_null_for_unavailable_data():
    collector = KPICollector()
    tool = make_record_financial_kpis_tool(collector)
    tool.invoke({"property_id": "champions-pointe", "noi_variance_pct": None, "delinquency_pct": 4.5})

    kpis = collector.get("champions-pointe")
    assert kpis.noi_variance_pct is None
    assert kpis.delinquency_pct == 4.5


def test_record_pm_kpis_tool_stores_values():
    collector = KPICollector()
    tool = make_record_pm_kpis_tool(collector)
    tool.invoke({"property_id": "champions-pointe", "occupancy_pct": 0.86, "rollover_90d_pct": 15.0})

    kpis = collector.get("champions-pointe")
    assert kpis.occupancy_pct == 0.86
    assert kpis.rollover_90d_pct == 15.0


def test_record_capex_kpis_tool_stores_values():
    collector = KPICollector()
    tool = make_record_capex_kpis_tool(collector)
    tool.invoke({"property_id": "champions-pointe", "critical_capex_count": 2})

    kpis = collector.get("champions-pointe")
    assert kpis.critical_capex_count == 2


def test_record_financial_kpis_tool_resolves_property_id_variant_when_known_ids_given():
    collector = KPICollector()
    tool = make_record_financial_kpis_tool(collector, known_property_ids=["champions_pointe"])
    tool.invoke({"property_id": "Champions Pointe", "noi_variance_pct": -5.0, "delinquency_pct": 2.0})

    assert collector.get("champions_pointe").noi_variance_pct == -5.0
    assert collector.get("Champions Pointe") is None


def test_record_pm_kpis_tool_resolves_property_id_variant_when_known_ids_given():
    collector = KPICollector()
    tool = make_record_pm_kpis_tool(collector, known_property_ids=["champions_pointe"])
    tool.invoke({"property_id": "Champions Pointe", "occupancy_pct": 0.9, "rollover_90d_pct": 10.0})

    assert collector.get("champions_pointe").occupancy_pct == 0.9


def test_record_capex_kpis_tool_resolves_property_id_variant_when_known_ids_given():
    collector = KPICollector()
    tool = make_record_capex_kpis_tool(collector, known_property_ids=["champions_pointe"])
    tool.invoke({"property_id": "Champions Pointe", "critical_capex_count": 1})

    assert collector.get("champions_pointe").critical_capex_count == 1

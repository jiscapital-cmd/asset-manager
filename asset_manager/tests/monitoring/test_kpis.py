import pytest

from asset_manager.monitoring.kpis import (
    KPICollector,
    KPIThresholds,
    PropertyKPIs,
    evaluate_kpis,
    load_thresholds_from_env,
)

DEFAULT_THRESHOLDS = KPIThresholds()


# --- KPICollector -------------------------------------------------------------


def test_collector_merges_fields_from_separate_calls_without_clobbering():
    collector = KPICollector()
    collector.record("champions_pointe", occupancy_pct=0.86, rollover_90d_pct=15.0)
    collector.record("champions_pointe", noi_variance_pct=-12.0, delinquency_pct=3.0)
    collector.record("champions_pointe", critical_capex_count=2)

    kpis = collector.get("champions_pointe")
    assert kpis == PropertyKPIs(
        property_id="champions_pointe",
        occupancy_pct=0.86,
        rollover_90d_pct=15.0,
        noi_variance_pct=-12.0,
        delinquency_pct=3.0,
        critical_capex_count=2,
    )


def test_collector_keeps_properties_separate():
    collector = KPICollector()
    collector.record("champions_pointe", occupancy_pct=0.86)
    collector.record("garfield_vista", occupancy_pct=0.95)

    assert collector.get("champions_pointe").occupancy_pct == 0.86
    assert collector.get("garfield_vista").occupancy_pct == 0.95
    assert set(collector.all().keys()) == {"champions_pointe", "garfield_vista"}


def test_collector_get_returns_none_for_unknown_property():
    collector = KPICollector()
    assert collector.get("unknown") is None


def test_collector_ignores_none_valued_fields_so_they_dont_overwrite_a_known_value():
    collector = KPICollector()
    collector.record("champions_pointe", occupancy_pct=0.86)
    collector.record("champions_pointe", occupancy_pct=None)

    assert collector.get("champions_pointe").occupancy_pct == 0.86


# --- evaluate_kpis --------------------------------------------------------------


def test_no_breaches_when_all_kpis_within_thresholds():
    kpis = PropertyKPIs(
        property_id="champions_pointe",
        occupancy_pct=0.95,
        noi_variance_pct=-2.0,
        delinquency_pct=1.0,
        rollover_90d_pct=5.0,
        critical_capex_count=0,
    )
    assert evaluate_kpis(kpis, DEFAULT_THRESHOLDS) == []


def test_occupancy_below_threshold_breaches():
    kpis = PropertyKPIs(property_id="p", occupancy_pct=0.86)
    breaches = evaluate_kpis(kpis, DEFAULT_THRESHOLDS)
    assert len(breaches) == 1
    assert "occupancy" in breaches[0].lower()
    assert "86" in breaches[0]


def test_occupancy_at_exactly_threshold_does_not_breach():
    kpis = PropertyKPIs(property_id="p", occupancy_pct=0.90)
    assert evaluate_kpis(kpis, DEFAULT_THRESHOLDS) == []


def test_noi_variance_worse_than_threshold_breaches():
    kpis = PropertyKPIs(property_id="p", noi_variance_pct=-15.0)
    breaches = evaluate_kpis(kpis, DEFAULT_THRESHOLDS)
    assert len(breaches) == 1
    assert "noi" in breaches[0].lower()


def test_noi_variance_above_budget_does_not_breach():
    kpis = PropertyKPIs(property_id="p", noi_variance_pct=8.0)
    assert evaluate_kpis(kpis, DEFAULT_THRESHOLDS) == []


def test_delinquency_above_threshold_breaches():
    kpis = PropertyKPIs(property_id="p", delinquency_pct=7.5)
    breaches = evaluate_kpis(kpis, DEFAULT_THRESHOLDS)
    assert len(breaches) == 1
    assert "delinquency" in breaches[0].lower()


def test_rollover_above_threshold_breaches():
    kpis = PropertyKPIs(property_id="p", rollover_90d_pct=25.0)
    breaches = evaluate_kpis(kpis, DEFAULT_THRESHOLDS)
    assert len(breaches) == 1
    assert "rollover" in breaches[0].lower()


def test_any_critical_capex_item_breaches():
    kpis = PropertyKPIs(property_id="p", critical_capex_count=1)
    breaches = evaluate_kpis(kpis, DEFAULT_THRESHOLDS)
    assert len(breaches) == 1
    assert "capex" in breaches[0].lower()


def test_zero_critical_capex_items_does_not_breach():
    kpis = PropertyKPIs(property_id="p", critical_capex_count=0)
    assert evaluate_kpis(kpis, DEFAULT_THRESHOLDS) == []


def test_missing_data_never_treated_as_a_breach():
    # All fields None ("DATA NOT AVAILABLE") must never be treated as zero
    # or as a violation — matches the DATA_RULE convention used throughout
    # agents/prompts.py.
    kpis = PropertyKPIs(property_id="p")
    assert evaluate_kpis(kpis, DEFAULT_THRESHOLDS) == []


def test_multiple_simultaneous_breaches_are_all_reported():
    kpis = PropertyKPIs(
        property_id="p",
        occupancy_pct=0.80,
        noi_variance_pct=-20.0,
        delinquency_pct=9.0,
        rollover_90d_pct=30.0,
        critical_capex_count=3,
    )
    breaches = evaluate_kpis(kpis, DEFAULT_THRESHOLDS)
    assert len(breaches) == 5


def test_custom_thresholds_are_respected():
    thresholds = KPIThresholds(occupancy_alert_below=0.98)
    kpis = PropertyKPIs(property_id="p", occupancy_pct=0.95)
    breaches = evaluate_kpis(kpis, thresholds)
    assert len(breaches) == 1


# --- load_thresholds_from_env ---------------------------------------------------


def test_load_thresholds_from_env_uses_defaults_when_unset(monkeypatch):
    for var in (
        "OCCUPANCY_ALERT_BELOW",
        "NOI_VARIANCE_ALERT_PCT",
        "DELINQUENCY_ALERT_ABOVE_PCT",
        "ROLLOVER_90D_ALERT_PCT",
        "CRITICAL_CAPEX_ALERT_COUNT",
    ):
        monkeypatch.delenv(var, raising=False)

    thresholds = load_thresholds_from_env()
    assert thresholds == KPIThresholds()


def test_load_thresholds_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("OCCUPANCY_ALERT_BELOW", "0.95")
    monkeypatch.setenv("NOI_VARIANCE_ALERT_PCT", "5")
    monkeypatch.setenv("DELINQUENCY_ALERT_ABOVE_PCT", "3")
    monkeypatch.setenv("ROLLOVER_90D_ALERT_PCT", "10")
    monkeypatch.setenv("CRITICAL_CAPEX_ALERT_COUNT", "2")

    thresholds = load_thresholds_from_env()
    assert thresholds == KPIThresholds(
        occupancy_alert_below=0.95,
        noi_variance_alert_pct=5.0,
        delinquency_alert_above_pct=3.0,
        rollover_90d_alert_pct=10.0,
        critical_capex_alert_count=2,
    )

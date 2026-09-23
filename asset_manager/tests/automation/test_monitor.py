from asset_manager.automation.monitor import run_monitor_forever, run_monitor_once
from asset_manager.monitoring.kpis import KPIThresholds, PropertyKPIs

THRESHOLDS = KPIThresholds()


def _kpis(property_id: str, **fields) -> dict[str, PropertyKPIs]:
    return {property_id: PropertyKPIs(property_id=property_id, **fields)}


def test_run_monitor_once_quiet_when_no_breaches():
    notified = []
    logged = []

    def fake_run_portfolio_review():
        return "# Portfolio Review\nAll properties stable.", _kpis(
            "champions-pointe", occupancy_pct=0.95, critical_capex_count=0
        )

    result = run_monitor_once(
        run_portfolio_review_fn=fake_run_portfolio_review,
        thresholds=THRESHOLDS,
        export_pdf_fn=lambda t, c: b"pdf-bytes",
        notify_fn=lambda m: notified.append(m),
        log_fn=lambda m: logged.append(m),
    )

    assert result.ran is True
    assert result.alerted is False
    assert result.breaches == {}
    assert notified == []
    assert len(logged) == 1
    assert "no" in logged[0].lower()


def test_run_monitor_once_alerts_when_a_property_breaches():
    notified = []
    sent_files = []

    def fake_run_portfolio_review():
        return "# Portfolio Review", _kpis("champions-pointe", occupancy_pct=0.80, critical_capex_count=2)

    result = run_monitor_once(
        run_portfolio_review_fn=fake_run_portfolio_review,
        thresholds=THRESHOLDS,
        export_pdf_fn=lambda t, c: b"pdf-bytes",
        notify_fn=lambda m: notified.append(m),
        send_file_fn=lambda filename, content: sent_files.append((filename, content)),
    )

    assert result.ran is True
    assert result.alerted is True
    assert "champions-pointe" in result.breaches
    assert len(notified) == 1
    assert "champions-pointe" in notified[0].lower()
    assert "occupancy" in notified[0].lower()
    assert len(sent_files) == 1
    assert sent_files[0][1] == b"pdf-bytes"


def test_run_monitor_once_alert_message_names_every_breaching_property():
    def fake_run_portfolio_review():
        return "# Portfolio Review", {
            "champions-pointe": PropertyKPIs(property_id="champions-pointe", occupancy_pct=0.80),
            "garfield-vista": PropertyKPIs(property_id="garfield-vista", critical_capex_count=3),
            "memorial-apartments": PropertyKPIs(property_id="memorial-apartments", occupancy_pct=0.96),
        }

    notified = []
    result = run_monitor_once(
        run_portfolio_review_fn=fake_run_portfolio_review,
        thresholds=THRESHOLDS,
        export_pdf_fn=lambda t, c: b"pdf-bytes",
        notify_fn=lambda m: notified.append(m),
    )

    assert set(result.breaches.keys()) == {"champions-pointe", "garfield-vista"}
    assert "champions-pointe" in notified[0]
    assert "garfield-vista" in notified[0]
    assert "memorial-apartments" not in notified[0]


def test_run_monitor_once_does_not_send_file_without_send_file_fn():
    def fake_run_portfolio_review():
        return "# Portfolio Review", _kpis("champions-pointe", occupancy_pct=0.5)

    # Should not raise even though send_file_fn is omitted.
    result = run_monitor_once(
        run_portfolio_review_fn=fake_run_portfolio_review,
        thresholds=THRESHOLDS,
        export_pdf_fn=lambda t, c: b"pdf-bytes",
        notify_fn=lambda m: None,
    )
    assert result.alerted is True


def test_run_monitor_once_notifies_and_marks_not_ran_on_review_failure():
    notified = []

    def flaky_run_portfolio_review():
        raise RuntimeError("orchestrator timed out")

    result = run_monitor_once(
        run_portfolio_review_fn=flaky_run_portfolio_review,
        thresholds=THRESHOLDS,
        export_pdf_fn=lambda t, c: b"pdf-bytes",
        notify_fn=lambda m: notified.append(m),
    )

    assert result.ran is False
    assert result.alerted is True
    assert len(notified) == 1
    assert "failed" in notified[0].lower()


def test_run_monitor_once_alerts_when_no_property_kpi_data_was_recorded():
    """Regression: a live run once completed without error but the
    orchestrator never delegated to any subagent, so kpi_collector.all()
    came back empty — silently logging "0 properties checked, no breaches"
    would have looked identical to a genuinely healthy portfolio. An empty
    result must be treated as an incomplete run, not a clean one."""
    notified = []
    logged = []

    def fake_run_portfolio_review():
        return "# Portfolio Review", {}

    result = run_monitor_once(
        run_portfolio_review_fn=fake_run_portfolio_review,
        thresholds=THRESHOLDS,
        export_pdf_fn=lambda t, c: b"pdf-bytes",
        notify_fn=lambda m: notified.append(m),
        log_fn=lambda m: logged.append(m),
    )

    assert result.ran is True
    assert result.alerted is True
    assert result.breaches == {}
    assert len(notified) == 1
    assert "no property kpi data" in notified[0].lower() or "not have completed" in notified[0].lower()


def test_run_monitor_once_missing_data_never_causes_a_breach():
    def fake_run_portfolio_review():
        return "# Portfolio Review", _kpis("champions-pointe")  # every field None

    notified = []
    result = run_monitor_once(
        run_portfolio_review_fn=fake_run_portfolio_review,
        thresholds=THRESHOLDS,
        export_pdf_fn=lambda t, c: b"pdf-bytes",
        notify_fn=lambda m: notified.append(m),
    )

    assert result.alerted is False
    assert notified == []


# --- run_monitor_forever --------------------------------------------------------


def test_run_monitor_forever_runs_max_iterations_and_sleeps_between():
    calls = []
    sleeps = []

    def fake_run_once():
        calls.append(1)
        return None

    run_monitor_forever(
        run_once_fn=fake_run_once,
        interval_seconds=60,
        sleep_fn=lambda seconds: sleeps.append(seconds),
        max_iterations=3,
    )

    assert len(calls) == 3
    assert sleeps == [60, 60, 60]


def test_run_monitor_forever_continues_after_an_iteration_raises():
    calls = []

    def flaky_run_once():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return None

    run_monitor_forever(
        run_once_fn=flaky_run_once,
        interval_seconds=10,
        sleep_fn=lambda seconds: None,
        max_iterations=3,
    )

    assert len(calls) == 3


def test_run_monitor_forever_logs_each_iteration_failure():
    logged = []

    def flaky_run_once():
        raise RuntimeError("boom")

    run_monitor_forever(
        run_once_fn=flaky_run_once,
        interval_seconds=10,
        sleep_fn=lambda seconds: None,
        max_iterations=1,
        log_fn=lambda m: logged.append(m),
    )

    assert any("boom" in m for m in logged)

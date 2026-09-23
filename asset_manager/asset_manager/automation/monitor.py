"""Autonomous KPI-driven portfolio monitoring — runs on its own schedule and
decides for itself whether a Slack alert is warranted, unlike
scheduled_review.py's endpoints, which always notify whenever n8n calls
them. Standalone entrypoint: `python -m asset_manager.automation.monitor`."""

import time
from dataclasses import dataclass, field
from typing import Callable

from asset_manager.monitoring.kpis import KPIThresholds, PropertyKPIs, evaluate_kpis


@dataclass
class MonitorRunResult:
    ran: bool
    alerted: bool
    breaches: dict[str, list[str]] = field(default_factory=dict)
    report_text: str | None = None


def run_monitor_once(
    run_portfolio_review_fn: Callable[[], tuple[str, dict[str, PropertyKPIs]]],
    thresholds: KPIThresholds,
    export_pdf_fn: Callable[[str, str], bytes],
    notify_fn: Callable[[str], None],
    send_file_fn: Callable[[str, bytes], None] | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> MonitorRunResult:
    log = log_fn or (lambda message: None)

    try:
        report_text, kpis_by_property = run_portfolio_review_fn()
    except Exception as exc:
        notify_fn(f"Autonomous monitoring run failed: {exc}")
        return MonitorRunResult(ran=False, alerted=True)

    if not kpis_by_property:
        # Observed in practice: the orchestrator can complete without error
        # but skip delegating to any subagent, so no record_*_kpis tool call
        # ever fires. Silently logging "0 properties checked, no breaches"
        # would be indistinguishable from a genuinely healthy portfolio —
        # treat an empty result as an incomplete run, not a clean one.
        notify_fn(
            "Autonomous monitoring run completed without any property KPI data — "
            "the review may not have completed as expected. No alert conditions "
            "could be evaluated this cycle."
        )
        return MonitorRunResult(ran=True, alerted=True, report_text=report_text)

    breaches: dict[str, list[str]] = {}
    for property_id, kpis in kpis_by_property.items():
        property_breaches = evaluate_kpis(kpis, thresholds)
        if property_breaches:
            breaches[property_id] = property_breaches

    if not breaches:
        log(f"Monitoring run complete — {len(kpis_by_property)} properties checked, no KPI thresholds breached.")
        return MonitorRunResult(ran=True, alerted=False, report_text=report_text)

    lines = [f"{property_id}: {'; '.join(items)}" for property_id, items in breaches.items()]
    notify_fn("Autonomous monitoring flagged KPI threshold breaches — " + " | ".join(lines))

    if send_file_fn is not None:
        pdf_bytes = export_pdf_fn("portfolio", report_text)
        try:
            send_file_fn("portfolio-report.pdf", pdf_bytes)
        except Exception as exc:
            notify_fn(f"Autonomous monitoring: file upload failed: {exc}")

    return MonitorRunResult(ran=True, alerted=True, breaches=breaches, report_text=report_text)


def run_monitor_forever(
    run_once_fn: Callable[[], MonitorRunResult],
    interval_seconds: int,
    sleep_fn: Callable[[float], None] = time.sleep,
    max_iterations: int | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    log = log_fn or (lambda message: None)
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        try:
            run_once_fn()
        except Exception as exc:
            # One bad run (transient network error, LLM timeout, ...) must
            # not kill the whole long-running monitor process.
            log(f"Monitoring iteration failed: {exc}")
        iterations += 1
        sleep_fn(interval_seconds)


def build_production_monitor() -> Callable[[], MonitorRunResult]:
    """Wires run_monitor_once to real Drive/Chroma/LLM/Slack — imported by
    the `python -m asset_manager.automation.monitor` entrypoint, not used in
    tests."""
    from asset_manager.agents.report_extraction import extract_final_report
    from asset_manager.automation.production import ProductionDependencies
    from asset_manager.export.render import markdown_to_pdf_bytes
    from asset_manager.monitoring.kpis import KPICollector, load_thresholds_from_env

    deps = ProductionDependencies()
    thresholds = load_thresholds_from_env()

    def run_portfolio_review_fn() -> tuple[str, dict[str, PropertyKPIs]]:
        kpi_collector = KPICollector()
        orchestrator = deps.build_orchestrator(kpi_collector)
        question = (
            "Give me a portfolio-level review comparing all properties on financial, "
            "occupancy, and CapEx risk, ranked, and produce this period's cross-property report."
        )
        result = orchestrator.invoke({"messages": [{"role": "user", "content": question}]})
        return extract_final_report(result["messages"]), kpi_collector.all()

    def run_once() -> MonitorRunResult:
        return run_monitor_once(
            run_portfolio_review_fn=run_portfolio_review_fn,
            thresholds=thresholds,
            export_pdf_fn=markdown_to_pdf_bytes,
            notify_fn=deps.notifier.send,
            send_file_fn=deps.send_file_fn,
            log_fn=print,
        )

    return run_once


if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()
    interval_hours = float(os.environ.get("MONITOR_INTERVAL_HOURS", "24"))
    run_once_fn = build_production_monitor()
    run_monitor_forever(run_once_fn, interval_seconds=int(interval_hours * 3600), log_fn=print)

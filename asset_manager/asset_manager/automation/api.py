"""HTTP endpoint n8n's Schedule Trigger -> HTTP Request node calls."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from asset_manager.automation.scheduled_review import run_portfolio_review, run_scheduled_review


class RunReviewsRequest(BaseModel):
    property_ids: list[str] = []


def create_app(
    all_property_ids,
    run_review_fn,
    export_docx_fn,
    export_pdf_fn,
    notify_fn,
    run_portfolio_review_fn=None,
    run_ingest_fn=None,
    send_file_fn=None,
) -> FastAPI:
    app = FastAPI(title="Asset Manager Automation API")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/reviews/run")
    def run_reviews(request: RunReviewsRequest):
        property_ids = request.property_ids or all_property_ids
        results = run_scheduled_review(
            property_ids=property_ids,
            run_review_fn=run_review_fn,
            export_docx_fn=export_docx_fn,
            export_pdf_fn=export_pdf_fn,
            notify_fn=notify_fn,
            send_file_fn=send_file_fn,
        )
        return {"reviewed": [r.property_id for r in results]}

    @app.post("/reviews/run-portfolio")
    def run_portfolio_review_endpoint():
        # Distinct from POST /reviews/run's N single-property reviews — this
        # produces one cross-property digest (spec Section 2, "Portfolio vs.
        # property-specific queries"), matching the plan's "known gap" note
        # that scheduled jobs previously never invoked portfolio mode.
        if run_portfolio_review_fn is None:
            raise HTTPException(status_code=501, detail="Portfolio review is not configured for this app.")
        result = run_portfolio_review(
            run_portfolio_review_fn=run_portfolio_review_fn,
            export_docx_fn=export_docx_fn,
            export_pdf_fn=export_pdf_fn,
            notify_fn=notify_fn,
            send_file_fn=send_file_fn,
        )
        return {"reviewed": [result.property_id] if result is not None else []}

    @app.post("/ingest/run")
    def run_ingest_endpoint():
        # Lets n8n trigger ingest.py's logic over HTTP (spec Section 6: "n8n
        # ... watches the Drive raw_docs/ folder and triggers ingest.py on
        # new files") instead of only being runnable as a local CLI script.
        # A polling schedule trigger (see n8n/ingest.workflow.json) rather
        # than Drive's native push-notification trigger — simpler and more
        # reliable, and cheap to poll often since ingestion is already
        # idempotent (content-hash skip) and resilient to individual bad
        # files (files_failed/failed_files below, not a crash).
        if run_ingest_fn is None:
            raise HTTPException(status_code=501, detail="Ingestion is not configured for this app.")
        summary = run_ingest_fn()
        return {
            "added": summary.files_added,
            "updated": summary.files_updated,
            "deleted": summary.files_deleted,
            "skipped": summary.files_skipped,
            "failed": summary.files_failed,
            "failed_files": summary.failed_files,
        }

    return app


def build_production_app() -> FastAPI:
    """Wires create_app() to real Drive/Chroma/LLM/Slack — imported by the
    uvicorn entrypoint, not used in tests."""
    from asset_manager.agents.report_extraction import extract_final_report
    from asset_manager.automation.production import ProductionDependencies
    from asset_manager.export.render import markdown_to_docx_bytes, markdown_to_pdf_bytes
    from asset_manager.monitoring.kpis import KPICollector

    deps = ProductionDependencies()

    def run_review_fn(property_id: str) -> str:
        # A fresh KPICollector per call: this endpoint's caller (n8n) doesn't
        # consume the KPI numbers — autonomous alerting on them happens in
        # automation/monitor.py's own runs — but the tools are required
        # inputs to build_orchestrator, so financial/pm/capex-agent can call
        # them without erroring.
        orchestrator = deps.build_orchestrator(KPICollector())
        question = f"Review property {property_id} and produce this period's report."
        result = orchestrator.invoke({"messages": [{"role": "user", "content": question}]})
        return extract_final_report(result["messages"])

    def run_portfolio_review_fn() -> str:
        # A distinct scheduled call using the orchestrator's portfolio-mode
        # prompt path (spec Section 2) — not just N single-property reviews.
        orchestrator = deps.build_orchestrator(KPICollector())
        question = (
            "Give me a portfolio-level review comparing all properties on financial, "
            "occupancy, and CapEx risk, ranked, and produce this period's cross-property report."
        )
        result = orchestrator.invoke({"messages": [{"role": "user", "content": question}]})
        return extract_final_report(result["messages"])

    return create_app(
        all_property_ids=deps.all_property_ids,
        run_review_fn=run_review_fn,
        export_docx_fn=markdown_to_docx_bytes,
        export_pdf_fn=markdown_to_pdf_bytes,
        notify_fn=deps.notifier.send,
        run_portfolio_review_fn=run_portfolio_review_fn,
        run_ingest_fn=deps.run_ingest,
        send_file_fn=deps.send_file_fn,
    )

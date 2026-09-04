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
        )
        return {"reviewed": [result.property_id] if result is not None else []}

    return app


def build_production_app() -> FastAPI:
    """Wires create_app() to real Drive/Chroma/LLM/Slack — imported by the
    uvicorn entrypoint, not used in tests."""
    import os

    import chromadb
    from dotenv import load_dotenv
    from langchain_openai import ChatOpenAI
    from openai import OpenAI

    from asset_manager.agents.orchestrator import build_orchestrator
    from asset_manager.agents.orchestrator_tools import (
        make_get_prior_report_tool,
        make_list_properties_tool,
        make_save_report_tool,
    )
    from asset_manager.export.render import markdown_to_docx_bytes, markdown_to_pdf_bytes
    from asset_manager.ingestion.drive_client import build_drive_client
    from asset_manager.ingestion.store import ChromaStore
    from asset_manager.notify.slack import SlackWebhookNotifier
    from asset_manager.reports.archive import ReportArchive
    from asset_manager.retrieval.tools import make_retrieval_tool

    load_dotenv()

    def embed_fn(texts: list[str]) -> list[list[float]]:
        client = OpenAI()
        response = client.embeddings.create(model="text-embedding-3-small", input=texts)
        return [d.embedding for d in response.data]

    drive = build_drive_client(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    store = ChromaStore(chromadb.PersistentClient(path="knowledge_base/chroma_db"), embed_fn=embed_fn)
    archive = ReportArchive(drive, reports_root_folder_id=os.environ["REPORTS_ROOT_FOLDER_ID"])
    notifier = SlackWebhookNotifier(os.environ["SLACK_WEBHOOK_URL"])

    all_property_ids = [
        k.removeprefix("PROPERTY_FOLDER_").lower() for k in os.environ if k.startswith("PROPERTY_FOLDER_")
    ]

    def _build_orchestrator():
        model = ChatOpenAI(
            model=os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )
        return build_orchestrator(
            model,
            make_retrieval_tool(store, "financial"),
            make_retrieval_tool(store, "pm"),
            make_retrieval_tool(store, "capex"),
            make_get_prior_report_tool(archive),
            make_list_properties_tool(all_property_ids),
            make_save_report_tool(archive),
        )

    def run_review_fn(property_id: str) -> str:
        orchestrator = _build_orchestrator()
        question = f"Review property {property_id} and produce this period's report."
        result = orchestrator.invoke({"messages": [{"role": "user", "content": question}]})
        return result["messages"][-1].content

    def run_portfolio_review_fn() -> str:
        # A distinct scheduled call using the orchestrator's portfolio-mode
        # prompt path (spec Section 2) — not just N single-property reviews.
        orchestrator = _build_orchestrator()
        question = (
            "Give me a portfolio-level review comparing all properties on financial, "
            "occupancy, and CapEx risk, ranked, and produce this period's cross-property report."
        )
        result = orchestrator.invoke({"messages": [{"role": "user", "content": question}]})
        return result["messages"][-1].content

    return create_app(
        all_property_ids=all_property_ids,
        run_review_fn=run_review_fn,
        export_docx_fn=markdown_to_docx_bytes,
        export_pdf_fn=markdown_to_pdf_bytes,
        notify_fn=notifier.send,
        run_portfolio_review_fn=run_portfolio_review_fn,
    )

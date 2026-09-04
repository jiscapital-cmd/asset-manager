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
    from asset_manager.ingestion.ingest import run_ingestion
    from asset_manager.ingestion.store import ChromaStore
    from asset_manager.notify.slack import SlackWebhookNotifier
    from asset_manager.notify.slack_files import SlackFileUploader
    from asset_manager.reports.archive import ReportArchive
    from asset_manager.reports.local_store import LocalFileStore
    from asset_manager.retrieval.tools import make_retrieval_tool

    load_dotenv()

    def embed_fn(texts: list[str]) -> list[list[float]]:
        client = OpenAI()
        response = client.embeddings.create(model="text-embedding-3-small", input=texts)
        return [d.embedding for d in response.data]

    drive = build_drive_client(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    store = ChromaStore(chromadb.PersistentClient(path="knowledge_base/chroma_db"), embed_fn=embed_fn)
    # Local disk, not Drive: a service account has no storage quota of its own
    # on a personal (non-Workspace) Google Drive, so it can't create new report
    # files there even with Editor access on the folder (see
    # ingestion/drive_client.py). REPORTS_ROOT_FOLDER_ID stays unused unless
    # that changes (e.g. a Workspace Shared Drive becomes available).
    reports_root = os.environ.get("REPORTS_LOCAL_DIR", "knowledge_base/reports")
    archive = ReportArchive(LocalFileStore(reports_root), reports_root_folder_id=reports_root)
    notifier = SlackWebhookNotifier(os.environ["SLACK_WEBHOOK_URL"])
    # File uploads need Slack's Web API (a bot token + channel id), not the
    # Incoming Webhook URL above — webhooks can only post text. Optional:
    # only wired up if both are configured, so this app still runs fine
    # (text notifications only) without them.
    slack_bot_token = os.environ.get("SLACK_BOT_TOKEN")
    slack_channel_id = os.environ.get("SLACK_CHANNEL_ID")
    send_file_fn = None
    if slack_bot_token and slack_channel_id:
        file_uploader = SlackFileUploader(bot_token=slack_bot_token, channel_id=slack_channel_id)

        def send_file_fn(filename: str, content: bytes) -> None:
            file_uploader.upload(filename, content, initial_comment=f"Scheduled report: {filename}")

    all_property_ids = [
        k.removeprefix("PROPERTY_FOLDER_").lower() for k in os.environ if k.startswith("PROPERTY_FOLDER_")
    ]
    property_folders = {
        k.removeprefix("PROPERTY_FOLDER_").lower(): v for k, v in os.environ.items() if k.startswith("PROPERTY_FOLDER_")
    }

    def run_ingest_fn():
        return run_ingestion(drive, store, property_folders)

    def _build_orchestrator():
        model = ChatOpenAI(
            model=os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )
        return build_orchestrator(
            model,
            make_retrieval_tool(store, "financial", known_property_ids=all_property_ids),
            make_retrieval_tool(store, "pm", known_property_ids=all_property_ids),
            make_retrieval_tool(store, "capex", known_property_ids=all_property_ids),
            make_get_prior_report_tool(archive, known_property_ids=all_property_ids),
            make_list_properties_tool(all_property_ids),
            make_save_report_tool(archive, known_property_ids=all_property_ids),
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
        run_ingest_fn=run_ingest_fn,
        send_file_fn=send_file_fn,
    )

"""HTTP endpoint n8n's Schedule Trigger -> HTTP Request node calls."""

from fastapi import FastAPI
from pydantic import BaseModel

from asset_manager.automation.scheduled_review import run_scheduled_review


class RunReviewsRequest(BaseModel):
    property_ids: list[str] = []


def create_app(all_property_ids, run_review_fn, export_docx_fn, export_pdf_fn, notify_fn) -> FastAPI:
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

    def run_review_fn(property_id: str) -> str:
        model = ChatOpenAI(model=os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"), base_url="https://openrouter.ai/api/v1")
        orchestrator = build_orchestrator(
            model,
            make_retrieval_tool(store, "financial"),
            make_retrieval_tool(store, "pm"),
            make_retrieval_tool(store, "capex"),
            make_get_prior_report_tool(archive),
            make_list_properties_tool(all_property_ids),
            make_save_report_tool(archive),
        )
        question = f"Review property {property_id} and produce this period's report."
        result = orchestrator.invoke({"messages": [{"role": "user", "content": question}]})
        return result["messages"][-1].content

    return create_app(
        all_property_ids=all_property_ids,
        run_review_fn=run_review_fn,
        export_docx_fn=markdown_to_docx_bytes,
        export_pdf_fn=markdown_to_pdf_bytes,
        notify_fn=notifier.send,
    )

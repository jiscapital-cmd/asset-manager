"""Shared production wiring (real Drive/Chroma/LLM/Slack) for both
automation/api.py (n8n-triggered HTTP endpoints) and automation/monitor.py
(the self-scheduling autonomous monitor) — both need the same orchestrator
construction, just from different entrypoints. Not used in tests, same as
the code it replaces in api.py's former build_production_app()."""

import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from openai import OpenAI

from asset_manager.agents.kpi_tools import (
    make_record_capex_kpis_tool,
    make_record_financial_kpis_tool,
    make_record_pm_kpis_tool,
)
from asset_manager.agents.orchestrator import build_orchestrator
from asset_manager.agents.orchestrator_tools import (
    make_get_prior_report_tool,
    make_list_properties_tool,
    make_save_report_tool,
)
from asset_manager.ingestion.chroma_client import get_chroma_client
from asset_manager.ingestion.drive_client import build_drive_client
from asset_manager.ingestion.ingest import run_ingestion
from asset_manager.ingestion.store import ChromaStore
from asset_manager.monitoring.kpis import KPICollector
from asset_manager.notify.slack import SlackWebhookNotifier
from asset_manager.notify.slack_files import SlackFileUploader
from asset_manager.reports.archive import ReportArchive
from asset_manager.reports.local_store import LocalFileStore
from asset_manager.retrieval.tools import make_retrieval_tool


class ProductionDependencies:
    def __init__(self):
        load_dotenv()

        def embed_fn(texts: list[str]) -> list[list[float]]:
            client = OpenAI()
            response = client.embeddings.create(model="text-embedding-3-small", input=texts)
            return [d.embedding for d in response.data]

        self.drive = build_drive_client(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        self.store = ChromaStore(get_chroma_client(), embed_fn=embed_fn)
        # Local disk, not Drive: a service account has no storage quota of its
        # own on a personal (non-Workspace) Google Drive, so it can't create
        # new report files there even with Editor access on the folder (see
        # ingestion/drive_client.py). REPORTS_ROOT_FOLDER_ID stays unused
        # unless that changes (e.g. a Workspace Shared Drive becomes available).
        reports_root = os.environ.get("REPORTS_LOCAL_DIR", "knowledge_base/reports")
        self.archive = ReportArchive(LocalFileStore(reports_root), reports_root_folder_id=reports_root)
        self.notifier = SlackWebhookNotifier(os.environ["SLACK_WEBHOOK_URL"])
        # File uploads need Slack's Web API (a bot token + channel id), not the
        # Incoming Webhook URL above — webhooks can only post text. Optional:
        # only wired up if both are configured.
        slack_bot_token = os.environ.get("SLACK_BOT_TOKEN")
        slack_channel_id = os.environ.get("SLACK_CHANNEL_ID")
        self.send_file_fn = None
        if slack_bot_token and slack_channel_id:
            file_uploader = SlackFileUploader(bot_token=slack_bot_token, channel_id=slack_channel_id)

            def send_file_fn(filename: str, content: bytes) -> None:
                file_uploader.upload(filename, content, initial_comment=f"Scheduled report: {filename}")

            self.send_file_fn = send_file_fn

        self.all_property_ids = [
            k.removeprefix("PROPERTY_FOLDER_").lower() for k in os.environ if k.startswith("PROPERTY_FOLDER_")
        ]
        self.property_folders = {
            k.removeprefix("PROPERTY_FOLDER_").lower(): v
            for k, v in os.environ.items()
            if k.startswith("PROPERTY_FOLDER_")
        }

    def run_ingest(self):
        return run_ingestion(self.drive, self.store, self.property_folders)

    def build_orchestrator(self, kpi_collector: KPICollector):
        model = ChatOpenAI(
            model=os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
            base_url="https://openrouter.ai/api/v1",
            api_key=os.environ["OPENROUTER_API_KEY"],
        )
        return build_orchestrator(
            model,
            make_retrieval_tool(self.store, "financial", known_property_ids=self.all_property_ids),
            make_retrieval_tool(self.store, "pm", known_property_ids=self.all_property_ids),
            make_retrieval_tool(self.store, "capex", known_property_ids=self.all_property_ids),
            make_get_prior_report_tool(self.archive, known_property_ids=self.all_property_ids),
            make_list_properties_tool(self.all_property_ids),
            make_save_report_tool(self.archive, known_property_ids=self.all_property_ids),
            make_record_financial_kpis_tool(kpi_collector, known_property_ids=self.all_property_ids),
            make_record_pm_kpis_tool(kpi_collector, known_property_ids=self.all_property_ids),
            make_record_capex_kpis_tool(kpi_collector, known_property_ids=self.all_property_ids),
        )

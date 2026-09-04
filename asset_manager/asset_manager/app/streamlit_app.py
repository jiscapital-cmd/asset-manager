"""Streamlit chat UI for the Asset Manager orchestrator."""

import os

import chromadb
import streamlit as st
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from openai import OpenAI

from asset_manager.agents.orchestrator import build_orchestrator
from asset_manager.agents.orchestrator_tools import (
    make_get_prior_report_tool,
    make_list_properties_tool,
    make_save_report_tool,
)
from asset_manager.app.model_config import AGENT_NAMES, AVAILABLE_MODELS, resolve_model_overrides
from asset_manager.ingestion.store import ChromaStore
from asset_manager.reports.archive import ReportArchive
from asset_manager.retrieval.tools import make_retrieval_tool

load_dotenv()

st.set_page_config(page_title="Asset Manager", page_icon="🏢")
st.title("Asset Manager")

with st.sidebar:
    default_model = st.selectbox("Default model", AVAILABLE_MODELS, index=0)
    with st.expander("Advanced: per-agent model overrides"):
        overrides = {}
        for agent_name in AGENT_NAMES:
            choice = st.selectbox(agent_name, ["(use default)"] + AVAILABLE_MODELS, key=agent_name)
            if choice != "(use default)":
                overrides[agent_name] = choice


@st.cache_resource
def get_store() -> ChromaStore:
    def embed_fn(texts: list[str]) -> list[list[float]]:
        client = OpenAI()
        response = client.embeddings.create(model="text-embedding-3-small", input=texts)
        return [d.embedding for d in response.data]

    client = chromadb.PersistentClient(path="knowledge_base/chroma_db")
    return ChromaStore(client, embed_fn=embed_fn)


def _load_property_ids_from_env() -> list[str]:
    return [k.removeprefix("PROPERTY_FOLDER_").lower() for k in os.environ if k.startswith("PROPERTY_FOLDER_")]


@st.cache_resource
def get_archive() -> ReportArchive:
    # Local disk, not Drive: a service account has no storage quota of its
    # own on a personal (non-Workspace) Google Drive, so it can't create new
    # report files there even with Editor access on the folder (see
    # ingestion/drive_client.py). REPORTS_ROOT_FOLDER_ID stays unused unless
    # that changes (e.g. a Workspace Shared Drive becomes available).
    from asset_manager.reports.local_store import LocalFileStore

    reports_root = os.environ.get("REPORTS_LOCAL_DIR", "knowledge_base/reports")
    return ReportArchive(LocalFileStore(reports_root), reports_root_folder_id=reports_root)


def get_orchestrator(model_name: str):
    store = get_store()
    archive = get_archive()
    property_ids = _load_property_ids_from_env()

    model = ChatOpenAI(
        model=model_name,
        base_url="https://openrouter.ai/api/v1",
        api_key=os.environ["OPENROUTER_API_KEY"],
    )
    financial_tool = make_retrieval_tool(store, "financial", known_property_ids=property_ids)
    pm_tool = make_retrieval_tool(store, "pm", known_property_ids=property_ids)
    capex_tool = make_retrieval_tool(store, "capex", known_property_ids=property_ids)
    prior_report_tool = make_get_prior_report_tool(archive, known_property_ids=property_ids)
    list_properties_tool = make_list_properties_tool(property_ids)
    save_report_tool = make_save_report_tool(archive, known_property_ids=property_ids)

    return build_orchestrator(
        model,
        financial_tool,
        pm_tool,
        capex_tool,
        prior_report_tool,
        list_properties_tool,
        save_report_tool,
    )


if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if question := st.chat_input("Ask about a property..."):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        model_map = resolve_model_overrides(default_model, overrides)
        orchestrator = get_orchestrator(model_map["financial-agent"])
        result = orchestrator.invoke({"messages": [{"role": "user", "content": question}]})
        answer = result["messages"][-1].content
        st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})

        from asset_manager.export.render import markdown_to_docx_bytes, markdown_to_pdf_bytes

        docx_bytes = markdown_to_docx_bytes("Asset Manager Report", answer)
        pdf_bytes = markdown_to_pdf_bytes("Asset Manager Report", answer)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button("Download as Word", docx_bytes, file_name="report.docx")
        with col2:
            st.download_button("Download as PDF", pdf_bytes, file_name="report.pdf")

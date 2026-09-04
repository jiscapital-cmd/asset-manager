"""Streamlit chat UI for the Asset Manager orchestrator."""

import os

import chromadb
import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from openai import OpenAI

from asset_manager.agents.orchestrator import build_orchestrator
from asset_manager.agents.orchestrator_tools import (
    make_get_prior_report_tool,
    make_list_properties_tool,
    make_save_report_tool,
)
from asset_manager.app.model_config import AGENT_NAMES, AVAILABLE_MODELS, resolve_model_overrides
from asset_manager.ingestion.ingest import SOURCE_TYPES
from asset_manager.ingestion.store import ChromaStore
from asset_manager.reports.archive import ReportArchive
from asset_manager.retrieval.tools import make_retrieval_tool

load_dotenv()

st.set_page_config(page_title="Asset Manager", page_icon="🏢", layout="wide")
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


# --- Live "agent steps" panel -----------------------------------------------
# Uses orchestrator.stream(stream_mode="updates", subgraphs=True): the
# orchestrator delegates to subagents via deepagents' shared "task" tool
# (args: subagent_type, description), which invokes the subagent's own
# compiled graph synchronously inside the tool call. With subgraphs=True,
# that nested graph's own steps stream too, each tagged with a namespace
# tuple like ("tools:<task_id>",) — this is what actually surfaces each
# subagent's own retrieve_*_documents calls (full query/property_id args
# and full result content), not just the top-level delegation.
#
# The "task" tool call itself doesn't expose which subagent a given nested
# namespace belongs to (the id in the namespace is an internal LangGraph
# task id, not the tool_call id) — so each nested "lane" starts unlabeled
# and gets resolved to a friendly name from the first subagent-specific
# tool it calls, since each subagent's tool wiring is unique (only
# financial-agent calls retrieve_financial_documents, only risk-agent calls
# get_prior_report, etc. — see agents/subagents.py).

_TOOL_ICONS = {
    "retrieve_financial_documents": "💰",
    "retrieve_pm_documents": "🏢",
    "retrieve_capex_documents": "🔧",
    "get_prior_report": "📜",
    "list_properties": "📋",
    "save_report": "💾",
}

_SUBAGENT_SIGNAL_TOOLS = {
    "retrieve_financial_documents": "financial-agent",
    "retrieve_pm_documents": "pm-agent",
    "retrieve_capex_documents": "capex-agent",
    "get_prior_report": "risk-agent",
}


def _describe_tool_call(name: str, args: dict) -> str:
    if name == "task":
        subagent = args.get("subagent_type", "?")
        description = args.get("description") or ""
        preview = description[:140] + ("…" if len(description) > 140 else "")
        return f"🚀 Delegating to **{subagent}** — _{preview}_"
    if name in _TOOL_ICONS:
        icon = _TOOL_ICONS[name]
        if name.startswith("retrieve_"):
            return f"{icon} Retrieving documents for **{args.get('property_id', '?')}**: _{args.get('query', '')}_"
        if name == "get_prior_report":
            return f"{icon} Fetching prior report for **{args.get('property_id', '?')}**"
        if name == "list_properties":
            return f"{icon} Listing available properties"
        if name == "save_report":
            return f"{icon} Saving report for **{args.get('property_id', '?')}**"
    return f"🔧 Calling `{name}`"


class _StepRenderer:
    """Renders orchestrator.stream(stream_mode="updates", subgraphs=True)
    output into the steps panel: one titled sub-area ("lane") per nested
    subagent invocation, resolved to a friendly name once we see a
    tool call that identifies it (see _SUBAGENT_SIGNAL_TOOLS)."""

    def __init__(self, top_level_container):
        self._top_level_container = top_level_container
        self._lanes: dict[tuple, dict] = {}
        self._call_labels: dict[str, str] = {}
        self.final_answer: str | None = None

    def _lane_for(self, namespace: tuple) -> dict:
        if namespace not in self._lanes:
            if namespace == ():
                lane = {"title_ph": None, "body": self._top_level_container, "resolved": "Orchestrator"}
            else:
                title_ph = self._top_level_container.empty()
                title_ph.markdown("**🧩 Subagent call — starting…**")
                body = self._top_level_container.container()
                lane = {"title_ph": title_ph, "body": body, "resolved": None}
            self._lanes[namespace] = lane
        return self._lanes[namespace]

    def _resolve_lane(self, lane: dict, tool_name: str) -> None:
        if lane["resolved"] is None and tool_name in _SUBAGENT_SIGNAL_TOOLS:
            lane["resolved"] = _SUBAGENT_SIGNAL_TOOLS[tool_name]
            if lane["title_ph"] is not None:
                lane["title_ph"].markdown(f"**🧩 Subagent: {lane['resolved']}**")

    @staticmethod
    def _as_text(content) -> str:
        return content if isinstance(content, str) else str(content)

    def render_update(self, namespace: tuple, chunk: dict) -> None:
        for node_output in chunk.values():
            if not isinstance(node_output, dict) or "messages" not in node_output:
                continue  # e.g. deepagents' internal middleware nodes carry no messages
            lane = self._lane_for(namespace)
            container = lane["body"]
            for message in node_output["messages"]:
                if isinstance(message, AIMessage) and message.tool_calls:
                    for tool_call in message.tool_calls:
                        self._resolve_lane(lane, tool_call["name"])
                        label = _describe_tool_call(tool_call["name"], tool_call.get("args", {}))
                        self._call_labels[tool_call["id"]] = label
                        container.markdown(label)
                        with container.expander("🧾 input", expanded=False):
                            st.json(tool_call.get("args", {}))
                elif isinstance(message, ToolMessage):
                    label = self._call_labels.get(message.tool_call_id, f"🔧 `{message.name}`")
                    content = self._as_text(message.content)
                    preview = content[:2000] + ("…" if len(content) > 2000 else "")
                    with container.expander(f"✅ {label} — output", expanded=False):
                        st.text(preview)
                elif isinstance(message, AIMessage) and message.content:
                    content = self._as_text(message.content)
                    if namespace == ():
                        self.final_answer = content
                    preview = content[:300] + ("…" if len(content) > 300 else "")
                    container.caption(f"💬 {preview}")


if "messages" not in st.session_state:
    st.session_state.messages = []

chat_tab, kb_tab = st.tabs(["💬 Chat", "📚 Knowledge Base"])

with chat_tab:
    chat_col, steps_col = st.columns([2, 1])

    with chat_col:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    with steps_col:
        st.markdown("### 🔍 Agent steps")
        steps_placeholder = st.empty()
        with steps_placeholder.container():
            st.caption("Steps for the next question will appear here as they happen.")

    if question := st.chat_input("Ask about a property..."):
        st.session_state.messages.append({"role": "user", "content": question})
        with chat_col:
            with st.chat_message("user"):
                st.markdown(question)

            with st.chat_message("assistant"):
                answer_placeholder = st.empty()
                answer_placeholder.markdown("_Thinking..._")

        with steps_col:
            steps_placeholder.empty()
            steps_container = steps_placeholder.container()

        model_map = resolve_model_overrides(default_model, overrides)
        orchestrator = get_orchestrator(model_map["financial-agent"])

        renderer = _StepRenderer(steps_container)
        for namespace, chunk in orchestrator.stream(
            {"messages": [{"role": "user", "content": question}]},
            stream_mode="updates",
            subgraphs=True,
        ):
            renderer.render_update(namespace, chunk)

        answer = renderer.final_answer or "(no response)"
        answer_placeholder.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})

        with chat_col:
            from asset_manager.export.render import markdown_to_docx_bytes, markdown_to_pdf_bytes

            docx_bytes = markdown_to_docx_bytes("Asset Manager Report", answer)
            pdf_bytes = markdown_to_pdf_bytes("Asset Manager Report", answer)

            col1, col2 = st.columns(2)
            with col1:
                st.download_button("Download as Word", docx_bytes, file_name="report.docx")
            with col2:
                st.download_button("Download as PDF", pdf_bytes, file_name="report.pdf")

with kb_tab:
    st.markdown(
        "Inspect exactly what `ingest.py` chunked, embedded, and stored in Chroma "
        "— independent of any chat question, and a live similarity-search tester."
    )

    kb_property_ids = _load_property_ids_from_env()
    if not kb_property_ids:
        st.warning("No PROPERTY_FOLDER_* variables found in .env — nothing to browse yet.")
    else:
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            kb_property_id = st.selectbox("Property", kb_property_ids, key="kb_property_id")
        with filter_col2:
            kb_source_type = st.selectbox("Source type", ["(all)"] + SOURCE_TYPES, key="kb_source_type")

        store = get_store()
        chunks = store.list_chunks(
            kb_property_id,
            source_type=None if kb_source_type == "(all)" else kb_source_type,
        )

        unique_files = sorted({c["filename"] for c in chunks})
        metric_col1, metric_col2 = st.columns(2)
        metric_col1.metric("Chunks", len(chunks))
        metric_col2.metric("Files", len(unique_files))

        st.markdown("#### Chunks")
        if not chunks:
            st.caption("No chunks ingested yet for this property/source type. Run `python -m asset_manager.ingestion.ingest`.")
        else:
            for chunk in chunks:
                header = f"{chunk['filename']} — p.{chunk['page_or_row']} — {chunk['source_type']}"
                with st.expander(header):
                    st.caption(f"ingested_at: {chunk['ingested_at']}  •  file_hash: {chunk['file_hash'][:12]}…")
                    st.text(chunk["text"])

        st.divider()
        st.markdown("#### Test retrieval")
        st.caption(
            "Runs the exact same embedding + Chroma similarity search a subagent's "
            "retrieval tool would run — see what actually comes back for a query."
        )
        test_query = st.text_input("Query", key="kb_test_query", placeholder="e.g. NOI budget variance")
        test_source_type = st.selectbox("Search within source type", SOURCE_TYPES, key="kb_test_source_type")
        if st.button("Run search", key="kb_test_run") and test_query:
            with st.spinner("Embedding query and searching Chroma…"):
                results = store.query(test_query, source_type=test_source_type, property_id=kb_property_id)
            if not results:
                st.caption("No results.")
            else:
                for r in results:
                    with st.expander(f"[{r['filename']}, p.{r['page_or_row']}]"):
                        st.text(r["text"])

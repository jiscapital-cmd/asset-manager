"""Streamlit chat UI for the Asset Manager orchestrator."""

import sys
from pathlib import Path

# Streamlit Cloud runs this script directly and only installs whatever's in
# requirements.txt (third-party packages) — it never runs `pip install -e .`
# the way local development does, so the asset_manager package itself isn't
# importable by default. This repo's layout is asset-manager/asset_manager/
# asset_manager/app/streamlit_app.py — the project root two directories up
# (containing the asset_manager/ package folder) needs to be on sys.path
# before any `from asset_manager....` import, regardless of the working
# directory Streamlit Cloud invokes this script from.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import html
import os
import re
import uuid

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
from asset_manager.ingestion.chroma_client import get_chroma_client
from asset_manager.ingestion.ingest import SOURCE_TYPES
from asset_manager.ingestion.store import ChromaStore
from asset_manager.reports.archive import ReportArchive
from asset_manager.retrieval.tools import make_retrieval_tool

load_dotenv()

st.set_page_config(
    page_title="PrimeAsset Realty Management", page_icon=":material/apartment:", layout="wide"
)

# --- Session state -----------------------------------------------------------

if "chats" not in st.session_state:
    st.session_state.chats = {}
if "current_chat_id" not in st.session_state or st.session_state.current_chat_id not in st.session_state.chats:
    _first_id = str(uuid.uuid4())
    st.session_state.chats[_first_id] = {"title": "New chat", "messages": []}
    st.session_state.current_chat_id = _first_id
if "view" not in st.session_state:
    st.session_state.view = "chat"  # "chat" | "knowledge_base"
if "sidebar_expanded" not in st.session_state:
    st.session_state.sidebar_expanded = True

expanded = st.session_state.sidebar_expanded
sidebar_width_px = 280 if expanded else 76
sidebar_justify = "flex-start"

# --- Global CSS ---------------------------------------------------------------

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    [data-testid="stAppViewContainer"] {{
        background:
            radial-gradient(480px circle at 8% -6%, rgba(153, 246, 228, 0.35), transparent 60%),
            radial-gradient(420px circle at 96% 4%, rgba(204, 251, 241, 0.45), transparent 55%);
        background-repeat: no-repeat;
    }}

    /* --- Collapsible icon-rail sidebar ------------------------------------ */
    [data-testid="stSidebar"] {{
        width: {sidebar_width_px}px !important;
        min-width: {sidebar_width_px}px !important;
        max-width: {sidebar_width_px}px !important;
        transition: width 0.15s ease;
    }}
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="collapsedControl"],
    [data-testid="stSidebarResizer"],
    [data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"] {{
        display: none !important;
    }}
    [data-testid="stSidebar"] .stButton > button {{
        justify-content: {sidebar_justify};
        gap: 10px;
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
        color: #334155;
        font-weight: 500;
        padding: 8px 10px !important;
        border-radius: 10px !important;
        text-align: left;
    }}
    [data-testid="stSidebar"] .stButton > button:hover {{
        background: rgba(15, 118, 110, 0.08) !important;
        color: #0f766e;
    }}
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {{
        background: #ccfbf1 !important;
        color: #0f766e !important;
    }}
    .pam-sidebar-brand {{
        display: flex;
        align-items: center;
        justify-content: {sidebar_justify};
        gap: 10px;
        padding: 4px 10px 14px 10px;
    }}
    .pam-sidebar-tile {{
        width: 28px;
        height: 28px;
        border-radius: 8px;
        background: #0f766e;
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
    }}
    .pam-sidebar-tile svg {{ width: 15px; height: 15px; }}
    .pam-sidebar-brand span {{
        font-family: 'Inter', sans-serif;
        font-weight: 800;
        font-size: 14.5px;
        color: #0f172a;
        white-space: nowrap;
    }}
    .pam-sidebar-label {{
        font-size: 11.5px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #94a3b8;
        padding: 14px 10px 4px 10px;
    }}
    .pam-sidebar-footer {{
        font-size: 12px;
        color: #94a3b8;
        padding: 10px;
        border-top: 1px solid rgba(15, 23, 42, 0.06);
        margin-top: 8px;
    }}

    /* --- Homescreen greeting ------------------------------------------------ */
    .pam-greeting {{
        text-align: center;
        margin: 9vh auto 28px auto;
        max-width: 640px;
    }}
    .pam-greeting h1 {{
        font-family: 'Inter', sans-serif;
        font-weight: 700;
        font-size: 30px;
        color: #0f172a;
        margin: 0 0 6px 0;
    }}
    .pam-greeting p {{
        font-size: 14.5px;
        color: #64748b;
        margin: 0;
    }}

    /* Suggestion chips + other main-area buttons stay pill/teal styled */
    [data-testid="stMain"] .stButton > button {{
        border-radius: 999px;
        border: 1px solid rgba(15, 23, 42, 0.1);
        color: #334155;
        font-weight: 500;
    }}
    [data-testid="stMain"] .stButton > button:hover {{
        border-color: #5eead4;
        color: #0f766e;
    }}

    /* Accordion-style expander / status cards */
    details[data-testid="stExpander"] {{
        border-radius: 14px !important;
        border: 1px solid rgba(15, 23, 42, 0.1) !important;
        background: #ffffff;
        transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }}
    details[data-testid="stExpander"]:hover {{
        border-color: #99f6e4 !important;
    }}
    details[data-testid="stExpander"][open] {{
        border-color: #99f6e4 !important;
        box-shadow: 0 10px 28px rgba(15, 118, 110, 0.12);
    }}
    [data-testid="stStatusWidget"] {{
        border-radius: 14px !important;
        border: 1px solid rgba(15, 23, 42, 0.1) !important;
    }}

    /* Dashboard report tiles (st.container(border=True)) */
    [data-testid="stVerticalBlockBorderWrapper"] {{
        border-radius: 14px !important;
        border-color: rgba(15, 23, 42, 0.1) !important;
    }}

    /* Chat input as a rounded search-like field with teal focus ring */
    [data-testid="stChatInput"] {{
        border-radius: 16px !important;
        box-shadow: 0 6px 20px rgba(15, 118, 110, 0.08);
    }}
    [data-testid="stChatInput"]:focus-within {{
        border-color: #14b8a6 !important;
        box-shadow: 0 0 0 4px rgba(20, 184, 166, 0.15) !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# --- Shared resources ---------------------------------------------------------


@st.cache_resource
def get_store() -> ChromaStore:
    def embed_fn(texts: list[str]) -> list[list[float]]:
        client = OpenAI()
        response = client.embeddings.create(model="text-embedding-3-small", input=texts)
        return [d.embedding for d in response.data]

    client = get_chroma_client()
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


# --- Agent steps: live rendering + recorded replay ---------------------------
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
#
# Every event is also recorded into a flat list (_StepRenderer.events) so a
# finished turn can be redrawn later — collapsed by default, like a chat
# history entry — without needing the live LangGraph stream to still exist.

_TOOL_ICONS = {
    "retrieve_financial_documents": ":material/payments:",
    "retrieve_pm_documents": ":material/apartment:",
    "retrieve_capex_documents": ":material/construction:",
    "get_prior_report": ":material/history:",
    "list_properties": ":material/list:",
    "save_report": ":material/save:",
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
        return f":material/arrow_forward: Delegating to **{subagent}** — _{preview}_"
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
    return f":material/settings: Calling `{name}`"


class _StepRenderer:
    """Renders orchestrator.stream(stream_mode="updates", subgraphs=True)
    output live into a container (typically an st.status body), one titled
    sub-area ("lane") per nested subagent invocation, resolved to a friendly
    name once we see a tool call that identifies it (see
    _SUBAGENT_SIGNAL_TOOLS). Also records every event into self.events for
    later static replay via _render_steps_static."""

    def __init__(self, top_level_container):
        self._top_level_container = top_level_container
        self._lanes: dict[tuple, dict] = {}
        self._call_labels: dict[str, str] = {}
        self.final_answer: str | None = None
        self.events: list[dict] = []

    def _lane_for(self, namespace: tuple) -> dict:
        if namespace not in self._lanes:
            if namespace == ():
                lane = {"title_ph": None, "body": self._top_level_container, "resolved": "Orchestrator"}
            else:
                title_ph = self._top_level_container.empty()
                title_ph.markdown("**:material/hub: Subagent call — starting…**")
                body = self._top_level_container.container()
                lane = {"title_ph": title_ph, "body": body, "resolved": None}
            self._lanes[namespace] = lane
        return self._lanes[namespace]

    def _resolve_lane(self, lane: dict, tool_name: str) -> None:
        if lane["resolved"] is None and tool_name in _SUBAGENT_SIGNAL_TOOLS:
            lane["resolved"] = _SUBAGENT_SIGNAL_TOOLS[tool_name]
            if lane["title_ph"] is not None:
                lane["title_ph"].markdown(f"**:material/hub: Subagent: {lane['resolved']}**")

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
                        with container.expander("Input", expanded=False, icon=":material/data_object:"):
                            st.json(tool_call.get("args", {}))
                        self.events.append(
                            {
                                "type": "tool_call",
                                "namespace": namespace,
                                "tool_name": tool_call["name"],
                                "label": label,
                                "args": tool_call.get("args", {}),
                            }
                        )
                elif isinstance(message, ToolMessage):
                    label = self._call_labels.get(message.tool_call_id, f":material/settings: `{message.name}`")
                    content = self._as_text(message.content)
                    preview = content[:2000] + ("…" if len(content) > 2000 else "")
                    with container.expander(f"{label} — output", expanded=False):
                        st.text(preview)
                    self.events.append(
                        {"type": "tool_output", "namespace": namespace, "label": label, "content": preview}
                    )
                elif isinstance(message, AIMessage) and message.content:
                    content = self._as_text(message.content)
                    if namespace == ():
                        self.final_answer = content
                    preview = content[:300] + ("…" if len(content) > 300 else "")
                    container.caption(f":material/chat_bubble: {preview}")
                    self.events.append({"type": "chat_text", "namespace": namespace, "content": preview})


def _lane_names_from_events(events: list[dict]) -> dict[tuple, str]:
    names: dict[tuple, str] = {}
    for event in events:
        namespace = event["namespace"]
        if namespace == () or namespace in names:
            continue
        if event["type"] == "tool_call" and event.get("tool_name") in _SUBAGENT_SIGNAL_TOOLS:
            names[namespace] = _SUBAGENT_SIGNAL_TOOLS[event["tool_name"]]
    return names


def _render_steps_static(container, events: list[dict]) -> None:
    """Redraws a finished turn's recorded events (no live LangGraph stream
    needed) — used when reopening a past chat's collapsed 'Agent steps'."""
    lane_names = _lane_names_from_events(events)
    lanes: dict[tuple, object] = {}

    def lane_for(namespace: tuple):
        if namespace not in lanes:
            if namespace == ():
                lanes[namespace] = container
            else:
                name = lane_names.get(namespace, "Subagent")
                container.markdown(f"**:material/hub: Subagent: {name}**")
                lanes[namespace] = container.container()
        return lanes[namespace]

    for event in events:
        body = lane_for(event["namespace"])
        if event["type"] == "tool_call":
            body.markdown(event["label"])
            with body.expander("Input", expanded=False, icon=":material/data_object:"):
                st.json(event["args"])
        elif event["type"] == "tool_output":
            with body.expander(f"{event['label']} — output", expanded=False):
                st.text(event["content"])
        elif event["type"] == "chat_text":
            body.caption(f":material/chat_bubble: {event['content']}")


# --- Executive report dashboard ----------------------------------------------
# The risk-agent's final synthesis follows a fixed structure (see
# agents/prompts.py's FINAL REPORT template): a single "# <title>" line
# followed by "## <section>" headings such as Financial, Property
# Operations, CapEx, Risk Assessment, etc. Narrower answers (e.g. "list all
# properties") don't follow that shape at all — _parse_report returns None
# for those, and the caller falls back to plain markdown.

_REPORT_TILE_ICONS = {
    "financial": ":material/payments:",
    "property operations": ":material/apartment:",
    "capex": ":material/construction:",
}

_REPORT_SECONDARY_ICONS = {
    "changes since prior review": ":material/history:",
    "recommended actions": ":material/checklist:",
    "data gaps": ":material/help:",
}

_RISK_LEVEL_STYLES = {
    "high": ("#fee2e2", "#b91c1c"),
    "elevated": ("#fee2e2", "#b91c1c"),
    "medium": ("#fef3c7", "#92400e"),
    "moderate": ("#fef3c7", "#92400e"),
    "low": ("#ccfbf1", "#0f766e"),
}

_KNOWN_REPORT_SECTIONS = {
    "executive assessment",
    "financial",
    "property operations",
    "capex",
    "risk assessment",
    "changes since prior review",
    "recommended actions",
    "data gaps",
}


def _parse_report(markdown_text: str) -> tuple[str, dict[str, str]] | None:
    """Recognizes the risk-agent's FINAL REPORT structure (see
    agents/prompts.py): a '# Title' line followed by '## Section' headings.
    The model doesn't always put the title on the exact first line (a short
    lead-in sentence sometimes precedes it), so this scans the first few
    lines for it rather than requiring lines[0] — but still requires at
    least 2 recognized section names, so an unrelated answer that happens
    to contain a stray '#'/'##' doesn't get misdetected as a report."""
    lines = markdown_text.splitlines()

    title = None
    title_idx = None
    for i, line in enumerate(lines[:5]):
        if line.startswith("# "):
            title = line[2:].strip()
            title_idx = i
            break
    if title is None:
        return None

    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in lines[title_idx + 1 :]:
        match = re.match(r"^##\s+(.*)", line)
        if match:
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = match.group(1).strip()
            buf = []
        else:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()

    known_hits = sum(1 for key in sections if key.lower() in _KNOWN_REPORT_SECTIONS)
    if known_hits < 2:
        return None
    return title, sections


def _extract_risk_levels(risk_section_text: str) -> list[tuple[str, str]]:
    levels = []
    pattern = re.compile(
        r"^\s*[-*•]?\s*\*{0,2}(Financial Risk|Occupancy & Operations Risk|CapEx Risk)\*{0,2}\s*:\s*(.+)"
    )
    for line in risk_section_text.splitlines():
        match = pattern.match(line)
        if match:
            levels.append((match.group(1).strip(), match.group(2).strip()))
    return levels


def _risk_level_word(value: str) -> str:
    stripped = value.strip().lstrip("*_ ")
    match = re.match(r"^([A-Za-z][A-Za-z\-]*)", stripped)
    return match.group(1) if match else (stripped or "Unknown")


def _risk_badge_html(label: str, value: str) -> str:
    level_word = _risk_level_word(value)
    bg, fg = _RISK_LEVEL_STYLES.get(level_word.lower(), ("#f1f5f9", "#475569"))
    return (
        f'<div style="background:{bg};color:{fg};border-radius:12px;'
        f'padding:14px 16px;flex:1;min-width:160px;">'
        f'<div style="font-size:11.5px;font-weight:600;text-transform:uppercase;'
        f'letter-spacing:.04em;opacity:.75;">{html.escape(label)}</div>'
        f'<div style="font-size:16px;font-weight:700;margin-top:2px;">{html.escape(level_word)}</div>'
        f"</div>"
    )


def _md(text: str) -> str:
    """Escapes literal '$' so dollar figures (very common in these reports)
    don't get misparsed as LaTeX math delimiters by st.markdown/st.info."""
    return text.replace("$", "\\$")


def render_report_or_markdown(content: str) -> None:
    """Renders a matching executive report as a dashboard (title, risk KPI
    row, financial/pm/capex tiles, secondary accordions); anything else
    falls back to plain markdown unchanged."""
    parsed = _parse_report(content)
    if parsed is None:
        st.markdown(_md(content))
        return

    title, sections = parsed
    st.markdown(f"#### :material/apartment: {_md(title)}")

    if "Executive Assessment" in sections:
        st.info(_md(sections["Executive Assessment"]))

    if "Risk Assessment" in sections:
        levels = _extract_risk_levels(sections["Risk Assessment"])
        if levels:
            badges = "".join(_risk_badge_html(label, value) for label, value in levels)
            st.markdown(f'<div style="display:flex;gap:12px;margin:4px 0 12px 0;">{badges}</div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("**:material/warning: Risk Assessment**")
            st.markdown(_md(sections["Risk Assessment"]))

    tile_keys = [k for k in sections if k.lower() in _REPORT_TILE_ICONS]
    if tile_keys:
        tile_cols = st.columns(len(tile_keys))
        for col, key in zip(tile_cols, tile_keys):
            with col:
                with st.container(border=True):
                    st.markdown(f"**{_REPORT_TILE_ICONS[key.lower()]} {_md(key)}**")
                    st.markdown(_md(sections[key]))

    secondary_keys = [k for k in sections if k.lower() in _REPORT_SECONDARY_ICONS]
    for key in secondary_keys:
        icon = _REPORT_SECONDARY_ICONS[key.lower()]
        with st.expander(f"{icon} {key}", expanded=(key.lower() == "recommended actions")):
            st.markdown(_md(sections[key]))

    handled = {"Executive Assessment", "Risk Assessment", *tile_keys, *secondary_keys}
    for key in sections:
        if key not in handled:
            st.markdown(f"**{_md(key)}**")
            st.markdown(_md(sections[key]))


# --- Sidebar: icon rail / expanded nav ---------------------------------------

with st.sidebar:
    st.markdown(
        """
        <div class="pam-sidebar-brand">
            <div class="pam-sidebar-tile">
                <svg viewBox="0 0 256 256" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M128 24L146 106L228 124L146 142L128 224L110 142L28 124L110 106Z" fill="white"/>
                </svg>
            </div>
            {label}
        </div>
        """.format(label="<span>PrimeAsset</span>" if expanded else ""),
        unsafe_allow_html=True,
    )

    if st.button(
        "Close sidebar" if expanded else " ",
        icon=":material/menu_open:" if expanded else ":material/menu:",
        key="sidebar_toggle",
        use_container_width=True,
    ):
        st.session_state.sidebar_expanded = not expanded
        st.rerun()

    if st.button(
        "New chat" if expanded else " ",
        icon=":material/edit_square:",
        key="new_chat_btn",
        use_container_width=True,
    ):
        new_id = str(uuid.uuid4())
        st.session_state.chats[new_id] = {"title": "New chat", "messages": []}
        st.session_state.current_chat_id = new_id
        st.session_state.view = "chat"
        st.rerun()

    if st.button(
        "Knowledge base" if expanded else " ",
        icon=":material/menu_book:",
        key="kb_nav_btn",
        use_container_width=True,
        type="primary" if st.session_state.view == "knowledge_base" else "secondary",
    ):
        st.session_state.view = "knowledge_base"
        st.rerun()

    if expanded:
        st.markdown('<div class="pam-sidebar-label">Chats</div>', unsafe_allow_html=True)
        for chat_id, chat in reversed(list(st.session_state.chats.items())):
            is_active = chat_id == st.session_state.current_chat_id and st.session_state.view == "chat"
            if st.button(
                chat["title"],
                key=f"chat_{chat_id}",
                use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.current_chat_id = chat_id
                st.session_state.view = "chat"
                st.rerun()

        st.divider()
        default_model = st.selectbox("Default model", AVAILABLE_MODELS, index=0)
        with st.expander("Advanced: per-agent model overrides", icon=":material/tune:"):
            overrides = {}
            for agent_name in AGENT_NAMES:
                choice = st.selectbox(agent_name, ["(use default)"] + AVAILABLE_MODELS, key=agent_name)
                if choice != "(use default)":
                    overrides[agent_name] = choice
        st.markdown(
            '<div class="pam-sidebar-footer">PrimeAsset Realty Management</div>', unsafe_allow_html=True
        )
    else:
        # Model choice still needs a value even while the sidebar is collapsed.
        default_model = st.session_state.get("_default_model_cache", AVAILABLE_MODELS[0])
        overrides = st.session_state.get("_overrides_cache", {})

    st.session_state["_default_model_cache"] = default_model
    st.session_state["_overrides_cache"] = overrides


# --- Main area ----------------------------------------------------------------


def render_chat() -> None:
    chat = st.session_state.chats[st.session_state.current_chat_id]

    for message in chat["messages"]:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant" and message.get("steps"):
                with st.status("Agent steps", state="complete", expanded=False) as hist_status:
                    _render_steps_static(hist_status, message["steps"])
            render_report_or_markdown(message["content"])
            if message["role"] == "assistant" and message.get("docx") is not None:
                dl_col1, dl_col2 = st.columns(2)
                with dl_col1:
                    st.download_button(
                        "Download as Word",
                        message["docx"],
                        file_name="report.docx",
                        icon=":material/download:",
                        key=f"docx_{message['id']}",
                    )
                with dl_col2:
                    st.download_button(
                        "Download as PDF",
                        message["pdf"],
                        file_name="report.pdf",
                        icon=":material/download:",
                        key=f"pdf_{message['id']}",
                    )

    question = None

    if not chat["messages"]:
        st.markdown(
            """
            <div class="pam-greeting">
                <h1>How can I help with your Assets?</h1>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Nested inside a container, st.chat_input renders inline instead of
        # docking to the bottom of the page — used only for this empty
        # homescreen state, in the same centered column as the greeting.
        _, mid_col, _ = st.columns([1, 2, 1])
        with mid_col:
            question = st.chat_input("Ask about a property...", key="home_chat_input")
    else:
        question = st.chat_input("Ask about a property...", key="docked_chat_input")

    if question:
        chat["messages"].append({"role": "user", "content": question})
        if chat["title"] == "New chat":
            chat["title"] = question[:40] + ("…" if len(question) > 40 else "")

        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            status = st.status("Working…", expanded=True, state="running")
            answer_placeholder = st.empty()

            model_map = resolve_model_overrides(default_model, overrides)
            orchestrator = get_orchestrator(model_map["financial-agent"])

            renderer = _StepRenderer(status)
            for namespace, chunk in orchestrator.stream(
                {"messages": [{"role": "user", "content": question}]},
                stream_mode="updates",
                subgraphs=True,
            ):
                renderer.render_update(namespace, chunk)

            status.update(label="Agent steps", state="complete", expanded=False)

            answer = renderer.final_answer or "(no response)"
            with answer_placeholder.container():
                render_report_or_markdown(answer)

            from asset_manager.export.render import markdown_to_docx_bytes, markdown_to_pdf_bytes

            docx_bytes = markdown_to_docx_bytes("Asset Manager Report", answer)
            pdf_bytes = markdown_to_pdf_bytes("Asset Manager Report", answer)

            dl_col1, dl_col2 = st.columns(2)
            with dl_col1:
                st.download_button(
                    "Download as Word", docx_bytes, file_name="report.docx", icon=":material/download:", key="docx_live"
                )
            with dl_col2:
                st.download_button(
                    "Download as PDF", pdf_bytes, file_name="report.pdf", icon=":material/download:", key="pdf_live"
                )

        chat["messages"].append(
            {
                "role": "assistant",
                "content": answer,
                "steps": renderer.events,
                "docx": docx_bytes,
                "pdf": pdf_bytes,
                "id": str(uuid.uuid4()),
            }
        )
        st.rerun()


def render_knowledge_base() -> None:
    st.markdown("### :material/menu_book: Knowledge base")
    st.markdown(
        "Inspect exactly what `ingest.py` chunked, embedded, and stored in Chroma "
        "— independent of any chat question, and a live similarity-search tester."
    )

    kb_property_ids = _load_property_ids_from_env()
    if not kb_property_ids:
        st.warning("No PROPERTY_FOLDER_* variables found in .env — nothing to browse yet.")
        return

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

    st.markdown("#### :material/list_alt: Chunks")
    if not chunks:
        st.caption("No chunks ingested yet for this property/source type. Run `python -m asset_manager.ingestion.ingest`.")
    else:
        for chunk in chunks:
            header = f"{chunk['filename']} — p.{chunk['page_or_row']} — {chunk['source_type']}"
            with st.expander(header):
                st.caption(f"ingested_at: {chunk['ingested_at']}  •  file_hash: {chunk['file_hash'][:12]}…")
                st.text(chunk["text"])

    st.markdown("#### :material/manage_search: Test retrieval")
    st.caption(
        "Runs the exact same embedding + Chroma similarity search a subagent's "
        "retrieval tool would run — see what actually comes back for a query."
    )
    test_query = st.text_input("Query", key="kb_test_query", placeholder="e.g. NOI budget variance")
    test_source_type = st.selectbox("Search within source type", SOURCE_TYPES, key="kb_test_source_type")
    if st.button("Run search", key="kb_test_run", icon=":material/search:") and test_query:
        with st.spinner("Embedding query and searching Chroma…"):
            results = store.query(test_query, source_type=test_source_type, property_id=kb_property_id)
        if not results:
            st.caption("No results.")
        else:
            for r in results:
                with st.expander(f"[{r['filename']}, p.{r['page_or_row']}]"):
                    st.text(r["text"])


if st.session_state.view == "knowledge_base":
    render_knowledge_base()
else:
    render_chat()

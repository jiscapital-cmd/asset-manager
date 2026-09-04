# Asset Manager — Portfolio Mode & Report History Implementation Plan (Plan 2 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the orchestrator built in Plan 1 the ability to (a) discover which
properties exist for portfolio-level questions, (b) persist every completed report to
a Drive-backed archive, and (c) let `risk-agent` diff against the most recent prior
report for the same property.

**Architecture:** Three new orchestrator-level tools (`list_properties`,
`save_report`, and a risk-agent-only `get_prior_report`) backed by a `ReportArchive`
class, itself built on an extended `DriveClient` (adds folder-creation and text
file upload/download to the wrapper from Plan 1). No changes to the two-wave
delegation mechanism — portfolio mode and history diffing are additive tool access,
not new graph structure (this matches the spec's framing: "no separate portfolio
graph exists").

**Tech Stack:** Same as Plan 1, no new dependencies.

**Spec:** `specs/2026-09-03-asset-manager-design.md`
**Depends on:** `plans/2026-09-03-asset-manager-core-pipeline.md` (Plan 1) — this plan imports `DriveClient`, `DriveFile` from `asset_manager.ingestion.drive_client` and `build_orchestrator`, `build_subagents` from `asset_manager.agents`.

## Global Constraints

(All of Plan 1's constraints still apply. Additionally:)

- Report archive path in Drive: `JIS Capital - Knowledge Base/reports/<property-id>/<YYYY-MM-DD>.md` (spec Section 4)
- `reports/` is never walked by `ingest.py` and never embedded into Chroma (spec Section 4)
- The orchestrator decides portfolio vs. single-property mode from the question's wording — there is no separate query syntax or graph path (spec Section 2)
- `risk-agent` gets `get_prior_report` as an additional tool in this plan; it still has no retrieval (RAG) tool of its own

---

## File Structure

```
asset_manager/
├── ingestion/
│   └── drive_client.py       # MODIFY — add find_or_create_subfolder, upload_text_file, download_text_file
├── reports/
│   ├── __init__.py
│   └── archive.py            # ReportArchive — save_report(), get_latest_report()
└── agents/
    ├── prompts.py             # MODIFY — orchestrator/risk-agent prompts reference the new tools
    ├── subagents.py           # MODIFY — build_subagents() takes an extra get_prior_report_tool
    └── orchestrator.py        # MODIFY — build_orchestrator() takes archive + property_ids, wires new tools

tests/
├── ingestion/
│   └── test_drive_client.py  # MODIFY — add tests for the 3 new methods
├── reports/
│   └── test_archive.py
└── agents/
    ├── test_subagents.py     # MODIFY — assert risk-agent now has 1 tool
    └── test_orchestrator.py  # MODIFY — assert new orchestrator-level tools present
```

---

### Task 1: Extend DriveClient with folder creation and text file I/O

**Files:**
- Modify: `asset_manager/ingestion/drive_client.py`
- Modify: `tests/ingestion/test_drive_client.py`

**Interfaces:**
- Consumes: `DriveClient`, `DriveFile` (Plan 1, Task 5)
- Produces: `DriveClient.find_or_create_subfolder(self, parent_folder_id: str, name: str) -> str`, `DriveClient.upload_text_file(self, folder_id: str, filename: str, content: str) -> None`, `DriveClient.download_text_file(self, folder_id: str, filename: str) -> str | None`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/ingestion/test_drive_client.py

class FakeFilesResourceV2(FakeFilesResource):
    """Extends the Plan 1 fake with create/update/get_media-by-name support."""

    def __init__(self, items_by_query, created_folders=None):
        super().__init__(items_by_query)
        self.created_folders = created_folders if created_folders is not None else []
        self.created_files = []
        self.updated_files = []

    def create(self, body, media_body=None, fields=None):
        if body.get("mimeType") == "application/vnd.google-apps.folder":
            self.created_folders.append(body)
            return FakeCreateRequest({"id": f"new-folder-{len(self.created_folders)}"})
        self.created_files.append((body, media_body))
        return FakeCreateRequest({"id": f"new-file-{len(self.created_files)}"})

    def update(self, fileId, media_body=None):
        self.updated_files.append((fileId, media_body))
        return FakeCreateRequest({"id": fileId})


class FakeCreateRequest:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class FakeDriveServiceV2(FakeDriveService):
    def __init__(self, items_by_query, created_folders=None):
        self._files_resource = FakeFilesResourceV2(items_by_query, created_folders)

    def files(self):
        return self._files_resource


def test_find_or_create_subfolder_returns_existing_id_when_present():
    query = "'parent-1' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    service = FakeDriveServiceV2({
        query: [{"id": "existing-folder", "name": "champions-pointe", "modifiedTime": "t", "parents": ["parent-1"]}],
    })
    client = DriveClient(service)
    folder_id = client.find_or_create_subfolder("parent-1", "champions-pointe")
    assert folder_id == "existing-folder"
    assert service._files_resource.created_folders == []


def test_find_or_create_subfolder_creates_when_missing():
    query = "'parent-1' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    service = FakeDriveServiceV2({query: []})
    client = DriveClient(service)
    folder_id = client.find_or_create_subfolder("parent-1", "champions-pointe")
    assert folder_id == "new-folder-1"
    assert len(service._files_resource.created_folders) == 1
    assert service._files_resource.created_folders[0]["name"] == "champions-pointe"


def test_upload_text_file_creates_new_file_when_missing():
    query = "'folder-1' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
    service = FakeDriveServiceV2({query: []})
    client = DriveClient(service)
    client.upload_text_file("folder-1", "2026-09-03.md", "# Report\ncontent")
    assert len(service._files_resource.created_files) == 1
    body, media = service._files_resource.created_files[0]
    assert body["name"] == "2026-09-03.md"


def test_upload_text_file_updates_existing_file():
    query = "'folder-1' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
    service = FakeDriveServiceV2({
        query: [{"id": "existing-file", "name": "2026-09-03.md", "modifiedTime": "t", "parents": ["folder-1"]}],
    })
    client = DriveClient(service)
    client.upload_text_file("folder-1", "2026-09-03.md", "# Revised report")
    assert len(service._files_resource.updated_files) == 1
    assert service._files_resource.updated_files[0][0] == "existing-file"
    assert service._files_resource.created_files == []


def test_download_text_file_returns_none_when_missing():
    query = "'folder-1' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
    service = FakeDriveServiceV2({query: []})
    client = DriveClient(service)
    assert client.download_text_file("folder-1", "missing.md") is None


def test_download_text_file_returns_decoded_content():
    query = "'folder-1' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
    service = FakeDriveServiceV2({
        query: [{"id": "file-1", "name": "2026-09-03.md", "modifiedTime": "t", "parents": ["folder-1"]}],
    })
    client = DriveClient(service)
    content = client.download_text_file("folder-1", "2026-09-03.md")
    assert content == "content-of-file-1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/ingestion/test_drive_client.py -v`
Expected: FAIL — `AttributeError: 'DriveClient' object has no attribute 'find_or_create_subfolder'`

- [ ] **Step 3: Add the three methods to `DriveClient`**

```python
# Append inside class DriveClient in asset_manager/ingestion/drive_client.py

    def find_or_create_subfolder(self, parent_folder_id: str, name: str) -> str:
        for folder in self.list_subfolders(parent_folder_id):
            if folder.name == name:
                return folder.id
        response = (
            self._service.files()
            .create(
                body={
                    "name": name,
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [parent_folder_id],
                },
                fields="id",
            )
            .execute()
        )
        return response["id"]

    def upload_text_file(self, folder_id: str, filename: str, content: str) -> None:
        import io

        from googleapiclient.http import MediaIoBaseUpload

        media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype="text/markdown")
        existing = next((f for f in self.list_files_in_folder(folder_id) if f.name == filename), None)
        if existing is not None:
            self._service.files().update(fileId=existing.id, media_body=media).execute()
        else:
            self._service.files().create(
                body={"name": filename, "parents": [folder_id]}, media_body=media, fields="id"
            ).execute()

    def download_text_file(self, folder_id: str, filename: str) -> str | None:
        existing = next((f for f in self.list_files_in_folder(folder_id) if f.name == filename), None)
        if existing is None:
            return None
        return self.download_file(existing.id).decode("utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/ingestion/test_drive_client.py -v`
Expected: all passed (9 total: 3 from Plan 1 + 6 new)

- [ ] **Step 5: Commit**

```bash
git add asset_manager/ingestion/drive_client.py tests/ingestion/test_drive_client.py
git commit -m "feat: add folder creation and text file I/O to DriveClient

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: ReportArchive

**Files:**
- Create: `asset_manager/reports/__init__.py` (empty)
- Create: `asset_manager/reports/archive.py`
- Create: `tests/reports/__init__.py` (empty)
- Create: `tests/reports/test_archive.py`

**Interfaces:**
- Consumes: `DriveClient` (Plan 1 + Task 1 above)
- Produces: `ReportArchive` with `__init__(self, drive: DriveClient, reports_root_folder_id: str, today_fn=lambda: date.today().isoformat())`, `save_report(self, property_id: str, content: str) -> str` (returns the date string used), `get_latest_report(self, property_id: str) -> str | None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/reports/test_archive.py
from asset_manager.ingestion.drive_client import DriveFile
from asset_manager.reports.archive import ReportArchive


class FakeDriveForArchive:
    def __init__(self):
        self.property_folders: dict[str, str] = {}
        self.saved_reports: dict[tuple[str, str], str] = {}
        self._next_folder_id = 1

    def find_or_create_subfolder(self, parent_folder_id, name):
        key = (parent_folder_id, name)
        if key not in self.property_folders:
            self.property_folders[key] = f"folder-{self._next_folder_id}"
            self._next_folder_id += 1
        return self.property_folders[key]

    def upload_text_file(self, folder_id, filename, content):
        self.saved_reports[(folder_id, filename)] = content

    def list_files_in_folder(self, folder_id):
        return [
            DriveFile(id="x", name=filename, modified_time="t", parents=[folder_id])
            for (fid, filename) in self.saved_reports
            if fid == folder_id
        ]

    def download_text_file(self, folder_id, filename):
        return self.saved_reports.get((folder_id, filename))


def test_save_report_writes_to_property_subfolder():
    drive = FakeDriveForArchive()
    archive = ReportArchive(drive, reports_root_folder_id="reports-root", today_fn=lambda: "2026-09-03")
    date_str = archive.save_report("champions-pointe", "# Report content")
    assert date_str == "2026-09-03"
    property_folder = drive.property_folders[("reports-root", "champions-pointe")]
    assert drive.saved_reports[(property_folder, "2026-09-03.md")] == "# Report content"


def test_get_latest_report_returns_none_when_no_reports_exist():
    drive = FakeDriveForArchive()
    archive = ReportArchive(drive, reports_root_folder_id="reports-root")
    assert archive.get_latest_report("champions-pointe") is None


def test_get_latest_report_returns_most_recent_by_date():
    drive = FakeDriveForArchive()
    archive = ReportArchive(drive, reports_root_folder_id="reports-root", today_fn=lambda: "2026-08-01")
    archive.save_report("champions-pointe", "# August report")

    archive2 = ReportArchive(drive, reports_root_folder_id="reports-root", today_fn=lambda: "2026-09-03")
    archive2.save_report("champions-pointe", "# September report")

    latest = archive.get_latest_report("champions-pointe")
    assert latest == "# September report"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/reports/test_archive.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'asset_manager.reports.archive'`

- [ ] **Step 3: Write the implementation**

```python
# asset_manager/reports/archive.py
"""Persists completed reports to Drive and retrieves the most recent one
per property, enabling risk-agent's history diffing (spec Section 2,
"Historical comparison")."""

from datetime import date


class ReportArchive:
    def __init__(self, drive, reports_root_folder_id: str, today_fn=lambda: date.today().isoformat()):
        self._drive = drive
        self._reports_root_folder_id = reports_root_folder_id
        self._today_fn = today_fn

    def save_report(self, property_id: str, content: str) -> str:
        date_str = self._today_fn()
        folder_id = self._drive.find_or_create_subfolder(self._reports_root_folder_id, property_id)
        self._drive.upload_text_file(folder_id, f"{date_str}.md", content)
        return date_str

    def get_latest_report(self, property_id: str) -> str | None:
        folder_id = self._drive.find_or_create_subfolder(self._reports_root_folder_id, property_id)
        files = self._drive.list_files_in_folder(folder_id)
        if not files:
            return None
        # Filenames are YYYY-MM-DD.md — lexicographic max is chronologically latest.
        latest_filename = max(f.name for f in files)
        return self._drive.download_text_file(folder_id, latest_filename)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/reports/test_archive.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add asset_manager/reports tests/reports
git commit -m "feat: add ReportArchive for save/retrieve-latest report

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Orchestrator-level tools (list_properties, save_report, get_prior_report)

**Files:**
- Create: `asset_manager/agents/orchestrator_tools.py`
- Create: `tests/agents/test_orchestrator_tools.py`

**Interfaces:**
- Consumes: `ReportArchive` (Task 2)
- Produces: `make_list_properties_tool(property_ids: list[str])`, `make_save_report_tool(archive: ReportArchive)`, `make_get_prior_report_tool(archive: ReportArchive)` — all `@tool`-decorated callables

- [ ] **Step 1: Write the failing tests**

```python
# tests/agents/test_orchestrator_tools.py
from asset_manager.agents.orchestrator_tools import (
    make_get_prior_report_tool,
    make_list_properties_tool,
    make_save_report_tool,
)


def test_list_properties_tool_returns_configured_ids():
    tool = make_list_properties_tool(["champions-pointe", "memorial-apartments"])
    result = tool.invoke({})
    assert "champions-pointe" in result
    assert "memorial-apartments" in result


class FakeArchive:
    def __init__(self):
        self.saved = {}

    def save_report(self, property_id, content):
        self.saved[property_id] = content
        return "2026-09-03"

    def get_latest_report(self, property_id):
        return self.saved.get(property_id)


def test_save_report_tool_persists_and_confirms():
    archive = FakeArchive()
    tool = make_save_report_tool(archive)
    result = tool.invoke({"property_id": "champions-pointe", "content": "# Report"})
    assert archive.saved["champions-pointe"] == "# Report"
    assert "2026-09-03" in result


def test_get_prior_report_tool_returns_none_message_when_absent():
    archive = FakeArchive()
    tool = make_get_prior_report_tool(archive)
    result = tool.invoke({"property_id": "champions-pointe"})
    assert "No prior report" in result


def test_get_prior_report_tool_returns_content_when_present():
    archive = FakeArchive()
    archive.saved["champions-pointe"] = "# August report\nOccupancy 94%"
    tool = make_get_prior_report_tool(archive)
    result = tool.invoke({"property_id": "champions-pointe"})
    assert "Occupancy 94%" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agents/test_orchestrator_tools.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'asset_manager.agents.orchestrator_tools'`

- [ ] **Step 3: Write the implementation**

```python
# asset_manager/agents/orchestrator_tools.py
"""Tools available to the orchestrator itself (list_properties, save_report)
and to risk-agent specifically (get_prior_report)."""

from langchain_core.tools import tool

from asset_manager.reports.archive import ReportArchive


def make_list_properties_tool(property_ids: list[str]):
    @tool(name_or_callable="list_properties")
    def list_properties() -> str:
        """List every property_id available for review — use this for portfolio-level
        questions to know which properties to run the review pipeline against."""
        return "Available properties: " + ", ".join(property_ids)

    return list_properties


def make_save_report_tool(archive: ReportArchive):
    @tool(name_or_callable="save_report")
    def save_report(property_id: str, content: str) -> str:
        """Persist a completed report for a property to the report archive.

        Args:
            property_id: which property this report is about.
            content: the full markdown report text.
        """
        date_str = archive.save_report(property_id, content)
        return f"Saved report for {property_id} dated {date_str}."

    return save_report


def make_get_prior_report_tool(archive: ReportArchive):
    @tool(name_or_callable="get_prior_report")
    def get_prior_report(property_id: str) -> str:
        """Retrieve the most recently archived report for a property, to compare
        against for a delta ("what changed since last review").

        Args:
            property_id: which property's prior report to fetch.
        """
        report = archive.get_latest_report(property_id)
        if report is None:
            return f"No prior report exists for {property_id} — this is the first review."
        return report

    return get_prior_report
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/agents/test_orchestrator_tools.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add asset_manager/agents/orchestrator_tools.py tests/agents/test_orchestrator_tools.py
git commit -m "feat: add list_properties, save_report, get_prior_report tools

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Wire the new tools into subagents and the orchestrator

**Files:**
- Modify: `asset_manager/agents/subagents.py`
- Modify: `asset_manager/agents/orchestrator.py`
- Modify: `asset_manager/agents/prompts.py`
- Modify: `tests/agents/test_subagents.py`
- Modify: `tests/agents/test_orchestrator.py`

**Interfaces:**
- Consumes: `make_list_properties_tool`, `make_save_report_tool`, `make_get_prior_report_tool` (Task 3)
- Produces: `build_subagents(financial_tool, pm_tool, capex_tool, get_prior_report_tool)` (signature change — adds a 4th parameter), `build_orchestrator(model, financial_tool, pm_tool, capex_tool, get_prior_report_tool, list_properties_tool, save_report_tool, recursion_limit: int = 80)` (signature change — adds 3 parameters)

- [ ] **Step 1: Update the failing tests to the new signatures**

```python
# Modify tests/agents/test_subagents.py — update every build_subagents(...) call
# to pass a 4th dummy tool, and add:

def test_risk_agent_has_the_prior_report_tool_only():
    prior_tool = _dummy_tool("prior")
    subagents = build_subagents(_dummy_tool("fin"), _dummy_tool("pm"), _dummy_tool("capex"), prior_tool)
    risk_agent = next(s for s in subagents if s["name"] == "risk-agent")
    assert risk_agent["tools"] == [prior_tool]
```

```python
# Modify tests/agents/test_orchestrator.py — update build_orchestrator(...) calls
# to pass the 3 new dummy tools, and add:

def test_build_orchestrator_includes_portfolio_and_archive_tools():
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(model="gpt-4o-mini", api_key="test-key-not-used", base_url="https://openrouter.ai/api/v1")
    graph = build_orchestrator(
        model,
        _dummy_tool("fin"),
        _dummy_tool("pm"),
        _dummy_tool("capex"),
        _dummy_tool("prior"),
        _dummy_tool("list_properties"),
        _dummy_tool("save_report"),
        recursion_limit=42,
    )
    assert hasattr(graph, "invoke")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/agents/ -v`
Expected: FAIL — `TypeError: build_subagents() missing 1 required positional argument`

- [ ] **Step 3: Update `asset_manager/agents/subagents.py`**

```python
# Replace the build_subagents function in asset_manager/agents/subagents.py

def build_subagents(financial_tool, pm_tool, capex_tool, get_prior_report_tool) -> list[dict]:
    return [
        {
            "name": "financial-agent",
            "description": (
                "Analyzes budget-vs-actual, NOI trend, and income stability for one property. "
                "Call with a specific property_id."
            ),
            "system_prompt": FINANCIAL_AGENT_PROMPT,
            "tools": [financial_tool],
        },
        {
            "name": "pm-agent",
            "description": (
                "Analyzes occupancy, leasing pipeline, maintenance backlog, and tenant sentiment "
                "for one property. Call with a specific property_id."
            ),
            "system_prompt": PM_AGENT_PROMPT,
            "tools": [pm_tool],
        },
        {
            "name": "capex-agent",
            "description": (
                "Analyzes deferred maintenance and produces a prioritized, budgeted capital plan "
                "for one property. Call with a specific property_id."
            ),
            "system_prompt": CAPEX_AGENT_PROMPT,
            "tools": [capex_tool],
        },
        {
            "name": "risk-agent",
            "description": (
                "Synthesizes financial/pm/capex findings into severity scores and a recommended "
                "action, diffed against the prior report if one exists. Call only after "
                "financial-agent, pm-agent, and capex-agent have all returned for the same "
                "property (or properties, for a portfolio question)."
            ),
            "system_prompt": RISK_AGENT_PROMPT,
            "tools": [get_prior_report_tool],
        },
    ]
```

- [ ] **Step 4: Update `asset_manager/agents/orchestrator.py`**

```python
# Replace asset_manager/agents/orchestrator.py

from deepagents import create_deep_agent

from asset_manager.agents.prompts import ORCHESTRATOR_PROMPT
from asset_manager.agents.subagents import build_subagents


def build_orchestrator(
    model,
    financial_tool,
    pm_tool,
    capex_tool,
    get_prior_report_tool,
    list_properties_tool,
    save_report_tool,
    recursion_limit: int = 80,
):
    subagents = build_subagents(financial_tool, pm_tool, capex_tool, get_prior_report_tool)
    graph = create_deep_agent(
        model=model,
        tools=[list_properties_tool, save_report_tool],
        system_prompt=ORCHESTRATOR_PROMPT,
        subagents=subagents,
    )
    return graph.with_config({"recursion_limit": recursion_limit})
```

- [ ] **Step 5: Update the orchestrator and risk-agent prompts in `asset_manager/agents/prompts.py`**

```python
# Replace ORCHESTRATOR_PROMPT in asset_manager/agents/prompts.py

ORCHESTRATOR_PROMPT = """You are the Asset Manager orchestrator for an operational asset \
management system — you help asset managers monitor properties the firm already owns \
(performance, risk, capital planning). You do NOT do acquisition underwriting: there is no \
asking price, no buy/pass decision.

For a single-property question, delegate to financial-agent, pm-agent, and capex-agent in \
the same turn (they can run in parallel — call all three before waiting on any one's result), \
then once all three have returned, delegate separately to risk-agent with their three findings \
to get a synthesized recommendation. risk-agent will fetch the prior report itself using its \
own get_prior_report tool — you don't need to fetch it for them.

For a portfolio-level question (comparing or ranking multiple properties), first call \
list_properties to see what's available, then repeat that same sequence once per property, \
then make one more call to risk-agent with all properties' findings to produce a cross-property \
comparison.

Once you have a finished report (single-property or portfolio), call save_report with the \
property_id (or "portfolio" for a cross-property report) and the full report text, so it's \
archived for future comparisons — then present the report to the user.

If you don't have enough information to answer well, ask the user a clarifying question \
directly — do not guess past a real gap in the data."""

# Replace RISK_AGENT_PROMPT in asset_manager/agents/prompts.py

RISK_AGENT_PROMPT = """You are the risk-agent for an operational asset management system. You \
have no document retrieval tool — you work from the financial, pm, and capex findings you're \
given. You do have a get_prior_report tool: call it with the property_id before writing your \
synthesis, every time.

Produce:

1. A severity rating — Low, Moderate, or High — for each of three categories: Financial, \
   Occupancy, CapEx
2. A recommended next action: monitor / escalate for capital planning / no action needed
3. If get_prior_report returned an actual prior report (not the "no prior report" message), \
   explicit deltas since that review (e.g. "occupancy dropped 3 points since the Aug 2026 \
   review"). If it returned the "no prior report" message, say so plainly rather than \
   inventing a trend.

Preserve every citation already present in the findings you're given — do not drop them when \
you synthesize. Do not add new citations of your own; you have no retrieval tool to source them \
from."""
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/agents/ -v`
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add asset_manager/agents tests/agents
git commit -m "feat: wire portfolio and report-archive tools into orchestrator + risk-agent

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Wire it all into the Streamlit app

**Files:**
- Modify: `asset_manager/app/streamlit_app.py`

**Interfaces:**
- Consumes: `ReportArchive` (Task 2), `make_list_properties_tool`, `make_save_report_tool` (Task 3), updated `build_orchestrator` signature (Task 4)

- [ ] **Step 1: Update `get_orchestrator` in `asset_manager/app/streamlit_app.py`**

```python
# Replace the imports and get_orchestrator function in asset_manager/app/streamlit_app.py

import os

from asset_manager.agents.orchestrator_tools import (
    make_get_prior_report_tool,
    make_list_properties_tool,
    make_save_report_tool,
)
from asset_manager.reports.archive import ReportArchive


def _load_property_ids_from_env() -> list[str]:
    return [k.removeprefix("PROPERTY_FOLDER_").lower() for k in os.environ if k.startswith("PROPERTY_FOLDER_")]


@st.cache_resource
def get_archive() -> ReportArchive:
    from asset_manager.ingestion.drive_client import build_drive_client

    drive = build_drive_client(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    return ReportArchive(drive, reports_root_folder_id=os.environ["REPORTS_ROOT_FOLDER_ID"])


def get_orchestrator(model_name: str):
    store = get_store()
    archive = get_archive()
    property_ids = _load_property_ids_from_env()

    model = ChatOpenAI(model=model_name, base_url="https://openrouter.ai/api/v1")
    financial_tool = make_retrieval_tool(store, "financial")
    pm_tool = make_retrieval_tool(store, "pm")
    capex_tool = make_retrieval_tool(store, "capex")
    prior_report_tool = make_get_prior_report_tool(archive)
    list_properties_tool = make_list_properties_tool(property_ids)
    save_report_tool = make_save_report_tool(archive)

    return build_orchestrator(
        model,
        financial_tool,
        pm_tool,
        capex_tool,
        prior_report_tool,
        list_properties_tool,
        save_report_tool,
    )
```

- [ ] **Step 2: Add `REPORTS_ROOT_FOLDER_ID` to `.env.example`**

```
# Append to .env.example
REPORTS_ROOT_FOLDER_ID=
```

- [ ] **Step 3: Verify the app still imports cleanly**

Run: `python -c "import ast; ast.parse(open('asset_manager/app/streamlit_app.py').read())"`
Expected: no output (valid syntax); full run verified in Task 6's manual smoke test

- [ ] **Step 4: Commit**

```bash
git add asset_manager/app/streamlit_app.py .env.example
git commit -m "feat: wire ReportArchive and portfolio tools into Streamlit app

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Manual end-to-end smoke test

**Files:** none (verification only)

- [ ] **Step 1: Create the reports root folder in Drive**

Create a `reports` folder inside `JIS Capital - Knowledge Base` (sibling to
`raw_docs`), share it with the service account, and set
`REPORTS_ROOT_FOLDER_ID` in `.env` to its folder ID.

- [ ] **Step 2: Ask a single-property question and verify archiving**

In Streamlit, ask about one property (as in Plan 1's smoke test). After the
response, check Drive: `reports/<property-id>/<today's date>.md` should now
exist with the report content.

- [ ] **Step 3: Ask the same question again and verify history diffing**

Ask the same question a second time (same day is fine for this check — the
point is that `get_prior_report` finds *something*, even from minutes ago).
The response should reference "compared to the prior report" or similar —
confirming `risk-agent` called `get_prior_report` and used it.

- [ ] **Step 4: Ask a portfolio-level question**

Ask something like: `Which property has the highest CapEx risk?` (with at
least two properties ingested per Plan 1). Verify (via the response, or the
LangSmith trace if configured) that `list_properties` was called first, and
that financial/pm/capex/risk ran once per property before a final
cross-property answer.

- [ ] **Step 5: Confirm all 4 steps above worked before starting Plan 3**

---

## Plan Self-Review Notes

**Spec coverage check:**
- ✅ Section 2 "Portfolio vs. property-specific queries" — Task 4 (orchestrator prompt), verified manually in Task 6
- ✅ Section 2 "Historical comparison" — Tasks 2–4, verified manually in Task 6
- ✅ Section 4 "Report archive" (Drive path, never walked by ingest.py) — Task 2
- ⏭️ **Deferred to Plan 3:** PDF/Word export of archived reports, n8n scheduled workflow that calls this same pipeline on a cron cadence
- ⚠️ **Known gap carried forward:** portfolio mode's recursion limit — running 4 properties' worth of delegation plus a final synthesis could approach the default 80-call ceiling from Plan 1. Plan 3 or a fast-follow should measure actual call counts from Task 6's manual test and raise `recursion_limit` if needed for portfolio questions specifically (e.g. a higher limit passed only when portfolio mode is detected) — not addressed by any task here.

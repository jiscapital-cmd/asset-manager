# Asset Manager — Export & Automation Implementation Plan (Plan 3 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let any report be downloaded as PDF/Word, and build the n8n scheduled review
workflow — a small HTTP endpoint n8n's cron trigger calls, which runs the orchestrator
per property, archives the result, exports it, and notifies.

**Architecture:** A markdown-to-DOCX/PDF renderer (pure Python, no external binaries).
A `run_scheduled_review` pure-function orchestrator (testable with fakes) wrapped by a
small FastAPI app that n8n's HTTP Request node calls on a schedule. An n8n workflow
JSON file, committed to the repo, that a human imports into their n8n instance — n8n
workflows aren't executable Python, so this is documentation/config, not code under
test, and is verified by manual import (Task 6).

**Tech Stack:** Adds `python-docx` (already a Plan 1 dependency), `reportlab` (pure-Python
PDF generation, no external binary like wkhtmltopdf), `fastapi`, `uvicorn`, `httpx` (test
client), `requests` (Slack webhook).

**Spec:** `docs/superpowers/specs/2026-09-03-asset-manager-design.md`
**Depends on:** Plan 1 (`docs/superpowers/plans/2026-09-03-asset-manager-core-pipeline.md`) and Plan 2 (`docs/superpowers/plans/2026-09-03-asset-manager-portfolio-history.md`) — imports `build_orchestrator`, `ReportArchive`, `ChromaStore`, and the tool factories from both.

## Global Constraints

(All of Plan 1 and Plan 2's constraints still apply. Additionally:)

- Export formats: PDF and Word (DOCX), same content as the chat/archived report — spec Section 2 "Delivery formats"
- n8n sits entirely outside the orchestrator's reasoning loop — it triggers or reacts, the orchestrator never waits on it (spec Section 6)
- No external API cost/complexity for PDF rendering — pure-Python (`reportlab`), no headless browser or system binary dependency
- The scheduled review endpoint must not block indefinitely — bounded by the same recursion/timeout ceilings as any orchestrator run (spec Section 7)

---

## File Structure

```
asset_manager/
├── export/
│   ├── __init__.py
│   └── render.py              # markdown_to_docx_bytes(), markdown_to_pdf_bytes()
├── automation/
│   ├── __init__.py
│   ├── scheduled_review.py    # run_scheduled_review() — pure orchestration, testable with fakes
│   └── api.py                 # FastAPI app: POST /reviews/run, GET /health
├── notify/
│   ├── __init__.py
│   └── slack.py                # SlackWebhookNotifier + NotifierProtocol
└── app/
    └── streamlit_app.py        # MODIFY — add "Download report" buttons

n8n/
└── scheduled-review.workflow.json   # importable n8n workflow definition

tests/
├── export/
│   └── test_render.py
├── automation/
│   ├── test_scheduled_review.py
│   └── test_api.py
└── notify/
    └── test_slack.py
```

---

### Task 1: Markdown → DOCX export

**Files:**
- Create: `asset_manager/export/__init__.py` (empty)
- Create: `asset_manager/export/render.py`
- Create: `tests/export/__init__.py` (empty)
- Create: `tests/export/test_render.py`

**Interfaces:**
- Produces: `markdown_to_docx_bytes(title: str, markdown_content: str) -> bytes`

- [ ] **Step 1: Write the failing tests**

```python
# tests/export/test_render.py
import io

from docx import Document

from asset_manager.export.render import markdown_to_docx_bytes


def test_markdown_to_docx_includes_title():
    content = "## Summary\nOccupancy is 94%."
    doc_bytes = markdown_to_docx_bytes("Champions Pointe — Sep 2026", content)
    doc = Document(io.BytesIO(doc_bytes))
    all_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Champions Pointe — Sep 2026" in all_text


def test_markdown_to_docx_renders_headings_and_body():
    content = "## Financial\nNOI came in under budget.\n## Risk\nModerate overall."
    doc_bytes = markdown_to_docx_bytes("Report", content)
    doc = Document(io.BytesIO(doc_bytes))
    all_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Financial" in all_text
    assert "NOI came in under budget." in all_text
    assert "Risk" in all_text
    assert "Moderate overall." in all_text


def test_markdown_to_docx_renders_bullet_lists():
    content = "## Findings\n- Occupancy dropped 3 points\n- Roof reserve is underfunded"
    doc_bytes = markdown_to_docx_bytes("Report", content)
    doc = Document(io.BytesIO(doc_bytes))
    all_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Occupancy dropped 3 points" in all_text
    assert "Roof reserve is underfunded" in all_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/export/test_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'asset_manager.export.render'`

- [ ] **Step 3: Write the DOCX half of the implementation**

```python
# asset_manager/export/render.py
"""Render a markdown report (as produced by the orchestrator) into DOCX/PDF.

Supports a deliberately small markdown subset — the orchestrator is
instructed (spec Section 3) to write reports as headings, paragraphs, and
bullet lists, which is all real asset-management reports need.
"""

import io


def _parse_markdown_lines(markdown_content: str) -> list[tuple[str, str]]:
    """Return [(kind, text), ...] where kind is 'heading', 'bullet', or 'paragraph'."""
    lines = []
    for raw_line in markdown_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            lines.append(("heading", line[3:]))
        elif line.startswith("# "):
            lines.append(("heading", line[2:]))
        elif line.startswith("- "):
            lines.append(("bullet", line[2:]))
        else:
            lines.append(("paragraph", line))
    return lines


def markdown_to_docx_bytes(title: str, markdown_content: str) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading(title, level=0)
    for kind, text in _parse_markdown_lines(markdown_content):
        if kind == "heading":
            doc.add_heading(text, level=2)
        elif kind == "bullet":
            doc.add_paragraph(text, style="List Bullet")
        else:
            doc.add_paragraph(text)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/export/test_render.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add asset_manager/export tests/export
git commit -m "feat: add markdown-to-DOCX report export

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Markdown → PDF export

**Files:**
- Modify: `asset_manager/export/render.py`
- Modify: `tests/export/test_render.py`

**Interfaces:**
- Consumes: `_parse_markdown_lines` (Task 1)
- Produces: `markdown_to_pdf_bytes(title: str, markdown_content: str) -> bytes`

- [ ] **Step 1: Write the failing tests**

```python
# Append to tests/export/test_render.py
from pypdf import PdfReader

from asset_manager.export.render import markdown_to_pdf_bytes


def test_markdown_to_pdf_produces_valid_pdf_bytes():
    content = "## Summary\nOccupancy is 94%."
    pdf_bytes = markdown_to_pdf_bytes("Champions Pointe", content)
    assert pdf_bytes.startswith(b"%PDF")


def test_markdown_to_pdf_is_readable_and_has_at_least_one_page():
    content = "## Summary\nOccupancy is 94%."
    pdf_bytes = markdown_to_pdf_bytes("Champions Pointe", content)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1


def test_markdown_to_pdf_includes_title_text():
    content = "## Summary\nOccupancy is 94%."
    pdf_bytes = markdown_to_pdf_bytes("Champions Pointe Review", content)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    extracted = reader.pages[0].extract_text()
    assert "Champions Pointe Review" in extracted
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/export/test_render.py -v`
Expected: FAIL with `ImportError: cannot import name 'markdown_to_pdf_bytes'`

- [ ] **Step 3: Add the PDF renderer**

```python
# Append to asset_manager/export/render.py

def markdown_to_pdf_bytes(title: str, markdown_content: str) -> bytes:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER)

    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    bullet_buffer: list[str] = []

    def flush_bullets():
        if bullet_buffer:
            story.append(
                ListFlowable(
                    [ListItem(Paragraph(b, styles["Normal"])) for b in bullet_buffer],
                    bulletType="bullet",
                )
            )
            bullet_buffer.clear()

    for kind, text in _parse_markdown_lines(markdown_content):
        if kind == "bullet":
            bullet_buffer.append(text)
            continue
        flush_bullets()
        if kind == "heading":
            story.append(Paragraph(text, styles["Heading2"]))
        else:
            story.append(Paragraph(text, styles["Normal"]))
        story.append(Spacer(1, 6))
    flush_bullets()

    doc.build(story)
    return buf.getvalue()
```

- [ ] **Step 4: Add the missing `io` import used by the new PDF tests**

```python
# At the top of tests/export/test_render.py, add:
import io
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/export/test_render.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add asset_manager/export/render.py tests/export/test_render.py
git commit -m "feat: add markdown-to-PDF report export

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Slack notifier

**Files:**
- Create: `asset_manager/notify/__init__.py` (empty)
- Create: `asset_manager/notify/slack.py`
- Create: `tests/notify/__init__.py` (empty)
- Create: `tests/notify/test_slack.py`

**Interfaces:**
- Produces: `SlackWebhookNotifier` with `__init__(self, webhook_url: str, post_fn=requests.post)`, `send(self, message: str) -> None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/notify/test_slack.py
from asset_manager.notify.slack import SlackWebhookNotifier


class FakePostFn:
    def __init__(self):
        self.calls = []

    def __call__(self, url, json, timeout=10):
        self.calls.append((url, json))

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

        return FakeResponse()


def test_send_posts_message_as_slack_text_payload():
    post_fn = FakePostFn()
    notifier = SlackWebhookNotifier("https://hooks.slack.com/services/xxx", post_fn=post_fn)
    notifier.send("Champions Pointe review is ready.")
    assert len(post_fn.calls) == 1
    url, payload = post_fn.calls[0]
    assert url == "https://hooks.slack.com/services/xxx"
    assert payload == {"text": "Champions Pointe review is ready."}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/notify/test_slack.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'asset_manager.notify.slack'`

- [ ] **Step 3: Write the implementation**

```python
# asset_manager/notify/slack.py
"""Sends a notification to a Slack incoming webhook."""

import requests


class SlackWebhookNotifier:
    def __init__(self, webhook_url: str, post_fn=requests.post):
        self._webhook_url = webhook_url
        self._post_fn = post_fn

    def send(self, message: str) -> None:
        response = self._post_fn(self._webhook_url, json={"text": message}, timeout=10)
        response.raise_for_status()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/notify/test_slack.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add asset_manager/notify tests/notify
git commit -m "feat: add Slack webhook notifier

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Scheduled review orchestration (pure function)

**Files:**
- Create: `asset_manager/automation/__init__.py` (empty)
- Create: `asset_manager/automation/scheduled_review.py`
- Create: `tests/automation/__init__.py` (empty)
- Create: `tests/automation/test_scheduled_review.py`

**Interfaces:**
- Consumes: nothing directly imported — takes its dependencies as parameters so it's testable without real Drive/LLM/Slack access
- Produces: `ScheduledReviewResult` (dataclass: `property_id: str, report_text: str, docx_bytes: bytes, pdf_bytes: bytes`), `run_scheduled_review(property_ids: list[str], run_review_fn: Callable[[str], str], export_docx_fn: Callable[[str, str], bytes], export_pdf_fn: Callable[[str, str], bytes], notify_fn: Callable[[str], None]) -> list[ScheduledReviewResult]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/automation/test_scheduled_review.py
from asset_manager.automation.scheduled_review import run_scheduled_review


def test_run_scheduled_review_runs_each_property_and_notifies():
    reviewed = []
    notified = []

    def fake_run_review(property_id: str) -> str:
        reviewed.append(property_id)
        return f"# Report for {property_id}\nAll good."

    def fake_export_docx(title, content):
        return b"docx-bytes"

    def fake_export_pdf(title, content):
        return b"pdf-bytes"

    def fake_notify(message):
        notified.append(message)

    results = run_scheduled_review(
        property_ids=["champions-pointe", "memorial-apartments"],
        run_review_fn=fake_run_review,
        export_docx_fn=fake_export_docx,
        export_pdf_fn=fake_export_pdf,
        notify_fn=fake_notify,
    )

    assert reviewed == ["champions-pointe", "memorial-apartments"]
    assert len(results) == 2
    assert results[0].property_id == "champions-pointe"
    assert results[0].docx_bytes == b"docx-bytes"
    assert results[0].pdf_bytes == b"pdf-bytes"
    assert len(notified) == 2


def test_run_scheduled_review_continues_after_one_property_fails():
    def flaky_run_review(property_id: str) -> str:
        if property_id == "memorial-apartments":
            raise RuntimeError("orchestrator timed out")
        return f"# Report for {property_id}"

    notified = []
    results = run_scheduled_review(
        property_ids=["champions-pointe", "memorial-apartments", "garfield-vista"],
        run_review_fn=flaky_run_review,
        export_docx_fn=lambda t, c: b"docx",
        export_pdf_fn=lambda t, c: b"pdf",
        notify_fn=lambda m: notified.append(m),
    )

    succeeded_ids = [r.property_id for r in results]
    assert succeeded_ids == ["champions-pointe", "garfield-vista"]
    assert any("memorial-apartments" in m and "failed" in m.lower() for m in notified)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/automation/test_scheduled_review.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'asset_manager.automation.scheduled_review'`

- [ ] **Step 3: Write the implementation**

```python
# asset_manager/automation/scheduled_review.py
"""Runs a review per property on a schedule (invoked by the n8n workflow via
asset_manager.automation.api). One property's failure doesn't abort the
others (spec Section 7, "tool errors" — "in portfolio mode, one property's
failure doesn't abort the other three")."""

from dataclasses import dataclass
from typing import Callable


@dataclass
class ScheduledReviewResult:
    property_id: str
    report_text: str
    docx_bytes: bytes
    pdf_bytes: bytes


def run_scheduled_review(
    property_ids: list[str],
    run_review_fn: Callable[[str], str],
    export_docx_fn: Callable[[str, str], bytes],
    export_pdf_fn: Callable[[str, str], bytes],
    notify_fn: Callable[[str], None],
) -> list[ScheduledReviewResult]:
    results: list[ScheduledReviewResult] = []

    for property_id in property_ids:
        try:
            report_text = run_review_fn(property_id)
        except Exception as exc:
            notify_fn(f"Scheduled review for {property_id} failed: {exc}")
            continue

        docx_bytes = export_docx_fn(property_id, report_text)
        pdf_bytes = export_pdf_fn(property_id, report_text)
        results.append(
            ScheduledReviewResult(
                property_id=property_id,
                report_text=report_text,
                docx_bytes=docx_bytes,
                pdf_bytes=pdf_bytes,
            )
        )
        notify_fn(f"Scheduled review for {property_id} is ready.")

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/automation/test_scheduled_review.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add asset_manager/automation/scheduled_review.py tests/automation/test_scheduled_review.py
git commit -m "feat: add scheduled review orchestration with per-property failure isolation

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: FastAPI endpoint for n8n to call

**Files:**
- Create: `asset_manager/automation/api.py`
- Create: `tests/automation/test_api.py`

**Interfaces:**
- Consumes: `run_scheduled_review` (Task 4)
- Produces: a FastAPI `app` with `GET /health` and `POST /reviews/run` (body: `{"property_ids": [str, ...]}`, or omit for "all configured properties")

- [ ] **Step 1: Write the failing tests**

```python
# tests/automation/test_api.py
from fastapi.testclient import TestClient

from asset_manager.automation.api import create_app


def _build_test_app():
    def fake_run_review(property_id: str) -> str:
        return f"# Report for {property_id}"

    return create_app(
        all_property_ids=["champions-pointe", "memorial-apartments"],
        run_review_fn=fake_run_review,
        export_docx_fn=lambda t, c: b"docx",
        export_pdf_fn=lambda t, c: b"pdf",
        notify_fn=lambda m: None,
    )


def test_health_returns_ok():
    client = TestClient(_build_test_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_run_reviews_with_explicit_property_ids():
    client = TestClient(_build_test_app())
    response = client.post("/reviews/run", json={"property_ids": ["champions-pointe"]})
    assert response.status_code == 200
    body = response.json()
    assert body["reviewed"] == ["champions-pointe"]


def test_run_reviews_defaults_to_all_configured_properties():
    client = TestClient(_build_test_app())
    response = client.post("/reviews/run", json={})
    assert response.status_code == 200
    body = response.json()
    assert sorted(body["reviewed"]) == ["champions-pointe", "memorial-apartments"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/automation/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'asset_manager.automation.api'`

- [ ] **Step 3: Write the implementation**

```python
# asset_manager/automation/api.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/automation/test_api.py -v`
Expected: 3 passed

- [ ] **Step 5: Wire real dependencies for production use**

```python
# Append to asset_manager/automation/api.py

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
```

- [ ] **Step 6: Commit**

```bash
git add asset_manager/automation/api.py tests/automation/test_api.py
git commit -m "feat: add FastAPI endpoint for n8n-triggered scheduled reviews

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: n8n workflow definition + Streamlit download buttons

**Files:**
- Create: `n8n/scheduled-review.workflow.json`
- Modify: `asset_manager/app/streamlit_app.py`

**Interfaces:**
- Consumes: `markdown_to_docx_bytes`, `markdown_to_pdf_bytes` (Tasks 1–2)

- [ ] **Step 1: Write the n8n workflow JSON**

```json
{
  "name": "Asset Manager - Scheduled Review",
  "nodes": [
    {
      "parameters": {
        "rule": {
          "interval": [{ "field": "cronExpression", "expression": "0 6 1 * *" }]
        }
      },
      "name": "Monthly Trigger",
      "type": "n8n-nodes-base.scheduleTrigger",
      "typeVersion": 1,
      "position": [200, 300]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "http://localhost:8000/reviews/run",
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "{}",
        "options": { "timeout": 600000 }
      },
      "name": "Run Reviews",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4,
      "position": [420, 300]
    },
    {
      "parameters": {
        "conditions": {
          "options": { "caseSensitive": true, "leftValue": "", "typeValidation": "strict" },
          "conditions": [
            {
              "leftValue": "={{ $json.statusCode }}",
              "rightValue": 200,
              "operator": { "type": "number", "operation": "equals" }
            }
          ],
          "combinator": "and"
        }
      },
      "name": "Succeeded?",
      "type": "n8n-nodes-base.if",
      "typeVersion": 2,
      "position": [640, 300]
    }
  ],
  "connections": {
    "Monthly Trigger": { "main": [[{ "node": "Run Reviews", "type": "main", "index": 0 }]] },
    "Run Reviews": { "main": [[{ "node": "Succeeded?", "type": "main", "index": 0 }]] }
  },
  "meta": {
    "description": "Calls the Asset Manager automation API (asset_manager.automation.api) on the 1st of every month at 6am. The API itself sends Slack notifications per property (see SlackWebhookNotifier) — this workflow's job is purely triggering the run, matching the spec's requirement that n8n triggers/reacts but the orchestrator never waits on it."
  }
}
```

- [ ] **Step 2: Add "Download report" buttons to Streamlit**

```python
# Append to the end of asset_manager/app/streamlit_app.py, inside the
# `if question := st.chat_input(...)` block, after displaying the answer:

        from asset_manager.export.render import markdown_to_docx_bytes, markdown_to_pdf_bytes

        docx_bytes = markdown_to_docx_bytes("Asset Manager Report", answer)
        pdf_bytes = markdown_to_pdf_bytes("Asset Manager Report", answer)

        col1, col2 = st.columns(2)
        with col1:
            st.download_button("Download as Word", docx_bytes, file_name="report.docx")
        with col2:
            st.download_button("Download as PDF", pdf_bytes, file_name="report.pdf")
```

- [ ] **Step 3: Verify the app still imports cleanly**

Run: `python -c "import ast; ast.parse(open('asset_manager/app/streamlit_app.py').read())"`
Expected: no output (valid syntax)

- [ ] **Step 4: Commit**

```bash
git add n8n asset_manager/app/streamlit_app.py
git commit -m "feat: add n8n scheduled-review workflow and Streamlit export buttons

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Manual end-to-end smoke test

**Files:** none (verification only)

- [ ] **Step 1: Create a Slack incoming webhook**

In your Slack workspace, add an "Incoming Webhooks" app to a channel, copy
the webhook URL into `.env` as `SLACK_WEBHOOK_URL`.

- [ ] **Step 2: Run the automation API locally**

Run: `uvicorn asset_manager.automation.api:build_production_app --factory --port 8000`
Expected: starts without error; `curl http://localhost:8000/health` returns `{"status":"ok"}`

- [ ] **Step 3: Trigger a review manually via curl**

Run: `curl -X POST http://localhost:8000/reviews/run -H "Content-Type: application/json" -d '{"property_ids": ["champions-pointe"]}'`
Expected: returns `{"reviewed": ["champions-pointe"]}` after the review completes; a
Slack message arrives in the configured channel; a new report appears in Drive under
`reports/champions-pointe/<today>.md`

- [ ] **Step 4: Import the n8n workflow**

In your n8n instance: Workflows → Import from File → select
`n8n/scheduled-review.workflow.json`. Update the HTTP Request node's URL if the
automation API isn't running on `localhost:8000`. Activate the workflow.

- [ ] **Step 5: Trigger the n8n workflow manually (don't wait for the cron schedule)**

In the n8n editor, click "Execute Workflow" on the Monthly Trigger node.
Expected: the same result as Step 3 — reviews run, Slack notified, reports archived.

- [ ] **Step 6: Verify PDF/Word downloads from the Streamlit chat**

Ask a question in Streamlit (from Plan 1/2), confirm both "Download as Word"
and "Download as PDF" buttons appear and produce openable files.

- [ ] **Step 7: Confirm all 6 steps above worked**

If everything passes, all three plans are complete — the system covers
ingestion, single-property and portfolio review, history diffing, PDF/Word
export, and scheduled automation.

---

## Plan Self-Review Notes

**Spec coverage check:**
- ✅ Section 2 "Delivery formats" (PDF/Word export) — Tasks 1–2, 6
- ✅ Section 6 "n8n — now built, not just hooked" (scheduled review workflow, notifications) — Tasks 3–6
- ✅ Section 7 "Tool errors ... in portfolio mode, one property's failure doesn't abort the other three" — Task 4
- ⚠️ **Known gap, not addressed by any of the 3 plans:** the n8n workflow JSON's `Succeeded?` node currently has no downstream action wired to either branch — a production version should add an Slack/email alert specifically for a non-200 response from the API (distinct from the per-property failure notifications the API itself already sends), so a total API outage is still visible. Worth a fast-follow task once the workflow is live and its failure modes are better understood.
- ⚠️ **Known gap:** `run_scheduled_review`'s `run_review_fn` (wired in `build_production_app`) sends a single free-form question to the orchestrator per property; it does not yet explicitly invoke portfolio mode as part of the scheduled job. If a periodic cross-property digest is wanted (not just N separate single-property reviews), that needs its own scheduled call using the orchestrator's portfolio-mode prompt path (Plan 2) — not built here.

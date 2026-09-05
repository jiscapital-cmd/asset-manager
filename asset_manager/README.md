# Asset Manager

An AI system for **operational asset management** — monitoring properties a firm
already owns (performance, risk, capital planning), grounded in real documents stored
in Google Drive. Not acquisition underwriting: there's no asking price, no buy/pass
decision.

A single deep-agent orchestrator (built with `deepagents` / LangGraph) delegates to
`financial-agent`, `pm-agent`, and `capex-agent` in parallel, then to `risk-agent` for
synthesis — for one property or, in portfolio mode, across all of them. See
`specs/2026-09-03-asset-manager-design.md` for the full design and `plans/` for the
three implementation plans this was built from.

## Architecture at a glance

```
Streamlit chat UI  ──┐
Automation API (n8n)─┼──► deep-agent orchestrator ──► financial/pm/capex-agent ──► risk-agent
Ingestion (CLI/n8n) ──┘         │                              │
                                 ▼                              ▼
                        Chroma (vector DB,               Report archive
                        client-server mode)              (local disk .md/.pdf/.docx)
```

Google Drive (`raw_docs/<property>/{financial,pm,capex,general}/`) is the source of
documents; ingestion chunks/embeds them into Chroma. Reports save to local disk, not
Drive — a Google service account has no storage quota of its own on a personal
(non-Workspace) Drive, so it can't create new files there even with folder access.

Full diagrams: [`docs/diagrams/system-flow.svg`](docs/diagrams/system-flow.svg) (the
pipeline above, both entry points) and
[`docs/diagrams/two-wave-delegation.svg`](docs/diagrams/two-wave-delegation.svg) (the
orchestrator's wave 1 → gate → wave 2 mechanism). An interactive version of both
lives at the [Asset Manager Flow](https://claude.ai/code/artifact/fc72a975-0974-4907-8137-00741f9ac189)
Claude artifact (private — visible only if you're signed in as its owner).

## Prerequisites

- Python 3.11+ (developed against 3.12/3.13)
- API keys: **OpenRouter** (chat models), **OpenAI** (embeddings only — OpenRouter
  doesn't proxy those)
- A **Google Cloud service account** with Drive API access (see setup below)
- Optional: a **Slack** incoming webhook + bot token (automation notifications/file
  uploads), **LangSmith** (tracing), **n8n** (scheduling)

## Setup

### 1. Install

```bash
pip install -e . pytest
```

(`dev` is a [PEP 735 dependency group](https://peps.python.org/pep-0735/), not an
extra — `pip install -e ".[dev]"` won't error, but it silently won't install `pytest`
either unless your pip is new enough to support `--group dev`. Installing it directly
alongside `-e .` sidesteps the version check entirely.)

### 2. Google Drive service account

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project,
   enable the **Drive API**, create a **service account**, and download its JSON key
   as `service-account.json` in this folder (already gitignored).
   - If your org blocks service-account key creation, you'll need an Org Policy admin
     to disable `iam.disableServiceAccountKeyCreation` for the project (or override it
     at the project level).
2. In Drive, create this structure (already expected for the 4 pilot properties):
   ```
   JIS Capital - Knowledge Base/
   ├── raw_docs/
   │   └── <Property Name>/{financial,pm,capex,general}/
   └── reports/          (empty — created for reference; reports actually save locally)
   ```
   Subfolder names (`financial`, `pm`, `capex`, `general`) must match exactly, lowercase.
3. Share `raw_docs` (Viewer) with the service account's `client_email` (from the JSON
   key file) — permissions cascade to every subfolder underneath.

### 3. Configure `.env`

Copy `.env.example` to `.env` and fill in:

- `OPENROUTER_API_KEY`, `OPENAI_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_JSON=./service-account.json`
- `PROPERTY_FOLDER_<SLUG>=<drive-folder-id>` — one per property, ID from that
  property's folder URL (`.../folders/<THIS_PART>`). `<SLUG>` becomes the internal
  `property_id` (lowercased as-is, e.g. `PROPERTY_FOLDER_CHAMPIONS_POINTE` →
  `champions_pointe`).
- `REPORTS_LOCAL_DIR` (defaults to `knowledge_base/reports`, fine to leave)
- `CHROMA_HOST`/`CHROMA_PORT` (defaults `localhost:8001`, fine to leave)
- Optional: `SLACK_WEBHOOK_URL` (text notifications), `SLACK_BOT_TOKEN` +
  `SLACK_CHANNEL_ID` (PDF file uploads — needs a Slack app with the `files:write` scope,
  invited into the target channel)

## Running it

Everything goes through **one shared Chroma server** — the Streamlit app, the
automation API, and ingestion are all separate processes that must not open the local
Chroma files directly (that caused real data-race errors in practice). Start it first,
every time:

```bash
chroma run --path knowledge_base/chroma_db --port 8001
```

### Ingest documents

Upload documents into the right Drive subfolders, then:

```bash
python -m asset_manager.ingestion.ingest
```

Safe to re-run — unchanged files are skipped (content-hash check), and one bad/
unsupported file is recorded and skipped rather than aborting the whole batch.

### Chat UI

```bash
streamlit run asset_manager/app/streamlit_app.py
```

Opens at `http://localhost:8501` — a **💬 Chat** tab (with a live "Agent steps" panel
showing every subagent delegation and tool call, down to the actual retrieval calls)
and a **📚 Knowledge Base** tab (browse ingested chunks, test retrieval queries
directly).

### Automation API (for n8n)

```bash
uvicorn asset_manager.automation.api:build_production_app --factory --port 8000
```

Exposes `GET /health`, `POST /ingest/run`, `POST /reviews/run`,
`POST /reviews/run-portfolio`. See `n8n/*.workflow.json` for importable n8n workflows
that call these on a schedule (15-min polling for ingestion, monthly for reviews) — if
n8n runs somewhere other than this machine (e.g. n8n Cloud), it can't reach
`localhost` directly; tunnel it (`ngrok http 8000`) and use the tunnel URL in the
workflow's HTTP Request nodes instead.

## Tests

```bash
pytest
```

## Project layout

```
asset_manager/
├── ingestion/     # Drive → chunk → embed → Chroma
├── retrieval/     # per-source-type retrieval tool (financial/pm/capex)
├── agents/        # subagent prompts, orchestrator (deepagents/LangGraph)
├── reports/       # report archive (local disk) + history diffing
├── export/        # markdown → DOCX/PDF
├── automation/    # FastAPI app for n8n-triggered ingestion/reviews
├── notify/        # Slack (text + file upload)
└── app/           # Streamlit chat UI

n8n/               # importable n8n workflow definitions
plans/             # implementation plans (as built)
specs/             # design spec
```

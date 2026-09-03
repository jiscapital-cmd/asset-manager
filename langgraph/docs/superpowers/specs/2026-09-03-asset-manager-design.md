# Asset Manager — Design Spec (v1)

**Status:** Approved for implementation planning
**Scope:** Single user, local machine, four pilot properties

## 1. Purpose & scope

An AI system for **ongoing operational asset management** — monitoring properties the
firm already owns (performance, risk, capital planning) — not acquisition underwriting.
There is no "asking price," no buy/pass decision, and no purchase-comps analysis.
Financial framing is budget-vs-actual and NOI trend, not cap-rate-vs-market.

**In scope for v1:** one asset manager (the user), running locally, asking questions in
a chat interface about four named properties (Champions Pointe, Memorial Apartments,
Garfield Vista, Madgrey Apartments), grounded in documents stored in Google Drive.

**Explicitly out of scope for v1:** multi-user access control, hosted/cloud deployment,
a live ResMan API integration, and a built n8n workflow (the hooks are designed but not
implemented).

## 2. Architecture

A single **deep agent** orchestrator, built with `create_deep_agent` (the same pattern as
`langgraph-advanced/deep-agents-walkthrough/competitive_analysis_agent/`), running as one
LangGraph `agent ⇄ tools` reasoning loop — not a hand-rolled `StateGraph` with fixed
fan-out edges. Delegation to specialist subagents happens dynamically, through a `task`
tool call, in **two sequential waves**:

- **Wave 1 (parallel):** the orchestrator calls `financial-agent`, `pm-agent`, and
  `capex-agent` in the same turn. Each runs its own complete `agent ⇄ tools` loop, calls
  its own Chroma-backed retrieval tool (filtered to its `source_type`), and writes its
  conclusions to its own findings file.
- **Wave 2 (sequential, gated):** only after all three wave-1 calls have returned does
  the orchestrator make a separate `task(risk-agent)` call. `risk-agent` reads the three
  findings files — it cannot run before they exist — and writes `risk_analysis.md`.

State lives in the orchestrator's **virtual filesystem** (files it reads/writes via
`ls`/`read_file`/`write_file`/`edit_file`), not a fixed `TypedDict` schema:
`analysis_request.txt`, `financial_findings.md`, `pm_findings.md`, `capex_findings.md`,
`risk_analysis.md`, `report.md`.

Full diagrams: see the published architecture artifact (runtime graph, ingestion/MCP/n8n
map, Studio's actual rendered view, and component notes).

### Human-in-the-loop

The orchestrator is conversational — if it lacks enough information to answer, it asks
the user a clarifying question as a normal chat turn (no custom `interrupt()` /
conditional-edge logic needed), backed by a checkpointer so the paused run resumes
correctly once the user answers.

### Output shape

The final report gives **risk flags + a recommended next action**
(monitor / escalate for capital planning / no action needed) — not a pursue/pass
acquisition decision. Every finding **cites its source** (e.g. "NOI figure from
T12_2026.pdf, p.3"), using the filename/page metadata captured at ingestion.

## 3. Subagents

| Subagent | Reads | Produces |
|---|---|---|
| `financial-agent` | T12s, rent rolls, budget-vs-actual, delinquency reports | Budget variance, NOI trend, income stability |
| `pm-agent` | Leases, work orders, inspections, vendor contracts | Occupancy, lease rollover risk, maintenance backlog |
| `capex-agent` | Reserve studies, condition assessments, CapEx history | Deferred maintenance, upcoming capital needs |
| `risk-agent` | The three findings files above (no retrieval tool of its own) | Synthesized risk flags + recommended action |

## 4. Knowledge base

### Document taxonomy (per property)

- **financial/** — T12s, rent rolls, budget-vs-actual, delinquency aging, debt service records
- **pm/** — leases, lease expiration schedule, occupancy reports, work order history, vendor contracts, inspection reports
- **capex/** — CapEx spend history, reserve studies, deferred maintenance logs, condition assessments, insurance claims
- **general/** — tax records, insurance policies, market reports, prior asset management memos

### Storage

Google Drive, structure: `JIS Capital - Knowledge Base/raw_docs/<property>/{financial,pm,capex,general}/`
— already created for the four pilot properties. Chosen over local disk for
multi-device access without extra code (Drive sync); accessed programmatically via the
**Google Drive MCP server** rather than a hand-written API client.

### Ingestion (`ingest.py`, offline, on demand — never part of a live run)

1. Walk the Drive `raw_docs/` tree via the Drive MCP server; `property_id` and
   `source_type` come from the folder path itself.
2. Load each file's text by type (PDF → per-page extraction, .docx → paragraph
   extraction, CSV/text → direct read).
3. Split into overlapping chunks (~800 tokens, ~100 token overlap).
4. Tag every chunk: `property_id`, `source_type`, `filename`, `page_or_row`,
   `ingested_at`.
5. Embed each chunk (OpenAI embeddings endpoint — OpenRouter does not proxy embeddings).
6. Upsert into the single Chroma collection at `knowledge_base/chroma_db/`.
7. **Content-hash check, both directions:** unchanged files are skipped; a changed or
   removed file has its old chunks deleted before any replacement is written — stale
   financials never linger alongside current ones.

At query time this is invisible to the live graph: each subagent's retrieval tool calls
Chroma similarity search with a `source_type` (and `property_id`) filter.

### Future: ResMan

Starts as manual export into Drive. A **ResMan MCP server** is the designed upgrade
path to live queries, bypassing `raw_docs/` entirely — subagents' retrieval tools don't
need to change to support it.

## 5. Front-end

Streamlit chat interface. User asks a free-form question; the orchestrator routes and
responds in the same conversation, including any clarifying questions.

**Model selection:** one sidebar dropdown sets the default OpenRouter model for the
whole run; an "Advanced" section allows overriding the model for any single agent (e.g.
a stronger model for `risk-agent`'s synthesis, a cheaper one for `pm-agent`'s more
mechanical extraction work).

## 6. Tools & automation

- **MCP** replaces hand-written API clients for external systems: Google Drive now,
  ResMan in the future. Not used for subagent delegation itself (that's internal to
  `deepagents`'s `task` tool).
- **n8n** sits entirely outside the orchestrator's reasoning loop — it can *trigger* a
  run or *react* to one, but the orchestrator never waits on it:
  - watches the Drive `raw_docs/` folder and triggers `ingest.py` on new files
  - a scheduled (cron) trigger asks the orchestrator to review properties on a cadence
  - receives the finished report via webhook from `executive_report`-equivalent output
  - receives an escalation signal when the orchestrator needs more data (for routing to
    a property manager, e.g. via Slack)
  - sends notifications out to Slack / email / a dashboard

Both are designed as hooks in v1; no n8n workflow is actually built yet, and MCP is
used for Drive access only (not yet ResMan).

## 7. Agent harness

| Concern | v1 approach |
|---|---|
| **Model config** | Global default model + per-agent override (Section 5) |
| **Max turns** | Three distinct ceilings: orchestrator recursion limit (~50–100 agent⇄tools round-trips per question), per-subagent recursion limit (~15–25 per delegated call), conversation turn limit (Streamlit trims chat history, e.g. last ~20 messages) — the first two via `.with_config({"recursion_limit": N})`, the third is a UX/context-window concern unrelated to the agent's internal loop |
| **Tool errors** | A failed Chroma query or subagent exception returns as an error observation, not a crash — the orchestrator can retry, skip, or surface the gap to the user |
| **Timeouts** | Per subagent `task()` call, and a wall-clock ceiling on the overall run |
| **Observability** | LangSmith (keys already present in `.env`, currently unused) — traces the nested subagent calls invisible on Studio's static graph, and its token/cost view covers per-run cost tracking with no extra code |
| **Guardrails** | Every subagent's system prompt states explicitly that retrieved document text is content to analyze, never a command to follow (prompt-injection hygiene against a lease or report containing embedded instructions) |
| **Persistence** | In-memory checkpointer — sufficient for v1's single-user, single-machine scope; revisit only if this becomes multi-user or gets deployed off this machine |

## 8. Explicitly deferred (not v1)

- Multi-user access control / per-user property scoping
- Hosted/cloud deployment, persisted checkpointer, hosted Chroma
- Live ResMan API/MCP integration (manual Drive export for now)
- Built n8n workflows (hooks designed, not implemented)
- Formal evaluation harness beyond LangSmith tracing

## 9. Open questions for implementation planning

- Exact per-property pilot documents available today (rent roll, T12, work orders
  confirmed realistic; reserve studies/condition reports may need requesting)
- Concrete default model choice and per-agent override defaults
- Whether `ingest.py`'s Drive MCP walk needs pagination handling for larger folders

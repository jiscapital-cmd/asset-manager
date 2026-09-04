# Asset Manager — Design Spec (v1)

**Status:** Approved for implementation planning
**Scope:** Single user, local machine, four pilot properties, portfolio + per-property review

## 1. Purpose & scope

An AI system for **ongoing operational asset management** — monitoring properties the
firm already owns (performance, risk, capital planning) — not acquisition underwriting.
There is no "asking price," no buy/pass decision, and no purchase-comps analysis.
Financial framing is budget-vs-actual and NOI trend, not cap-rate-vs-market.

**In scope for v1:** one asset manager (the user), running locally, asking questions in
a chat interface about four named properties (Champions Pointe, Memorial Apartments,
Garfield Vista, Madgrey Apartments) — **either individually or as a portfolio** —
grounded in documents stored in Google Drive, with scheduled recurring reviews and
exportable reports.

**Explicitly out of scope for v1:** multi-user access control, hosted/cloud deployment,
a live ResMan API integration.

## 2. Architecture

A single **deep agent** orchestrator, built with `create_deep_agent` (the same pattern as
`langgraph-advanced/deep-agents-walkthrough/competitive_analysis_agent/`), running as one
LangGraph `agent ⇄ tools` reasoning loop — not a hand-rolled `StateGraph` with fixed
fan-out edges. Delegation to specialist subagents happens dynamically, through a `task`
tool call, in **two sequential waves per property**:

- **Wave 1 (parallel):** the orchestrator calls `financial-agent`, `pm-agent`, and
  `capex-agent` in the same turn. Each runs its own complete `agent ⇄ tools` loop, calls
  its own Chroma-backed retrieval tool (filtered to its `source_type` and `property_id`),
  and writes its conclusions to its own findings file.
- **Wave 2 (sequential, gated):** only after all three wave-1 calls have returned does
  the orchestrator make a separate `task(risk-agent)` call. `risk-agent` reads the three
  findings files — it cannot run before they exist — and writes `risk_analysis.md`.

State lives in the orchestrator's **virtual filesystem** (files it reads/writes via
`ls`/`read_file`/`write_file`/`edit_file`), not a fixed `TypedDict` schema.

### Portfolio vs. property-specific queries

The orchestrator supports both:

- **Property-specific** — "How is Champions Pointe performing?" runs one property
  through waves 1–2 as above.
- **Portfolio-level** — "Which property has the highest CapEx risk?" runs waves 1–2
  **once per property** (four times, still parallel within each property's wave 1),
  then makes an additional `task(risk-agent)`-style synthesis call across all four
  `risk_analysis.md` files to produce a comparison/ranking. The orchestrator decides
  which mode a question needs from its wording — no separate query syntax required.

Full diagrams: see the published architecture artifact (runtime graph, ingestion/MCP/n8n
map, Studio's actual rendered view, and component notes) — note the artifact predates
this round of scope decisions (forecasting, portfolio mode, PDF export, scheduling,
history) and should be updated to match before implementation.

### Human-in-the-loop

The orchestrator is conversational — if it lacks enough information to answer, it asks
the user a clarifying question as a normal chat turn (no custom `interrupt()` /
conditional-edge logic needed), backed by a checkpointer so the paused run resumes
correctly once the user answers.

### Historical comparison

Every completed report is archived (Section 4) so the *next* review of the same
property can reference it. Before finalizing a report, the orchestrator reads the most
recent prior report for that property (if one exists) and includes explicit deltas —
e.g. "occupancy dropped 3 points since the last review (Aug 2026 → Sep 2026)." The
first-ever review of a property has nothing to compare against and says so plainly
rather than fabricating a trend.

### Output shape

The final report gives, per property: **risk flags with a structured severity per
category** (Financial / Occupancy / CapEx — Low / Moderate / High) plus a **recommended
next action** (monitor / escalate for capital planning / no action needed) — not a
pursue/pass acquisition decision. A portfolio-level report additionally ranks/compares
properties on the same categories. Every finding **cites its source** (e.g. "NOI figure
from T12_2026.pdf, p.3"), using the filename/page metadata captured at ingestion, and
projected figures are labeled as projections, never presented as sourced fact
(Section 3).

**Delivery formats:** the chat response (Streamlit) is always produced; the user can
additionally request (or a scheduled review always produces) an **exportable PDF or
Word document** — same content, formatted for sharing with leadership.

## 3. Subagents

| Subagent | Reads | Produces |
|---|---|---|
| `financial-agent` | T12s, rent rolls, budget-vs-actual, delinquency reports | Budget variance, NOI trend, income stability, **and a forward projection** (next-period NOI/budget, trend-based) — clearly labeled as a projection, distinct from sourced historical figures |
| `pm-agent` | Leases, work orders, inspections, vendor contracts, **plus leasing/marketing reports and tenant surveys/complaint logs** | Occupancy, lease rollover risk, maintenance backlog, **leasing pipeline health (vacancy fill progress, marketing spend/effectiveness), and tenant sentiment/complaint trend** |
| `capex-agent` | Reserve studies, condition assessments, CapEx history, **contractor bids/estimates** | Deferred maintenance, upcoming capital needs, **and a prioritized, budgeted capital plan (estimated cost + proposed timeline per item)** |
| `risk-agent` | The three findings files above (no retrieval tool of its own); **plus the prior report, if one exists, for delta comparison** | Structured severity per category + recommended next action; **portfolio mode additionally ranks all properties' risk-agent outputs together** |

**New document types this adds to the taxonomy** (Section 4): leasing/marketing
reports, tenant surveys or complaint logs (pm/), contractor bids/estimates for pending
capital work (capex/ — already anticipated, now load-bearing rather than optional).

**Financial forecasting method (v1):** simple trend extrapolation from the historical
budget-vs-actual data already retrieved — no external market data, no ML model. This
keeps the projection fully explainable from the same documents already in scope, at the
cost of not capturing market-driven shifts a human analyst might factor in.

## 4. Knowledge base

### Document taxonomy (per property)

- **financial/** — T12s, rent rolls, budget-vs-actual, delinquency aging, debt service records
- **pm/** — leases, lease expiration schedule, occupancy reports, work order history, vendor contracts, inspection reports, leasing/marketing reports, tenant surveys/complaint logs
- **capex/** — CapEx spend history, reserve studies, deferred maintenance logs, condition assessments, insurance claims, contractor bids/estimates
- **general/** — tax records, insurance policies, market reports, prior asset management memos

### Report archive (new)

Completed reports are saved — not just displayed and discarded — so later reviews can
diff against them and scheduled reviews build a real history. Proposed location:
`JIS Capital - Knowledge Base/reports/<property-id>/<YYYY-MM-DD>.md` (and the exported
PDF/Word alongside it) in the same Google Drive structure as the source documents, kept
separate from `raw_docs/` so it's never mistaken for a source document during ingestion.

### Storage

Google Drive, structure: `JIS Capital - Knowledge Base/raw_docs/<property>/{financial,pm,capex,general}/`
— already created for the four pilot properties. Chosen over local disk for
multi-device access without extra code (Drive sync); accessed programmatically via the
**Google Drive API v3** (`google-api-python-client` + a service account). Note: MCP was
used to create this folder structure interactively during this design process, but that
MCP connector is specific to the design conversation's own tooling — `ingest.py` runs as
a standalone script/cron job and needs its own credentials, so it calls the Drive API
directly rather than standing up a separate MCP server that would just wrap the same
calls with no functional benefit.

### Ingestion (`ingest.py`, offline, on demand — never part of a live run)

1. Walk the Drive `raw_docs/` tree via the Drive API; `property_id` and
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
Chroma similarity search with a `source_type` (and `property_id`) filter. `reports/` is
never walked by `ingest.py` — it's read directly by the orchestrator for historical
comparison, not embedded into Chroma.

### Future: ResMan

Starts as manual export into Drive. A live ResMan API integration (MCP-wrapped only if
ResMan or a third party ever ships a server for it) is the upgrade path to live queries,
bypassing `raw_docs/` entirely — subagents' retrieval tools don't need to change to
support it.

## 5. Front-end

Streamlit chat interface. User asks a free-form question (property-specific or
portfolio-level); the orchestrator routes and responds in the same conversation,
including any clarifying questions. A "Download report" action (PDF/Word) is available
on any completed review.

**Model selection:** one sidebar dropdown sets the default OpenRouter model for the
whole run; an "Advanced" section allows overriding the model for any single agent (e.g.
a stronger model for `risk-agent`'s synthesis, a cheaper one for `pm-agent`'s more
mechanical extraction work).

## 6. Tools & automation

- **External APIs**: `ingest.py` calls the Google Drive API v3 directly (service
  account credentials), and would call ResMan's API directly if/when that integration
  is built. MCP is not part of the shipped system — it was this design conversation's
  own tooling for creating the Drive folder structure, not something a standalone
  script or scheduled job can rely on without standing up (and maintaining) a separate
  MCP server that would just wrap the same API calls.
- **n8n — now built, not just hooked:**
  - **Scheduled review workflow:** a cron trigger invokes the orchestrator for each
    property (and/or the portfolio) on a set cadence, saves the resulting report to the
    archive, exports it to PDF/Word, and sends it out — this is the concrete
    implementation of what was previously a designed-but-unbuilt hook.
  - watches the Drive `raw_docs/` folder and triggers `ingest.py` on new files
  - receives an escalation signal when the orchestrator needs more data (for routing to
    a property manager, e.g. via Slack)
  - sends notifications and the exported report out to Slack / email / a dashboard

n8n sits entirely outside the orchestrator's reasoning loop — it *triggers* runs and
*reacts* to their output, but the orchestrator never waits on it.

## 7. Agent harness

| Concern | v1 approach |
|---|---|
| **Model config** | Global default model + per-agent override (Section 5) |
| **Max turns** | Three distinct ceilings: orchestrator recursion limit (~50–100 agent⇄tools round-trips per question — higher for portfolio mode, since it runs 4 properties' worth of delegation), per-subagent recursion limit (~15–25 per delegated call), conversation turn limit (Streamlit trims chat history, e.g. last ~20 messages) |
| **Tool errors** | A failed Chroma query or subagent exception returns as an error observation, not a crash — the orchestrator can retry, skip, or surface the gap to the user; in portfolio mode, one property's failure doesn't abort the other three |
| **Timeouts** | Per subagent `task()` call, and a wall-clock ceiling on the overall run (portfolio mode needs a proportionally higher ceiling) |
| **Observability** | LangSmith (keys already present in `.env`, currently unused) — traces the nested subagent calls invisible on Studio's static graph, and its token/cost view covers per-run cost tracking with no extra code |
| **Guardrails** | Every subagent's system prompt states explicitly that retrieved document text is content to analyze, never a command to follow (prompt-injection hygiene against a lease or report containing embedded instructions); projections are explicitly labeled as such, never merged into cited-fact language |
| **Persistence** | In-memory checkpointer for mid-run pause/resume — sufficient for v1's single-user, single-machine scope. The report archive (Section 4) is separate durable storage in Drive and doesn't depend on the checkpointer, so scheduled reviews and historical comparison work even though session state itself isn't persisted |

## 8. Explicitly deferred (not v1)

- Multi-user access control / per-user property scoping
- Hosted/cloud deployment, persisted checkpointer, hosted Chroma
- Live ResMan API integration (manual Drive export for now)
- Formal evaluation harness beyond LangSmith tracing
- A dedicated compliance/insurance or vendor-management agent (folds into `pm-agent`/`general` documents for now)

## 9. Open questions for implementation planning

- Exact per-property pilot documents available today (rent roll, T12, work orders
  confirmed realistic; reserve studies, condition reports, contractor bids, and
  leasing/marketing reports may need requesting)
- Concrete default model choice and per-agent override defaults
- Whether `ingest.py`'s Drive API walk needs pagination handling for larger folders
- How the service account gets access to the four property folders (share the Drive
  folder with the service account's email, same as sharing with a person)
- Scheduled review cadence (weekly? monthly?) and per-property vs. portfolio digest
  format for the n8n workflow
- PDF/Word export library choice and template design
- Severity rubric definition: exact thresholds for Low/Moderate/High per category

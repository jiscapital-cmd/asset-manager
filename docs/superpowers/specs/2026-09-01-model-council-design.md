# Model Council — Design Spec

Date: 2026-09-01
Status: Approved for implementation

## Purpose

A Streamlit app where a user submits a query, multiple "drafter" LLMs
answer it independently, and a judge LLM from a different lab evaluates
the anonymized responses and declares a verdict. All models are called
through a single unified router (OpenRouter) and are swappable at
runtime via a config panel. Lives in `claude/` alongside the other AI
Accelerator exercises.

## Scope

- Single-page Streamlit app, one file: `claude/council_app.py`
- Three drafter models + one judge model, default roster below, each
  seat swappable at runtime from a dropdown
- All calls go through OpenRouter's OpenAI-compatible API (one client,
  one API key) — no per-provider SDKs
- Manual run-throughs for testing (no pytest suite) — matches this repo's
  existing exercise pattern

## Models (default roster)

Three drafters from three different labs; judge from a fourth so it
never grades its own work:

| Seat | Model ID (OpenRouter) |
|------|------------------------|
| Drafter 1 | `anthropic/claude-sonnet-5` |
| Drafter 2 | `openai/gpt-5.4` |
| Drafter 3 | `google/gemini-3.1-pro-preview` |
| Judge | `x-ai/grok-4.6` |

These are defaults, not hardcoded — each seat's model is swappable at
runtime (see Config panel below). Defaults are constants at the top of
`council_app.py`.

## Config

- API key read from `.env` via `python-dotenv`: `OPENROUTER_API_KEY`
  (single key for all four seats).
- `.env` currently exists but is empty — user must populate it before
  running.
- New dependencies to add to `pyproject.toml`: `openai` (used as the
  OpenRouter client — OpenRouter is OpenAI-API-compatible, so the
  existing `openai` SDK is pointed at `https://openrouter.ai/api/v1`
  instead of OpenAI's endpoint), `python-dotenv` (`streamlit` already
  present; no separate `anthropic` or `google` SDKs needed).

### Model catalog + swap panel

- On app load, fetch the available model list once from OpenRouter's
  `GET /api/v1/models` endpoint and cache it in `st.session_state` (or
  `st.cache_data`) for the session.
- A collapsible sidebar panel (`st.sidebar.expander("Model roster")`)
  shows four `st.selectbox` widgets — one per seat (Drafter 1/2/3,
  Judge) — each defaulting to that seat's default model ID from the
  table above, populated from the fetched catalog.
- If the catalog fetch fails (network error, bad key), fall back to a
  static list containing just the four default model IDs so the app is
  still usable — show a small warning in the panel noting the live
  catalog couldn't be loaded.
- Selected model IDs are read from `st.session_state` at run time; no
  need to persist selections across sessions.

## Architecture

Three layers in the single file:

### 1. Drafters layer

One wrapper function, parameterized by model ID, used for all three
drafter seats:

```python
def call_drafter(model: str, query: str) -> DrafterResult
```

`DrafterResult` is a small dataclass/namedtuple: `model_name: str`,
`response_text: str | None`, `error: str | None`.

All three drafter calls are invoked concurrently via
`concurrent.futures.ThreadPoolExecutor` (max_workers=3) so they run in
parallel instead of sequentially. Each calls the shared OpenRouter
client (`openai.OpenAI(base_url="https://openrouter.ai/api/v1",
api_key=OPENROUTER_API_KEY)`) with `model=<selected model ID>`.

### 2. Judge layer

```python
def call_judge(model: str, query: str, anonymized: list[tuple[str, str]]) -> JudgeResult
```

- `anonymized` is a list of `(label, response_text)` pairs, e.g.
  `[("Response A", "..."), ("Response B", "..."), ("Response C", "...")]`
  — one entry per drafter that succeeded.
- Before calling the judge, the successful drafter responses are
  shuffled (`random.shuffle`) and assigned labels "Response A" /
  "Response B" / "Response C" in that shuffled order. The
  label→real-model-name mapping is kept locally in the app (never sent
  to the judge).
- The judge is called through the same OpenRouter client, using the
  judge seat's selected model ID, with a prompt containing the original
  query and all labeled responses, asking it to: briefly critique each
  response, score them, and declare a winner with reasoning.
- `JudgeResult`: `verdict_text: str | None`, `error: str | None`.
  Parsing is kept simple — the judge's full text response is shown as-is
  rather than parsed into structured fields, to avoid brittle output
  parsing.

### 3. UI layer (Streamlit)

- Sidebar: the model roster swap panel described in Config above.
- Main area: text input (or `st.text_area`) for the query, plus a "Run
  Council" button.
- On click:
  1. Show a spinner while all three drafters run concurrently, using
     whatever model IDs are currently selected in the sidebar.
  2. Display each drafter's raw response in its own column (three
     columns), labeled with its real model name (not anonymized — this
     is for the user, not the judge). Any drafter error is shown inline
     in its column instead of a response.
  3. If at least one drafter succeeded, run the judge step (spinner)
     using the selected judge model, then display the judge's verdict
     text in a panel below the columns.
  4. After the verdict is shown, reveal the label→model mapping (e.g. a
     caption: "Response A = openai/gpt-5.4, Response B =
     anthropic/claude-sonnet-5, Response C = google/gemini-3.1-pro-preview")
     so the user can connect the judge's commentary back to real models.
- If all three drafters fail, skip the judge step entirely and show an
  error state instead ("No responses available to judge").

## Data flow

```
app load
  → fetch model catalog from GET /api/v1/models (cached; fallback to
    static default list on failure)
  → sidebar shows 4 selectboxes (Drafter 1/2/3, Judge), defaults per
    roster table

user query + Run Council
  → [ThreadPoolExecutor] call_drafter(seat1_model, query)
                       ‖ call_drafter(seat2_model, query)
                       ‖ call_drafter(seat3_model, query)
  → collect DrafterResult for each
  → filter to successful results
  → shuffle + label as Response A/B/C (mapping kept locally)
  → call_judge(judge_model, query, labeled responses)
  → display: drafter panels (real names) + judge verdict + reveal mapping
```

## Error handling

- A single drafter failing (bad key, timeout, rate limit, unavailable
  model) does not stop the run — its panel shows the error message, and
  judging proceeds with whatever succeeded.
- If the judge call itself fails, show the raw drafter responses with a
  "judge unavailable" notice instead of crashing the app.
- If the model catalog fetch fails, fall back to the static default list
  (see Config) rather than blocking app load.
- All API calls wrapped in try/except at the wrapper-function level so
  exceptions never propagate to break the Streamlit render.

## Testing

No automated test suite — this is a small exercise app, consistent with
the rest of the repo. Verification is manual: run the app, confirm the
sidebar roster panel loads with the four defaults, submit a query,
confirm all three drafter panels render (including a simulated error
case, e.g. temporarily bad API key), confirm the judge verdict and
mapping reveal render correctly, and confirm swapping a seat's model in
the sidebar changes which model is called on the next run.

## Out of scope (for this iteration)

- More than three drafters or more than one judge
- Persisting past runs/history or roster selections across sessions
- Structured/parsed judge output (scores as numbers, etc.)
- Formal anti-groupthink measures beyond anonymization (e.g. independent
  prompt phrasing per drafter, multi-round deliberation)

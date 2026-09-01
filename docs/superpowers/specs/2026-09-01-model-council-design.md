# Model Council — Design Spec

Date: 2026-09-01
Status: Approved for implementation

## Purpose

A Streamlit app where a user submits a query, multiple "contestant" LLMs
answer it independently, and a fixed "judge" LLM evaluates the anonymized
responses and declares a verdict. Lives in `claude/` alongside the other
AI Accelerator exercises.

## Scope

- Single-page Streamlit app, one file: `claude/council_app.py`
- Two contestant models, one fixed judge model (see Models below)
- Manual run-throughs for testing (no pytest suite) — matches this repo's
  existing exercise pattern

## Models

| Role | Provider | Model ID |
|------|----------|----------|
| Contestant A | OpenAI | `gpt-4o-mini` |
| Contestant B | Anthropic | `claude-fable-5` |
| Judge | Anthropic | `claude-opus-5` |

Model IDs are constants at the top of `council_app.py` so they can be
swapped later without touching the rest of the code.

## Config

- API keys read from `.env` via `python-dotenv`:
  - `OPENAI_API_KEY`
  - `ANTHROPIC_API_KEY`
- `.env` currently exists but is empty — user must populate it before
  running.
- New dependencies to add to `pyproject.toml`: `anthropic`,
  `python-dotenv` (`openai` and `streamlit` are already present).

## Architecture

Three layers in the single file:

### 1. Contestants layer

Two thin wrapper functions, one per provider:

```python
def call_openai(model: str, query: str) -> ContestantResult
def call_anthropic(model: str, query: str) -> ContestantResult
```

`ContestantResult` is a small dataclass/namedtuple: `model_name: str`,
`response_text: str | None`, `error: str | None`.

Both are invoked concurrently via `concurrent.futures.ThreadPoolExecutor`
(max_workers=2) so the two API calls run in parallel instead of
sequentially.

### 2. Judge layer

```python
def call_judge(query: str, anonymized: list[tuple[str, str]]) -> JudgeResult
```

- `anonymized` is a list of `(label, response_text)` pairs, e.g.
  `[("Response A", "..."), ("Response B", "...")]`.
- Before calling the judge, the two successful contestant responses are
  shuffled (`random.shuffle`) and assigned labels "Response A" /
  "Response B" in that shuffled order. The label→real-model-name mapping
  is kept locally in the app (never sent to the judge).
- The judge is called via the Anthropic SDK (`claude-opus-5`) with a
  prompt containing the original query and both labeled responses, asking
  it to: briefly critique each response, score them, and declare a
  winner with reasoning.
- `JudgeResult`: `verdict_text: str | None`, `error: str | None`. Parsing
  is kept simple — the judge's full text response is shown as-is rather
  than parsed into structured fields, to avoid brittle output parsing.

### 3. UI layer (Streamlit)

- Text input (or `st.text_area`) for the query, plus a "Run Council"
  button.
- On click:
  1. Show a spinner while contestants run concurrently.
  2. Display each contestant's raw response in its own column, labeled
     with its real model name (not anonymized — this is for the user,
     not the judge). Any contestant error is shown inline in its column
     instead of a response.
  3. If at least one contestant succeeded, run the judge step (spinner),
     then display the judge's verdict text in a panel below the columns.
  4. After the verdict is shown, reveal the label→model mapping (e.g. a
     caption: "Response A = gpt-4o-mini, Response B = claude-fable-5") so
     the user can connect the judge's commentary back to real models.
- If both contestants fail, skip the judge step entirely and show an
  error state instead ("No responses available to judge").

## Data flow

```
user query
  → [ThreadPoolExecutor] call_openai(query) ‖ call_anthropic(query)
  → collect ContestantResult for each
  → filter to successful results
  → shuffle + label as Response A/B (mapping kept locally)
  → call_judge(query, labeled responses)
  → display: contestant panels (real names) + judge verdict + reveal mapping
```

## Error handling

- A single contestant failing (bad key, timeout, rate limit, etc.) does
  not stop the run — its panel shows the error message, and judging
  proceeds with whatever succeeded.
- If the judge call itself fails, show the raw contestant responses with
  a "judge unavailable" notice instead of crashing the app.
- All API calls wrapped in try/except at the wrapper-function level so
  exceptions never propagate to break the Streamlit render.

## Testing

No automated test suite — this is a small exercise app, consistent with
the rest of the repo. Verification is manual: run the app, submit a
query, confirm both contestant panels render (including a simulated
error case, e.g. temporarily bad API key), confirm the judge verdict and
mapping reveal render correctly.

## Out of scope (for this iteration)

- User-selectable models or judge (fixed per spec)
- More than two contestants
- Persisting past runs/history
- Structured/parsed judge output (scores as numbers, etc.)

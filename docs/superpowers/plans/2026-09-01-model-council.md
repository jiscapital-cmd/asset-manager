# Model Council Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Streamlit app where a user's query is answered by three drafter LLMs (each from a different lab) called through OpenRouter, and a judge LLM from a fourth lab evaluates anonymized drafter responses and declares a verdict — with all four seats swappable at runtime from a sidebar panel.

**Architecture:** Single file `claude/council_app.py` with three layers: a drafters layer (one parameterized OpenRouter call function, run concurrently via `ThreadPoolExecutor`), a judge layer (one OpenRouter call function taking shuffled/anonymized responses), and a Streamlit UI layer (sidebar model-swap panel + query input + result columns + verdict panel). All four seats call the same OpenRouter client, differing only by `model=` string.

**Tech Stack:** Python 3.12, `uv`-managed project, Streamlit, `openai` SDK (pointed at OpenRouter's OpenAI-compatible endpoint), `python-dotenv`, `concurrent.futures`.

**Spec:** `docs/superpowers/specs/2026-09-01-model-council-design.md`

## Global Constraints

- Single file: `claude/council_app.py` — no separate modules for this iteration.
- All model calls go through OpenRouter (`base_url="https://openrouter.ai/api/v1"`) using the `openai` SDK — no per-provider SDKs (no `anthropic`, no `google-generativeai`).
- Single API key: `OPENROUTER_API_KEY`, read from `.env` via `python-dotenv`.
- Default roster (constants at top of file):
  - Drafter 1: `anthropic/claude-sonnet-5`
  - Drafter 2: `openai/gpt-5.4`
  - Drafter 3: `google/gemini-3.1-pro-preview`
  - Judge: `x-ai/grok-4.6`
- No automated test suite — manual run-throughs only, per spec.
- No persistence of history or roster selections across sessions.

---

### Task 1: Project dependencies and env scaffolding

**Files:**
- Modify: `pyproject.toml` (add `python-dotenv`; `openai` and `streamlit` already present)
- Modify: `.env` (add `OPENROUTER_API_KEY=` placeholder line, if not already present — do not overwrite any existing content)

**Interfaces:**
- Produces: `OPENROUTER_API_KEY` env var available to later tasks via `python-dotenv`'s `load_dotenv()`.

- [ ] **Step 1: Add `python-dotenv` dependency**

Run from `c:\Users\sande\AI Accelerator`:

```bash
uv add python-dotenv
```

This updates `pyproject.toml` and `uv.lock`.

- [ ] **Step 2: Confirm `openai` and `streamlit` are already present**

Run:

```bash
uv run python -c "import openai, streamlit; print(openai.__version__, streamlit.__version__)"
```

Expected: both versions print without `ImportError`.

- [ ] **Step 3: Add the API key placeholder to `.env`**

Open `.env` at `c:\Users\sande\AI Accelerator\claude\.env` (currently empty) and add:

```
OPENROUTER_API_KEY=
```

Tell the user to fill in their real key before running the app — do not commit a real key.

- [ ] **Step 4: Verify `.env` is gitignored**

Run:

```bash
git check-ignore -v claude/.env
```

Expected: it prints a match (from the existing `.gitignore`). If it does NOT match, add `.env` to `.gitignore` before continuing — a real key must never be committed.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock .gitignore
git commit -m "Add python-dotenv dependency for model council app

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

(`.env` itself is gitignored and should NOT be committed.)

---

### Task 2: Drafter and judge call functions (no UI yet)

**Files:**
- Create: `claude/council_app.py`

**Interfaces:**
- Consumes: `OPENROUTER_API_KEY` from env (Task 1).
- Produces:
  - `DrafterResult` — dataclass with fields `model_name: str`, `response_text: str | None`, `error: str | None`
  - `JudgeResult` — dataclass with fields `verdict_text: str | None`, `error: str | None`
  - `call_drafter(model: str, query: str) -> DrafterResult`
  - `call_judge(model: str, query: str, anonymized: list[tuple[str, str]]) -> JudgeResult`
  - `get_client() -> openai.OpenAI` — returns a client configured for OpenRouter
  - Constants: `DEFAULT_DRAFTER_1`, `DEFAULT_DRAFTER_2`, `DEFAULT_DRAFTER_3`, `DEFAULT_JUDGE` (the model ID strings from Global Constraints)

This task has no automated tests (no pytest suite per spec) — verification is a manual smoke script run from the command line, checked in Step 4 below.

- [ ] **Step 1: Write the core module with client, dataclasses, and call functions**

```python
"""Model Council — query multiple LLMs via OpenRouter and have a judge model rank them."""

import os
import random
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

DEFAULT_DRAFTER_1 = "anthropic/claude-sonnet-5"
DEFAULT_DRAFTER_2 = "openai/gpt-5.4"
DEFAULT_DRAFTER_3 = "google/gemini-3.1-pro-preview"
DEFAULT_JUDGE = "x-ai/grok-4.6"


@dataclass
class DrafterResult:
    model_name: str
    response_text: str | None
    error: str | None


@dataclass
class JudgeResult:
    verdict_text: str | None
    error: str | None


def get_client() -> OpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    return OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)


def call_drafter(model: str, query: str) -> DrafterResult:
    try:
        client = get_client()
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": query}],
        )
        text = response.choices[0].message.content
        return DrafterResult(model_name=model, response_text=text, error=None)
    except Exception as exc:  # noqa: BLE001 - surface any provider/network error to the UI
        return DrafterResult(model_name=model, response_text=None, error=str(exc))


def build_judge_prompt(query: str, anonymized: list[tuple[str, str]]) -> str:
    parts = [
        "You are judging responses from multiple AI models to the same user query.",
        "Briefly critique each response, then declare a winner with reasoning.",
        "",
        f"User query: {query}",
        "",
    ]
    for label, text in anonymized:
        parts.append(f"{label}:\n{text}\n")
    return "\n".join(parts)


def call_judge(model: str, query: str, anonymized: list[tuple[str, str]]) -> JudgeResult:
    try:
        client = get_client()
        prompt = build_judge_prompt(query, anonymized)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content
        return JudgeResult(verdict_text=text, error=None)
    except Exception as exc:  # noqa: BLE001
        return JudgeResult(verdict_text=None, error=str(exc))


def anonymize_results(results: list[DrafterResult]) -> tuple[list[tuple[str, str]], dict[str, str]]:
    """Shuffle successful results and label them Response A/B/C.

    Returns (labeled list for the judge prompt, label -> model_name mapping for later reveal).
    """
    successful = [r for r in results if r.response_text is not None]
    shuffled = successful[:]
    random.shuffle(shuffled)
    labels = [f"Response {chr(ord('A') + i)}" for i in range(len(shuffled))]
    labeled = [(label, r.response_text) for label, r in zip(labels, shuffled)]
    mapping = {label: r.model_name for label, r in zip(labels, shuffled)}
    return labeled, mapping
```

- [ ] **Step 2: Verify the module imports cleanly**

Run from `c:\Users\sande\AI Accelerator`:

```bash
uv run python -c "import sys; sys.path.insert(0, 'claude'); import council_app; print('ok')"
```

Expected: prints `ok` with no import errors.

- [ ] **Step 3: Manual smoke test of `anonymize_results` (pure function, no API needed)**

Run:

```bash
uv run python -c "
import sys; sys.path.insert(0, 'claude')
from council_app import DrafterResult, anonymize_results
results = [
    DrafterResult('modelA', 'text A', None),
    DrafterResult('modelB', 'text B', None),
    DrafterResult('modelC', None, 'boom'),
]
labeled, mapping = anonymize_results(results)
assert len(labeled) == 2, labeled
assert len(mapping) == 2, mapping
assert set(mapping.values()) == {'modelA', 'modelB'}
print('anonymize_results ok:', labeled, mapping)
"
```

Expected: prints `anonymize_results ok: ...` with no `AssertionError`.

- [ ] **Step 4: Manual smoke test of `call_drafter` against the real API (requires a real key in `.env`)**

Ask the user to confirm they've put a real `OPENROUTER_API_KEY` in `claude/.env` before running this step. Then run:

```bash
uv run python -c "
import sys; sys.path.insert(0, 'claude')
from council_app import call_drafter, DEFAULT_DRAFTER_1
result = call_drafter(DEFAULT_DRAFTER_1, 'Say hello in one word.')
print(result)
"
```

Expected: `DrafterResult` printed with `response_text` set and `error=None`. If `error` is set (e.g. missing/invalid key), report it to the user and pause — do not proceed until this succeeds, since later tasks depend on real API access working.

- [ ] **Step 5: Commit**

```bash
git add claude/council_app.py
git commit -m "Add drafter/judge call functions for model council

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Model catalog fetch with fallback

**Files:**
- Modify: `claude/council_app.py`

**Interfaces:**
- Consumes: `get_client()` from Task 2.
- Produces: `fetch_model_catalog() -> list[str]` — returns a list of model ID strings; falls back to the four default IDs on any failure.

- [ ] **Step 1: Add the catalog fetch function**

Add to `claude/council_app.py` (after `get_client`):

```python
def fetch_model_catalog() -> list[str]:
    """Fetch available model IDs from OpenRouter; fall back to defaults on failure."""
    fallback = [DEFAULT_DRAFTER_1, DEFAULT_DRAFTER_2, DEFAULT_DRAFTER_3, DEFAULT_JUDGE]
    try:
        client = get_client()
        models = client.models.list()
        ids = [m.id for m in models.data]
        return ids if ids else fallback
    except Exception:  # noqa: BLE001 - any failure falls back to the static default list
        return fallback
```

- [ ] **Step 2: Manual smoke test with real API access**

Run:

```bash
uv run python -c "
import sys; sys.path.insert(0, 'claude')
from council_app import fetch_model_catalog, DEFAULT_DRAFTER_1
catalog = fetch_model_catalog()
print(len(catalog), 'models found')
print(DEFAULT_DRAFTER_1 in catalog)
"
```

Expected: prints a count greater than 0, and `True` for the default drafter being in the list (OpenRouter's catalog should include it). If `False`, that's OK for this smoke test — the UI falls back to defaults if a selection isn't in the catalog (handled in Task 4) — but note it for the user.

- [ ] **Step 3: Manual smoke test of the fallback path (simulate failure)**

Run:

```bash
uv run python -c "
import sys; sys.path.insert(0, 'claude')
import council_app
council_app.OPENROUTER_BASE_URL = 'https://invalid.invalid/api/v1'
catalog = council_app.fetch_model_catalog()
print(catalog)
assert catalog == [
    council_app.DEFAULT_DRAFTER_1,
    council_app.DEFAULT_DRAFTER_2,
    council_app.DEFAULT_DRAFTER_3,
    council_app.DEFAULT_JUDGE,
]
print('fallback ok')
"
```

Expected: prints the fallback list and `fallback ok` with no `AssertionError`.

- [ ] **Step 4: Commit**

```bash
git add claude/council_app.py
git commit -m "Add model catalog fetch with static fallback

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Streamlit UI — sidebar roster panel, query input, drafter panels, judge verdict

**Files:**
- Modify: `claude/council_app.py`

**Interfaces:**
- Consumes: `DEFAULT_DRAFTER_1/2/3`, `DEFAULT_JUDGE`, `fetch_model_catalog`, `call_drafter`, `call_judge`, `anonymize_results`, `DrafterResult`, `JudgeResult` (all from Tasks 2–3).
- Produces: a `main()` function that renders the full app, called under `if __name__ == "__main__": main()`.

- [ ] **Step 1: Add the Streamlit UI code**

Add to the bottom of `claude/council_app.py`:

```python
from concurrent.futures import ThreadPoolExecutor

import streamlit as st


def render_sidebar(catalog: list[str]) -> dict[str, str]:
    st.sidebar.header("Model roster")
    with st.sidebar.expander("Model roster", expanded=True):
        seats = {
            "Drafter 1": DEFAULT_DRAFTER_1,
            "Drafter 2": DEFAULT_DRAFTER_2,
            "Drafter 3": DEFAULT_DRAFTER_3,
            "Judge": DEFAULT_JUDGE,
        }
        selections = {}
        for seat_name, default_model in seats.items():
            options = catalog if default_model in catalog else [default_model] + catalog
            selections[seat_name] = st.selectbox(
                seat_name, options=options, index=options.index(default_model)
            )
    return selections


def run_drafters(models: list[str], query: str) -> list[DrafterResult]:
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(call_drafter, model, query) for model in models]
        return [f.result() for f in futures]


def main() -> None:
    st.set_page_config(page_title="Model Council", layout="wide")
    st.title("Model Council")
    st.caption(
        "Three drafter models answer independently; a judge model from a "
        "different lab evaluates anonymized responses and picks a winner."
    )

    if "model_catalog" not in st.session_state:
        with st.spinner("Loading model catalog..."):
            catalog = fetch_model_catalog()
        st.session_state["model_catalog"] = catalog
        if catalog == [DEFAULT_DRAFTER_1, DEFAULT_DRAFTER_2, DEFAULT_DRAFTER_3, DEFAULT_JUDGE]:
            st.sidebar.warning("Live model catalog unavailable — showing defaults only.")

    selections = render_sidebar(st.session_state["model_catalog"])

    query = st.text_area("Your query", height=100)
    run_clicked = st.button("Run Council", type="primary")

    if run_clicked and query.strip():
        drafter_models = [selections["Drafter 1"], selections["Drafter 2"], selections["Drafter 3"]]
        with st.spinner("Running drafters..."):
            results = run_drafters(drafter_models, query)

        cols = st.columns(3)
        for col, result in zip(cols, results):
            with col:
                st.subheader(result.model_name)
                if result.error:
                    st.error(result.error)
                else:
                    st.write(result.response_text)

        labeled, mapping = anonymize_results(results)
        if not labeled:
            st.error("No responses available to judge.")
            return

        with st.spinner("Running judge..."):
            judge_result = call_judge(selections["Judge"], query, labeled)

        st.subheader("Judge verdict")
        if judge_result.error:
            st.warning(f"Judge unavailable: {judge_result.error}")
        else:
            st.write(judge_result.verdict_text)
            mapping_str = ", ".join(f"{label} = {model}" for label, model in mapping.items())
            st.caption(mapping_str)
    elif run_clicked:
        st.warning("Enter a query first.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the module still imports cleanly**

Run:

```bash
uv run python -c "import sys; sys.path.insert(0, 'claude'); import council_app; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 3: Launch the app and manually verify**

Run:

```bash
cd claude
uv run streamlit run council_app.py
```

In the browser that opens:
1. Confirm the sidebar "Model roster" panel shows four selectboxes defaulted to the roster in Global Constraints.
2. Enter a query (e.g. "What is the capital of France?") and click "Run Council".
3. Confirm three columns render, each with a model name header and a response (or an error if a model is unavailable).
4. Confirm a "Judge verdict" section renders below with verdict text and a caption revealing the label→model mapping.
5. Swap one seat's model in the sidebar (e.g. change Drafter 1), click "Run Council" again, and confirm that column's header shows the newly selected model.
6. Stop the app (Ctrl+C in the terminal) once verified.

- [ ] **Step 4: Manually verify the error path**

Temporarily set an invalid value for `OPENROUTER_API_KEY` in `claude/.env` (e.g. append `x` to it), rerun the app, click "Run Council", and confirm each drafter column shows an error message instead of crashing the app, and that either a "No responses available to judge" error or a "Judge unavailable" warning is shown instead of a Python traceback. Restore the correct API key in `.env` afterward.

- [ ] **Step 5: Commit**

```bash
git add claude/council_app.py
git commit -m "Add Streamlit UI for model council app

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-Review Notes

- **Spec coverage:** Purpose/Scope → Task 4 (full app); Models/default roster → constants in Task 2; Config (API key, deps) → Task 1; Model catalog + swap panel → Task 3 (fetch) and Task 4 (sidebar UI); Architecture (drafters layer, judge layer, UI layer) → Tasks 2–4 respectively; Data flow → implemented end-to-end in Task 4's `main()`; Error handling (drafter failure, judge failure, catalog fetch failure) → covered in Tasks 2–4 with manual verification in Task 4 Step 4; Testing → manual run-throughs specified in each task's steps; Out of scope items are correctly not implemented.
- **Placeholder scan:** no TBD/TODO markers; all steps contain full runnable code or exact commands.
- **Type consistency:** `DrafterResult`, `JudgeResult`, `call_drafter`, `call_judge`, `anonymize_results`, `fetch_model_catalog`, `get_client`, and the `DEFAULT_*` constants are defined once in Tasks 2–3 and consumed with matching names/signatures in Task 4.

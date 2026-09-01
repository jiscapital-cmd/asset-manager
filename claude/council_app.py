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


from concurrent.futures import ThreadPoolExecutor

import streamlit as st


AGORA_CSS = """
<style>
:root {
    --agora-bg: #0b0c0f;
    --agora-panel: #16181d;
    --agora-border: #2a2d34;
    --agora-text: #e8e9ec;
    --agora-muted: #9098a3;
    --agora-accent: #6ee7b7;
}

html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
}

[data-testid="stAppViewContainer"], [data-testid="stHeader"] {
    background-color: var(--agora-bg);
    color: var(--agora-text);
}

[data-testid="stSidebar"] {
    background-color: var(--agora-panel);
    border-right: 1px solid var(--agora-border);
}

h1 {
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--agora-text);
}

[data-testid="stCaptionContainer"], .stCaption, small {
    color: var(--agora-muted) !important;
}

.stButton button {
    background-color: var(--agora-accent);
    color: #0b0c0f;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    padding: 0.5rem 1.25rem;
    transition: opacity 0.15s ease;
}

.stButton button:hover {
    opacity: 0.85;
    color: #0b0c0f;
}

[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="column"] > div {
    background-color: var(--agora-panel);
    border: 1px solid var(--agora-border);
    border-radius: 10px;
    padding: 1rem;
}

[data-testid="stTextArea"] textarea {
    background-color: var(--agora-panel);
    color: var(--agora-text);
    border: 1px solid var(--agora-border);
    border-radius: 8px;
}
</style>
"""


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
    st.markdown(AGORA_CSS, unsafe_allow_html=True)
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

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

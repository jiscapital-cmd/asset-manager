"""Picks the actual final report out of an orchestrator invocation's message
list.

Observed in practice: the orchestrator sometimes sends one more short
wrap-up message after the real report (e.g. "the report has been saved and
archived"), so `messages[-1].content` is not reliably the report — it's
whichever of the two the model happened to say last. The longest AIMessage
in the list is reliably the actual report; a one-line confirmation is never
it.
"""

from langchain_core.messages import AIMessage


def extract_final_report(messages: list) -> str:
    ai_contents = [
        message.content
        for message in messages
        if isinstance(message, AIMessage) and isinstance(message.content, str) and message.content
    ]
    if not ai_contents:
        return messages[-1].content if messages else ""
    return max(ai_contents, key=len)

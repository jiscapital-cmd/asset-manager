from langchain_core.messages import AIMessage, ToolMessage

from asset_manager.agents.report_extraction import extract_final_report


def test_extract_final_report_returns_the_only_ai_message():
    messages = [AIMessage(content="# Report\nAll good.")]
    assert extract_final_report(messages) == "# Report\nAll good."


def test_extract_final_report_picks_the_longest_ai_message_not_the_last():
    """Regression: the orchestrator sometimes sends a short wrap-up message
    (e.g. "the report has been saved") right after the real report — the
    LAST message is not reliably the report itself."""
    report = "# Asset Management Review\n" + ("Detailed findings. " * 50)
    messages = [
        AIMessage(content="", tool_calls=[{"name": "save_report", "args": {}, "id": "1"}]),
        ToolMessage(content="Saved report for garfield_vista dated 2026-09-22.", tool_call_id="1"),
        AIMessage(content=report),
        AIMessage(content="The Asset Management Review has been successfully completed and archived."),
    ]
    assert extract_final_report(messages) == report


def test_extract_final_report_ignores_empty_content_tool_call_messages():
    messages = [
        AIMessage(content="", tool_calls=[{"name": "list_properties", "args": {}, "id": "1"}]),
        ToolMessage(content="Available properties: garfield_vista", tool_call_id="1"),
        AIMessage(content="# Report\nReal content here."),
    ]
    assert extract_final_report(messages) == "# Report\nReal content here."


def test_extract_final_report_ignores_non_ai_messages():
    messages = [
        ToolMessage(content="some tool output that happens to be very long " * 10, tool_call_id="1"),
        AIMessage(content="# Report\nShort but the actual answer."),
    ]
    assert extract_final_report(messages) == "# Report\nShort but the actual answer."


def test_extract_final_report_falls_back_to_last_message_when_no_ai_content():
    messages = [ToolMessage(content="only a tool message", tool_call_id="1")]
    assert extract_final_report(messages) == "only a tool message"


def test_extract_final_report_returns_empty_string_for_empty_list():
    assert extract_final_report([]) == ""

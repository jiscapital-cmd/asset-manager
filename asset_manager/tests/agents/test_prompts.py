from asset_manager.agents.prompts import ORCHESTRATOR_PROMPT


def test_orchestrator_prompt_requires_preserving_citations_in_final_report():
    lowered = ORCHESTRATOR_PROMPT.lower()
    assert "citation" in lowered
    assert "save_report" in lowered


def test_orchestrator_prompt_forbids_a_confirmation_in_place_of_the_report():
    lowered = ORCHESTRATOR_PROMPT.lower()
    assert "final response" in lowered or "final message" in lowered
    assert "confirmation" in lowered

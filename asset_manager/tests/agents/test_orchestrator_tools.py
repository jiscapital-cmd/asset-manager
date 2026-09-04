from asset_manager.agents.orchestrator_tools import (
    make_get_prior_report_tool,
    make_list_properties_tool,
    make_save_report_tool,
)


def test_list_properties_tool_returns_configured_ids():
    tool = make_list_properties_tool(["champions-pointe", "memorial-apartments"])
    result = tool.invoke({})
    assert "champions-pointe" in result
    assert "memorial-apartments" in result


class FakeArchive:
    def __init__(self):
        self.saved = {}

    def save_report(self, property_id, content):
        self.saved[property_id] = content
        return "2026-09-03"

    def get_latest_report(self, property_id):
        return self.saved.get(property_id)


def test_save_report_tool_persists_and_confirms():
    archive = FakeArchive()
    tool = make_save_report_tool(archive)
    result = tool.invoke({"property_id": "champions-pointe", "content": "# Report"})
    assert archive.saved["champions-pointe"] == "# Report"
    assert "2026-09-03" in result


def test_get_prior_report_tool_returns_none_message_when_absent():
    archive = FakeArchive()
    tool = make_get_prior_report_tool(archive)
    result = tool.invoke({"property_id": "champions-pointe"})
    assert "No prior report" in result


def test_get_prior_report_tool_returns_content_when_present():
    archive = FakeArchive()
    archive.saved["champions-pointe"] = "# August report\nOccupancy 94%"
    tool = make_get_prior_report_tool(archive)
    result = tool.invoke({"property_id": "champions-pointe"})
    assert "Occupancy 94%" in result


def test_get_prior_report_tool_resolves_property_id_variant_when_known_ids_given():
    archive = FakeArchive()
    archive.saved["champions_pointe"] = "# August report\nOccupancy 94%"
    tool = make_get_prior_report_tool(archive, known_property_ids=["champions_pointe"])
    result = tool.invoke({"property_id": "Champions Pointe"})
    assert "Occupancy 94%" in result


def test_save_report_tool_resolves_property_id_variant_when_known_ids_given():
    archive = FakeArchive()
    tool = make_save_report_tool(archive, known_property_ids=["champions_pointe"])
    tool.invoke({"property_id": "Champions Pointe", "content": "# Report"})
    assert archive.saved["champions_pointe"] == "# Report"


def test_save_report_tool_leaves_unmatched_property_id_unchanged():
    archive = FakeArchive()
    tool = make_save_report_tool(archive, known_property_ids=["champions_pointe"])
    tool.invoke({"property_id": "portfolio", "content": "# Portfolio Report"})
    assert archive.saved["portfolio"] == "# Portfolio Report"

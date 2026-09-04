"""Tools available to the orchestrator itself (list_properties, save_report)
and to risk-agent specifically (get_prior_report)."""

from langchain_core.tools import tool

from asset_manager.property_ids import resolve_property_id
from asset_manager.reports.archive import ReportArchive


def make_list_properties_tool(property_ids: list[str]):
    @tool(name_or_callable="list_properties")
    def list_properties() -> str:
        """List every property_id available for review — use this for portfolio-level
        questions to know which properties to run the review pipeline against."""
        return "Available properties: " + ", ".join(property_ids)

    return list_properties


def make_save_report_tool(archive: ReportArchive, known_property_ids: list[str] | None = None):
    @tool(name_or_callable="save_report")
    def save_report(property_id: str, content: str) -> str:
        """Persist a completed report for a property to the report archive.

        Args:
            property_id: which property this report is about.
            content: the full markdown report text.
        """
        if known_property_ids:
            property_id = resolve_property_id(property_id, known_property_ids)
        date_str = archive.save_report(property_id, content)
        return f"Saved report for {property_id} dated {date_str}."

    return save_report


def make_get_prior_report_tool(archive: ReportArchive, known_property_ids: list[str] | None = None):
    @tool(name_or_callable="get_prior_report")
    def get_prior_report(property_id: str) -> str:
        """Retrieve the most recently archived report for a property, to compare
        against for a delta ("what changed since last review").

        Args:
            property_id: which property's prior report to fetch.
        """
        if known_property_ids:
            property_id = resolve_property_id(property_id, known_property_ids)
        report = archive.get_latest_report(property_id)
        if report is None:
            return f"No prior report exists for {property_id} — this is the first review."
        return report

    return get_prior_report

"""Runs a review per property on a schedule (invoked by the n8n workflow via
asset_manager.automation.api). One property's failure doesn't abort the
others (spec Section 7, "tool errors" — "in portfolio mode, one property's
failure doesn't abort the other three")."""

from dataclasses import dataclass
from typing import Callable


@dataclass
class ScheduledReviewResult:
    property_id: str
    report_text: str
    docx_bytes: bytes
    pdf_bytes: bytes


def run_scheduled_review(
    property_ids: list[str],
    run_review_fn: Callable[[str], str],
    export_docx_fn: Callable[[str, str], bytes],
    export_pdf_fn: Callable[[str, str], bytes],
    notify_fn: Callable[[str], None],
) -> list[ScheduledReviewResult]:
    results: list[ScheduledReviewResult] = []

    for property_id in property_ids:
        try:
            report_text = run_review_fn(property_id)
        except Exception as exc:
            notify_fn(f"Scheduled review for {property_id} failed: {exc}")
            continue

        docx_bytes = export_docx_fn(property_id, report_text)
        pdf_bytes = export_pdf_fn(property_id, report_text)
        results.append(
            ScheduledReviewResult(
                property_id=property_id,
                report_text=report_text,
                docx_bytes=docx_bytes,
                pdf_bytes=pdf_bytes,
            )
        )
        notify_fn(f"Scheduled review for {property_id} is ready.")

    return results

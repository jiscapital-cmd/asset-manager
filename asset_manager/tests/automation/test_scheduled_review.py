from asset_manager.automation.scheduled_review import run_scheduled_review


def test_run_scheduled_review_runs_each_property_and_notifies():
    reviewed = []
    notified = []

    def fake_run_review(property_id: str) -> str:
        reviewed.append(property_id)
        return f"# Report for {property_id}\nAll good."

    def fake_export_docx(title, content):
        return b"docx-bytes"

    def fake_export_pdf(title, content):
        return b"pdf-bytes"

    def fake_notify(message):
        notified.append(message)

    results = run_scheduled_review(
        property_ids=["champions-pointe", "memorial-apartments"],
        run_review_fn=fake_run_review,
        export_docx_fn=fake_export_docx,
        export_pdf_fn=fake_export_pdf,
        notify_fn=fake_notify,
    )

    assert reviewed == ["champions-pointe", "memorial-apartments"]
    assert len(results) == 2
    assert results[0].property_id == "champions-pointe"
    assert results[0].docx_bytes == b"docx-bytes"
    assert results[0].pdf_bytes == b"pdf-bytes"
    assert len(notified) == 2


def test_run_scheduled_review_continues_after_one_property_fails():
    def flaky_run_review(property_id: str) -> str:
        if property_id == "memorial-apartments":
            raise RuntimeError("orchestrator timed out")
        return f"# Report for {property_id}"

    notified = []
    results = run_scheduled_review(
        property_ids=["champions-pointe", "memorial-apartments", "garfield-vista"],
        run_review_fn=flaky_run_review,
        export_docx_fn=lambda t, c: b"docx",
        export_pdf_fn=lambda t, c: b"pdf",
        notify_fn=lambda m: notified.append(m),
    )

    succeeded_ids = [r.property_id for r in results]
    assert succeeded_ids == ["champions-pointe", "garfield-vista"]
    assert any("memorial-apartments" in m and "failed" in m.lower() for m in notified)

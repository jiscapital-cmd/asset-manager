from asset_manager.automation.scheduled_review import run_portfolio_review, run_scheduled_review


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


def test_run_portfolio_review_returns_result_and_notifies():
    notified = []

    def fake_run_portfolio_review() -> str:
        return "# Portfolio Review\nGarfield Vista has the highest CapEx risk."

    result = run_portfolio_review(
        run_portfolio_review_fn=fake_run_portfolio_review,
        export_docx_fn=lambda t, c: b"docx-bytes",
        export_pdf_fn=lambda t, c: b"pdf-bytes",
        notify_fn=lambda m: notified.append(m),
    )

    assert result is not None
    assert result.property_id == "portfolio"
    assert "Garfield Vista" in result.report_text
    assert result.docx_bytes == b"docx-bytes"
    assert result.pdf_bytes == b"pdf-bytes"
    assert len(notified) == 1
    assert "ready" in notified[0].lower()


def test_run_scheduled_review_sends_pdf_file_when_send_file_fn_given():
    sent_files = []

    result = run_scheduled_review(
        property_ids=["champions-pointe"],
        run_review_fn=lambda property_id: f"# Report for {property_id}",
        export_docx_fn=lambda t, c: b"docx-bytes",
        export_pdf_fn=lambda t, c: b"pdf-bytes",
        notify_fn=lambda m: None,
        send_file_fn=lambda filename, content: sent_files.append((filename, content)),
    )

    assert len(result) == 1
    assert len(sent_files) == 1
    filename, content = sent_files[0]
    assert "champions-pointe" in filename
    assert content == b"pdf-bytes"


def test_run_scheduled_review_does_not_send_file_for_failed_property():
    sent_files = []

    def flaky_run_review(property_id: str) -> str:
        raise RuntimeError("orchestrator timed out")

    run_scheduled_review(
        property_ids=["champions-pointe"],
        run_review_fn=flaky_run_review,
        export_docx_fn=lambda t, c: b"docx",
        export_pdf_fn=lambda t, c: b"pdf",
        notify_fn=lambda m: None,
        send_file_fn=lambda filename, content: sent_files.append((filename, content)),
    )

    assert sent_files == []


def test_run_portfolio_review_sends_pdf_file_when_send_file_fn_given():
    sent_files = []

    result = run_portfolio_review(
        run_portfolio_review_fn=lambda: "# Portfolio Review",
        export_docx_fn=lambda t, c: b"docx-bytes",
        export_pdf_fn=lambda t, c: b"pdf-bytes",
        notify_fn=lambda m: None,
        send_file_fn=lambda filename, content: sent_files.append((filename, content)),
    )

    assert result is not None
    assert len(sent_files) == 1
    filename, content = sent_files[0]
    assert "portfolio" in filename
    assert content == b"pdf-bytes"


def test_run_portfolio_review_returns_none_and_notifies_on_failure():
    notified = []

    def flaky_run_portfolio_review() -> str:
        raise RuntimeError("orchestrator timed out")

    result = run_portfolio_review(
        run_portfolio_review_fn=flaky_run_portfolio_review,
        export_docx_fn=lambda t, c: b"docx",
        export_pdf_fn=lambda t, c: b"pdf",
        notify_fn=lambda m: notified.append(m),
    )

    assert result is None
    assert len(notified) == 1
    assert "failed" in notified[0].lower()

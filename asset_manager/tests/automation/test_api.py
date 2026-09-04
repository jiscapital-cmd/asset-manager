from fastapi.testclient import TestClient

from asset_manager.automation.api import create_app


def _build_test_app():
    def fake_run_review(property_id: str) -> str:
        return f"# Report for {property_id}"

    return create_app(
        all_property_ids=["champions-pointe", "memorial-apartments"],
        run_review_fn=fake_run_review,
        export_docx_fn=lambda t, c: b"docx",
        export_pdf_fn=lambda t, c: b"pdf",
        notify_fn=lambda m: None,
    )


def test_health_returns_ok():
    client = TestClient(_build_test_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_run_reviews_with_explicit_property_ids():
    client = TestClient(_build_test_app())
    response = client.post("/reviews/run", json={"property_ids": ["champions-pointe"]})
    assert response.status_code == 200
    body = response.json()
    assert body["reviewed"] == ["champions-pointe"]


def test_run_reviews_defaults_to_all_configured_properties():
    client = TestClient(_build_test_app())
    response = client.post("/reviews/run", json={})
    assert response.status_code == 200
    body = response.json()
    assert sorted(body["reviewed"]) == ["champions-pointe", "memorial-apartments"]


def test_run_portfolio_review_returns_501_when_not_configured():
    client = TestClient(_build_test_app())
    response = client.post("/reviews/run-portfolio")
    assert response.status_code == 501


def test_run_portfolio_review_returns_200_when_configured():
    def fake_run_review(property_id: str) -> str:
        return f"# Report for {property_id}"

    def fake_run_portfolio_review() -> str:
        return "# Portfolio Review\nGarfield Vista has the highest CapEx risk."

    app = create_app(
        all_property_ids=["champions-pointe", "memorial-apartments"],
        run_review_fn=fake_run_review,
        export_docx_fn=lambda t, c: b"docx",
        export_pdf_fn=lambda t, c: b"pdf",
        notify_fn=lambda m: None,
        run_portfolio_review_fn=fake_run_portfolio_review,
    )
    client = TestClient(app)
    response = client.post("/reviews/run-portfolio")
    assert response.status_code == 200
    body = response.json()
    assert body["reviewed"] == ["portfolio"]


def test_run_ingest_returns_501_when_not_configured():
    client = TestClient(_build_test_app())
    response = client.post("/ingest/run")
    assert response.status_code == 501


def test_run_ingest_returns_summary_when_configured():
    from dataclasses import dataclass, field

    @dataclass
    class FakeIngestionSummary:
        files_added: int = 3
        files_updated: int = 1
        files_deleted: int = 0
        files_skipped: int = 5
        files_failed: int = 1
        failed_files: list = field(default_factory=lambda: ["bad.xyz: Unsupported file type: bad.xyz"])

    def fake_run_review(property_id: str) -> str:
        return f"# Report for {property_id}"

    def fake_run_ingest():
        return FakeIngestionSummary()

    app = create_app(
        all_property_ids=["champions-pointe"],
        run_review_fn=fake_run_review,
        export_docx_fn=lambda t, c: b"docx",
        export_pdf_fn=lambda t, c: b"pdf",
        notify_fn=lambda m: None,
        run_ingest_fn=fake_run_ingest,
    )
    client = TestClient(app)
    response = client.post("/ingest/run")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "added": 3,
        "updated": 1,
        "deleted": 0,
        "skipped": 5,
        "failed": 1,
        "failed_files": ["bad.xyz: Unsupported file type: bad.xyz"],
    }

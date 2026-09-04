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

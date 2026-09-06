import pytest

from asset_manager.ingestion.chroma_client import get_chroma_client


def test_get_chroma_client_uses_env_host_and_port(monkeypatch):
    captured = {}

    class FakeHttpClient:
        def __init__(self, host, port):
            captured["host"] = host
            captured["port"] = port

    monkeypatch.setattr("chromadb.HttpClient", FakeHttpClient)
    monkeypatch.delenv("CHROMA_API_KEY", raising=False)
    monkeypatch.setenv("CHROMA_HOST", "chroma.example.internal")
    monkeypatch.setenv("CHROMA_PORT", "9001")

    client = get_chroma_client()

    assert captured == {"host": "chroma.example.internal", "port": 9001}
    assert isinstance(client, FakeHttpClient)


def test_get_chroma_client_defaults_to_localhost_8001(monkeypatch):
    captured = {}

    class FakeHttpClient:
        def __init__(self, host, port):
            captured["host"] = host
            captured["port"] = port

    monkeypatch.setattr("chromadb.HttpClient", FakeHttpClient)
    monkeypatch.delenv("CHROMA_API_KEY", raising=False)
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    monkeypatch.delenv("CHROMA_PORT", raising=False)

    get_chroma_client()

    assert captured == {"host": "localhost", "port": 8001}


def test_get_chroma_client_uses_cloud_client_when_api_key_set(monkeypatch):
    captured = {}

    class FakeCloudClient:
        def __init__(self, tenant, database, api_key):
            captured["tenant"] = tenant
            captured["database"] = database
            captured["api_key"] = api_key

    monkeypatch.setattr("chromadb.CloudClient", FakeCloudClient)
    monkeypatch.setenv("CHROMA_API_KEY", "test-api-key")
    monkeypatch.setenv("CHROMA_TENANT", "test-tenant")
    monkeypatch.setenv("CHROMA_DATABASE", "test-database")

    client = get_chroma_client()

    assert captured == {"tenant": "test-tenant", "database": "test-database", "api_key": "test-api-key"}
    assert isinstance(client, FakeCloudClient)


def test_get_chroma_client_prefers_cloud_over_local_when_both_configured(monkeypatch):
    """CHROMA_API_KEY present means Chroma Cloud is intended — local
    CHROMA_HOST/CHROMA_PORT (if left over from a different environment's
    .env) must not silently take precedence and connect to the wrong DB."""
    local_called = []

    class FakeCloudClient:
        def __init__(self, tenant, database, api_key):
            pass

    class FakeHttpClient:
        def __init__(self, host, port):
            local_called.append((host, port))

    monkeypatch.setattr("chromadb.CloudClient", FakeCloudClient)
    monkeypatch.setattr("chromadb.HttpClient", FakeHttpClient)
    monkeypatch.setenv("CHROMA_API_KEY", "test-api-key")
    monkeypatch.setenv("CHROMA_TENANT", "test-tenant")
    monkeypatch.setenv("CHROMA_DATABASE", "test-database")
    monkeypatch.setenv("CHROMA_HOST", "localhost")
    monkeypatch.setenv("CHROMA_PORT", "8001")

    client = get_chroma_client()

    assert isinstance(client, FakeCloudClient)
    assert local_called == []

import pytest

from asset_manager.ingestion.chroma_client import get_chroma_client


def test_get_chroma_client_uses_env_host_and_port(monkeypatch):
    captured = {}

    class FakeHttpClient:
        def __init__(self, host, port):
            captured["host"] = host
            captured["port"] = port

    monkeypatch.setattr("chromadb.HttpClient", FakeHttpClient)
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
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    monkeypatch.delenv("CHROMA_PORT", raising=False)

    get_chroma_client()

    assert captured == {"host": "localhost", "port": 8001}

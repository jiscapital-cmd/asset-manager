import uuid

import chromadb

from asset_manager.ingestion.store import ChromaStore, ChunkRecord
from asset_manager.retrieval.tools import make_retrieval_tool


def fake_embed_fn(texts):
    return [[float(len(t)), 0.0] for t in texts]


def _seeded_store():
    # A unique collection name per store isolates tests from each other —
    # chromadb.EphemeralClient() shares its in-memory system cache across
    # instantiations within a process, so a fixed collection name would
    # otherwise accumulate chunks across test modules.
    store = ChromaStore(
        chromadb.EphemeralClient(), embed_fn=fake_embed_fn, collection_name=f"test-{uuid.uuid4()}"
    )
    store.upsert_chunks([
        ChunkRecord(
            id="p1:t12.pdf:3:0",
            text="NOI came in at $1.1M against a $1.15M budget.",
            property_id="p1",
            source_type="financial",
            filename="t12.pdf",
            page_or_row=3,
            file_hash="h1",
            ingested_at="2026-09-03T00:00:00Z",
        )
    ])
    return store


def test_retrieval_tool_has_source_type_specific_name():
    tool = make_retrieval_tool(_seeded_store(), source_type="financial")
    assert tool.name == "retrieve_financial_documents"


def test_retrieval_tool_returns_text_with_citation():
    tool = make_retrieval_tool(_seeded_store(), source_type="financial")
    result = tool.invoke({"query": "NOI", "property_id": "p1"})
    assert "$1.1M" in result
    assert "t12.pdf" in result
    assert "p.3" in result


def test_retrieval_tool_returns_no_results_message_when_empty():
    tool = make_retrieval_tool(_seeded_store(), source_type="capex")
    result = tool.invoke({"query": "reserve study", "property_id": "p1"})
    assert "No relevant" in result

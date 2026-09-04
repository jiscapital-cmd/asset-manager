import uuid

import chromadb
import pytest

from asset_manager.ingestion.store import ChromaStore, ChunkRecord


def fake_embed_fn(texts: list[str]) -> list[list[float]]:
    """Deterministic fake embedding: vector encodes text length + first char."""
    return [[float(len(t)), float(ord(t[0])) if t else 0.0] for t in texts]


@pytest.fixture
def store():
    # Unique collection name per test — chromadb.EphemeralClient() shares its
    # in-memory system cache across instantiations within a process, so a
    # fixed collection name would otherwise accumulate chunks across tests.
    client = chromadb.EphemeralClient()
    return ChromaStore(client, embed_fn=fake_embed_fn, collection_name=f"test-{uuid.uuid4()}")


def _record(property_id="p1", source_type="financial", filename="t12.pdf", page=1, text="NOI is $1.1M", file_hash="abc123"):
    return ChunkRecord(
        id=f"{property_id}:{filename}:{page}",
        text=text,
        property_id=property_id,
        source_type=source_type,
        filename=filename,
        page_or_row=page,
        file_hash=file_hash,
        ingested_at="2026-09-03T00:00:00Z",
    )


def test_upsert_and_query_returns_matching_chunk(store):
    store.upsert_chunks([_record()])
    results = store.query("NOI", source_type="financial", property_id="p1")
    assert len(results) == 1
    assert results[0]["filename"] == "t12.pdf"
    assert results[0]["page_or_row"] == 1


def test_query_filters_by_source_type(store):
    store.upsert_chunks([
        _record(source_type="financial", filename="t12.pdf"),
        _record(source_type="capex", filename="reserve_study.pdf"),
    ])
    results = store.query("anything", source_type="capex", property_id="p1")
    assert len(results) == 1
    assert results[0]["filename"] == "reserve_study.pdf"


def test_query_filters_by_property_id(store):
    store.upsert_chunks([
        _record(property_id="p1", filename="t12.pdf"),
        _record(property_id="p2", filename="t12.pdf"),
    ])
    results = store.query("anything", source_type="financial", property_id="p1")
    assert len(results) == 1
    assert results[0]["property_id"] == "p1"


def test_delete_by_filename_removes_only_that_files_chunks(store):
    store.upsert_chunks([
        _record(filename="t12.pdf", page=1),
        _record(filename="t12.pdf", page=2, text="more NOI data"),
        _record(filename="rent_roll.pdf", page=1, text="unit rents"),
    ])
    store.delete_by_filename("p1", "t12.pdf")
    results = store.query("data", source_type="financial", property_id="p1", n_results=10)
    filenames = {r["filename"] for r in results}
    assert filenames == {"rent_roll.pdf"}


def test_get_file_hash_returns_none_when_not_ingested(store):
    assert store.get_file_hash("p1", "unknown.pdf") is None


def test_get_file_hash_returns_stored_hash(store):
    store.upsert_chunks([_record(filename="t12.pdf", file_hash="hash-xyz")])
    assert store.get_file_hash("p1", "t12.pdf") == "hash-xyz"


def test_list_chunks_returns_all_chunks_for_property(store):
    store.upsert_chunks([
        _record(property_id="p1", filename="t12.pdf", page=1, text="page one"),
        _record(property_id="p1", filename="t12.pdf", page=2, text="page two"),
        _record(property_id="p2", filename="t12.pdf", page=1, text="other property"),
    ])
    chunks = store.list_chunks("p1")
    assert len(chunks) == 2
    assert {c["text"] for c in chunks} == {"page one", "page two"}


def test_list_chunks_filters_by_source_type(store):
    store.upsert_chunks([
        _record(property_id="p1", source_type="financial", filename="t12.pdf"),
        _record(property_id="p1", source_type="capex", filename="reserve_study.pdf"),
    ])
    chunks = store.list_chunks("p1", source_type="capex")
    assert len(chunks) == 1
    assert chunks[0]["filename"] == "reserve_study.pdf"


def test_list_chunks_returns_full_metadata_sorted_by_filename_and_page(store):
    store.upsert_chunks([
        _record(property_id="p1", filename="b.pdf", page=1, text="b1", file_hash="hb"),
        _record(property_id="p1", filename="a.pdf", page=2, text="a2", file_hash="ha"),
        _record(property_id="p1", filename="a.pdf", page=1, text="a1", file_hash="ha"),
    ])
    chunks = store.list_chunks("p1")
    assert [(c["filename"], c["page_or_row"]) for c in chunks] == [
        ("a.pdf", 1),
        ("a.pdf", 2),
        ("b.pdf", 1),
    ]
    assert chunks[0]["source_type"] == "financial"
    assert chunks[0]["file_hash"] == "ha"
    assert chunks[0]["ingested_at"] == "2026-09-03T00:00:00Z"


def test_list_chunks_returns_empty_list_when_none_ingested(store):
    assert store.list_chunks("unknown-property") == []

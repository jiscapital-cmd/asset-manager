import uuid

import chromadb
import pytest

from asset_manager.ingestion.drive_client import DriveFile
from asset_manager.ingestion.ingest import run_ingestion
from asset_manager.ingestion.store import ChromaStore


def fake_embed_fn(texts):
    return [[float(len(t)), 0.0] for t in texts]


@pytest.fixture
def store():
    # Unique collection name per test — chromadb.EphemeralClient() shares its
    # in-memory system cache across instantiations within a process, so a
    # fixed collection name would otherwise accumulate chunks across tests.
    return ChromaStore(chromadb.EphemeralClient(), embed_fn=fake_embed_fn, collection_name=f"test-{uuid.uuid4()}")


class FakeDrive:
    """Fakes the two DriveClient methods run_ingestion actually calls."""

    def __init__(self, subfolders_by_property, files_by_source_folder, content_by_file_id):
        self._subfolders_by_property = subfolders_by_property
        self._files_by_source_folder = files_by_source_folder
        self._content_by_file_id = content_by_file_id

    def list_subfolders(self, folder_id):
        return self._subfolders_by_property.get(folder_id, [])

    def list_files_in_folder(self, folder_id):
        return self._files_by_source_folder.get(folder_id, [])

    def download_file(self, file_id):
        return self._content_by_file_id[file_id]


def _drive_with_one_financial_file(text: bytes = b"NOI is $1.1M"):
    return FakeDrive(
        subfolders_by_property={
            "p1-folder": [DriveFile(id="fin-folder", name="financial", modified_time="t", parents=["p1-folder"])],
        },
        files_by_source_folder={
            "fin-folder": [DriveFile(id="file-1", name="t12.txt", modified_time="t", parents=["fin-folder"])],
        },
        content_by_file_id={"file-1": text},
    )


def test_run_ingestion_adds_new_file(store):
    drive = _drive_with_one_financial_file()
    summary = run_ingestion(drive, store, property_folders={"p1": "p1-folder"})
    assert summary.files_added == 1
    assert summary.files_updated == 0
    results = store.query("NOI", source_type="financial", property_id="p1")
    assert len(results) == 1
    assert results[0]["filename"] == "t12.txt"


def test_run_ingestion_skips_unchanged_file(store):
    drive = _drive_with_one_financial_file()
    run_ingestion(drive, store, property_folders={"p1": "p1-folder"})
    summary = run_ingestion(drive, store, property_folders={"p1": "p1-folder"})
    assert summary.files_added == 0
    assert summary.files_skipped == 1


def test_run_ingestion_reingests_changed_file(store):
    drive = _drive_with_one_financial_file(text=b"NOI is $1.1M")
    run_ingestion(drive, store, property_folders={"p1": "p1-folder"})

    drive_changed = _drive_with_one_financial_file(text=b"NOI is $1.3M, revised")
    summary = run_ingestion(drive_changed, store, property_folders={"p1": "p1-folder"})
    assert summary.files_updated == 1

    results = store.query("revised", source_type="financial", property_id="p1")
    assert len(results) == 1
    assert "1.3M" in results[0]["text"]


def test_run_ingestion_skips_unsupported_file_and_continues(store):
    """One file with an unsupported extension (e.g. .xlsx that fails to
    parse, or any other loader error) must not abort ingestion for the
    rest of the batch — it should be recorded as failed and skipped."""
    drive = FakeDrive(
        subfolders_by_property={
            "p1-folder": [DriveFile(id="fin-folder", name="financial", modified_time="t", parents=["p1-folder"])],
        },
        files_by_source_folder={
            "fin-folder": [
                DriveFile(id="bad-file", name="exhibit.xyz", modified_time="t", parents=["fin-folder"]),
                DriveFile(id="good-file", name="t12.txt", modified_time="t", parents=["fin-folder"]),
            ],
        },
        content_by_file_id={"bad-file": b"unsupported content", "good-file": b"NOI is $1.1M"},
    )
    summary = run_ingestion(drive, store, property_folders={"p1": "p1-folder"})

    assert summary.files_failed == 1
    assert summary.files_added == 1
    assert any("exhibit.xyz" in name for name in summary.failed_files)

    results = store.query("NOI", source_type="financial", property_id="p1")
    assert len(results) == 1
    assert results[0]["filename"] == "t12.txt"


def test_run_ingestion_removes_chunks_for_deleted_file(store):
    drive = _drive_with_one_financial_file()
    run_ingestion(drive, store, property_folders={"p1": "p1-folder"})

    drive_empty = FakeDrive(
        subfolders_by_property={
            "p1-folder": [DriveFile(id="fin-folder", name="financial", modified_time="t", parents=["p1-folder"])],
        },
        files_by_source_folder={"fin-folder": []},
        content_by_file_id={},
    )
    summary = run_ingestion(drive_empty, store, property_folders={"p1": "p1-folder"})
    assert summary.files_deleted == 1
    assert store.get_file_hash("p1", "t12.txt") is None

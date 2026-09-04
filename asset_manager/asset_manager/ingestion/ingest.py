"""Offline ingestion: walk Drive, chunk, embed, upsert/delete in Chroma.

Never runs as part of a live orchestrator run — invoked on demand or via
the n8n scheduled workflow (Plan 3).
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from asset_manager.ingestion.chunking import chunk_text, file_hash
from asset_manager.ingestion.drive_client import DriveClient
from asset_manager.ingestion.loaders import load_document
from asset_manager.ingestion.store import ChromaStore, ChunkRecord

SOURCE_TYPES = ["financial", "pm", "capex", "general"]


@dataclass
class IngestionSummary:
    files_added: int = 0
    files_updated: int = 0
    files_deleted: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    failed_files: list[str] = field(default_factory=list)


def run_ingestion(
    drive: DriveClient,
    store: ChromaStore,
    property_folders: dict[str, str],
    now_fn=lambda: datetime.now(UTC).isoformat(),
) -> IngestionSummary:
    summary = IngestionSummary()

    for property_id, property_folder_id in property_folders.items():
        subfolders = {f.name: f.id for f in drive.list_subfolders(property_folder_id)}
        seen_filenames: set[str] = set()

        for source_type in SOURCE_TYPES:
            folder_id = subfolders.get(source_type)
            if folder_id is None:
                continue

            for remote_file in drive.list_files_in_folder(folder_id):
                seen_filenames.add(remote_file.name)
                content = drive.download_file(remote_file.id)
                new_hash = file_hash(content)
                existing_hash = store.get_file_hash(property_id, remote_file.name)

                if existing_hash == new_hash:
                    summary.files_skipped += 1
                    continue

                # Parse/chunk BEFORE touching the store — a file that fails
                # to load (unsupported type, corrupt content, etc.) must not
                # abort the rest of the batch, and an update's old chunks
                # must not be deleted until the replacement is ready.
                try:
                    pages = load_document(content, remote_file.name)
                    records = []
                    for page_number, page_text in pages:
                        for i, chunk in enumerate(chunk_text(page_text)):
                            records.append(
                                ChunkRecord(
                                    id=f"{property_id}:{remote_file.name}:{page_number}:{i}",
                                    text=chunk,
                                    property_id=property_id,
                                    source_type=source_type,
                                    filename=remote_file.name,
                                    page_or_row=page_number,
                                    file_hash=new_hash,
                                    ingested_at=now_fn(),
                                )
                            )
                except Exception as exc:
                    summary.files_failed += 1
                    summary.failed_files.append(f"{remote_file.name}: {exc}")
                    continue

                if existing_hash is not None:
                    store.delete_by_filename(property_id, remote_file.name)
                    summary.files_updated += 1
                else:
                    summary.files_added += 1
                store.upsert_chunks(records)

        # Any file previously ingested for this property but no longer
        # present in Drive gets its chunks deleted (spec Section 7,
        # "document lifecycle").
        known_filenames = store.list_known_filenames(property_id)
        for filename in known_filenames - seen_filenames:
            store.delete_by_filename(property_id, filename)
            summary.files_deleted += 1

    return summary


def _load_property_folders_from_env() -> dict[str, str]:
    """Reads PROPERTY_FOLDER_<SLUG>=<drive_folder_id> pairs from the environment."""
    import os

    folders = {}
    for key, value in os.environ.items():
        if key.startswith("PROPERTY_FOLDER_"):
            property_id = key.removeprefix("PROPERTY_FOLDER_").lower()
            folders[property_id] = value
    return folders


def main() -> None:
    import os

    from dotenv import load_dotenv

    from asset_manager.ingestion.drive_client import build_drive_client
    from asset_manager.ingestion.store import ChromaStore

    load_dotenv()

    import chromadb
    from openai import OpenAI

    def embed_fn(texts: list[str]) -> list[list[float]]:
        client = OpenAI()
        response = client.embeddings.create(model="text-embedding-3-small", input=texts)
        return [d.embedding for d in response.data]

    drive = build_drive_client(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    chroma_client = chromadb.PersistentClient(path="knowledge_base/chroma_db")
    store = ChromaStore(chroma_client, embed_fn=embed_fn)
    property_folders = _load_property_folders_from_env()

    summary = run_ingestion(drive, store, property_folders)
    print(
        f"Ingestion complete: {summary.files_added} added, "
        f"{summary.files_updated} updated, {summary.files_deleted} deleted, "
        f"{summary.files_skipped} skipped, {summary.files_failed} failed"
    )
    if summary.failed_files:
        print("Failed files (skipped, did not stop the run):")
        for failure in summary.failed_files:
            print(f"  - {failure}")


if __name__ == "__main__":
    main()

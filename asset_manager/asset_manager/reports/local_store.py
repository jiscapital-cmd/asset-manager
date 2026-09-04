"""Local-filesystem storage backend for ReportArchive, duck-typing the same
4 DriveClient methods (find_or_create_subfolder / upload_text_file /
list_files_in_folder / download_text_file) ReportArchive depends on.

Used instead of DriveClient for report storage: a Google service account
has no storage quota of its own on a personal (non-Workspace) Google Drive,
so it cannot create new files there even in a folder shared with it at
Editor access (Drive returns 403 "storageQuotaExceeded" — see
ingestion/drive_client.py). Reading raw_docs/ via the service account is
unaffected — this only replaces where completed reports are written.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class LocalFile:
    id: str
    name: str
    modified_time: str
    parents: list[str]


class LocalFileStore:
    def __init__(self, root: str | Path):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def find_or_create_subfolder(self, parent_folder_id: str, name: str) -> str:
        path = Path(parent_folder_id) / name
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def upload_text_file(self, folder_id: str, filename: str, content: str) -> None:
        Path(folder_id, filename).write_text(content, encoding="utf-8")

    def list_files_in_folder(self, folder_id: str) -> list[LocalFile]:
        folder = Path(folder_id)
        if not folder.exists():
            return []
        return [
            LocalFile(id=str(p), name=p.name, modified_time="", parents=[folder_id])
            for p in folder.iterdir()
            if p.is_file()
        ]

    def download_text_file(self, folder_id: str, filename: str) -> str | None:
        path = Path(folder_id, filename)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

"""Thin wrapper over the Google Drive API v3.

Uses a service account for standalone (non-interactive) access — see
specs/2026-09-03-asset-manager-design.md Section 4 for
why this is direct API access rather than MCP.
"""

from dataclasses import dataclass


@dataclass
class DriveFile:
    id: str
    name: str
    modified_time: str
    parents: list[str]


class DriveClient:
    def __init__(self, service):
        self._service = service

    def list_files_in_folder(self, folder_id: str) -> list[DriveFile]:
        query = f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
        return self._list(query)

    def list_subfolders(self, folder_id: str) -> list[DriveFile]:
        query = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        return self._list(query)

    def _list(self, query: str) -> list[DriveFile]:
        response = self._service.files().list(q=query, fields="files(id,name,modifiedTime,parents)").execute()
        return [
            DriveFile(id=f["id"], name=f["name"], modified_time=f["modifiedTime"], parents=f["parents"])
            for f in response["files"]
        ]

    def download_file(self, file_id: str) -> bytes:
        return self._service.files().get_media(fileId=file_id).execute()

    def find_or_create_subfolder(self, parent_folder_id: str, name: str) -> str:
        for folder in self.list_subfolders(parent_folder_id):
            if folder.name == name:
                return folder.id
        response = (
            self._service.files()
            .create(
                body={
                    "name": name,
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [parent_folder_id],
                },
                fields="id",
            )
            .execute()
        )
        return response["id"]

    def upload_text_file(self, folder_id: str, filename: str, content: str) -> None:
        import io

        from googleapiclient.http import MediaIoBaseUpload

        media = MediaIoBaseUpload(io.BytesIO(content.encode("utf-8")), mimetype="text/markdown")
        existing = next((f for f in self.list_files_in_folder(folder_id) if f.name == filename), None)
        if existing is not None:
            self._service.files().update(fileId=existing.id, media_body=media).execute()
        else:
            self._service.files().create(
                body={"name": filename, "parents": [folder_id]}, media_body=media, fields="id"
            ).execute()

    def download_text_file(self, folder_id: str, filename: str) -> str | None:
        existing = next((f for f in self.list_files_in_folder(folder_id) if f.name == filename), None)
        if existing is None:
            return None
        return self.download_file(existing.id).decode("utf-8")


def build_drive_client(service_account_json_path: str) -> DriveClient:
    """Construct a real DriveClient using a service account credentials file.

    Not unit tested — requires real Google credentials. Verified in the
    manual smoke test (Task 10).

    Scope is read/write ("drive", not "drive.readonly"): the same DriveClient
    is used both for ingestion (read-only against raw_docs/) and for
    ReportArchive (find_or_create_subfolder/upload_text_file against reports/,
    added in Plan 2) — a read-only scope makes report saving fail with a 403
    "Insufficient Permission" the first time a report is written.
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_file(
        service_account_json_path, scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=credentials)
    return DriveClient(service)

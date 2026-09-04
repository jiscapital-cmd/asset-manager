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


def build_drive_client(service_account_json_path: str) -> DriveClient:
    """Construct a real DriveClient using a service account credentials file.

    Not unit tested — requires real Google credentials. Verified in the
    manual smoke test (Task 10).
    """
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials = service_account.Credentials.from_service_account_file(
        service_account_json_path, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    service = build("drive", "v3", credentials=credentials)
    return DriveClient(service)

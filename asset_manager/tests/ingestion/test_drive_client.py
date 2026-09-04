from asset_manager.ingestion.drive_client import DriveClient, DriveFile


class FakeFilesResource:
    def __init__(self, items_by_query):
        self._items_by_query = items_by_query

    def list(self, q, fields, pageToken=None):
        return FakeRequest(self._items_by_query.get(q, []))

    def get_media(self, fileId):
        return FakeMediaRequest(fileId)


class FakeRequest:
    def __init__(self, items):
        self._items = items

    def execute(self):
        return {"files": self._items, "nextPageToken": None}


class FakeMediaRequest:
    def __init__(self, file_id):
        self._file_id = file_id

    def execute(self):
        return f"content-of-{self._file_id}".encode("utf-8")


class FakeDriveService:
    def __init__(self, items_by_query):
        self._files_resource = FakeFilesResource(items_by_query)

    def files(self):
        return self._files_resource


def test_list_files_in_folder_returns_drive_files():
    query = "'folder-1' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
    service = FakeDriveService({
        query: [
            {"id": "f1", "name": "t12.pdf", "modifiedTime": "2026-09-01T00:00:00Z", "parents": ["folder-1"]},
        ]
    })
    client = DriveClient(service)
    files = client.list_files_in_folder("folder-1")
    assert files == [DriveFile(id="f1", name="t12.pdf", modified_time="2026-09-01T00:00:00Z", parents=["folder-1"])]


def test_list_subfolders_returns_only_folders():
    query = "'root-1' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    service = FakeDriveService({
        query: [
            {"id": "sub1", "name": "financial", "modifiedTime": "2026-09-01T00:00:00Z", "parents": ["root-1"]},
        ]
    })
    client = DriveClient(service)
    folders = client.list_subfolders("root-1")
    assert [f.name for f in folders] == ["financial"]


def test_download_file_returns_bytes():
    service = FakeDriveService({})
    client = DriveClient(service)
    content = client.download_file("f1")
    assert content == b"content-of-f1"

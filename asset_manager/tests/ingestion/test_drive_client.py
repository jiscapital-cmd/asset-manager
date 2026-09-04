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


class FakeFilesResourceV2(FakeFilesResource):
    """Extends the Plan 1 fake with create/update/get_media-by-name support."""

    def __init__(self, items_by_query, created_folders=None):
        super().__init__(items_by_query)
        self.created_folders = created_folders if created_folders is not None else []
        self.created_files = []
        self.updated_files = []

    def create(self, body, media_body=None, fields=None):
        if body.get("mimeType") == "application/vnd.google-apps.folder":
            self.created_folders.append(body)
            return FakeCreateRequest({"id": f"new-folder-{len(self.created_folders)}"})
        self.created_files.append((body, media_body))
        return FakeCreateRequest({"id": f"new-file-{len(self.created_files)}"})

    def update(self, fileId, media_body=None):
        self.updated_files.append((fileId, media_body))
        return FakeCreateRequest({"id": fileId})


class FakeCreateRequest:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class FakeDriveServiceV2(FakeDriveService):
    def __init__(self, items_by_query, created_folders=None):
        self._files_resource = FakeFilesResourceV2(items_by_query, created_folders)

    def files(self):
        return self._files_resource


def test_find_or_create_subfolder_returns_existing_id_when_present():
    query = "'parent-1' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    service = FakeDriveServiceV2({
        query: [{"id": "existing-folder", "name": "champions-pointe", "modifiedTime": "t", "parents": ["parent-1"]}],
    })
    client = DriveClient(service)
    folder_id = client.find_or_create_subfolder("parent-1", "champions-pointe")
    assert folder_id == "existing-folder"
    assert service._files_resource.created_folders == []


def test_find_or_create_subfolder_creates_when_missing():
    query = "'parent-1' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    service = FakeDriveServiceV2({query: []})
    client = DriveClient(service)
    folder_id = client.find_or_create_subfolder("parent-1", "champions-pointe")
    assert folder_id == "new-folder-1"
    assert len(service._files_resource.created_folders) == 1
    assert service._files_resource.created_folders[0]["name"] == "champions-pointe"


def test_upload_text_file_creates_new_file_when_missing():
    query = "'folder-1' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
    service = FakeDriveServiceV2({query: []})
    client = DriveClient(service)
    client.upload_text_file("folder-1", "2026-09-03.md", "# Report\ncontent")
    assert len(service._files_resource.created_files) == 1
    body, media = service._files_resource.created_files[0]
    assert body["name"] == "2026-09-03.md"


def test_upload_text_file_updates_existing_file():
    query = "'folder-1' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
    service = FakeDriveServiceV2({
        query: [{"id": "existing-file", "name": "2026-09-03.md", "modifiedTime": "t", "parents": ["folder-1"]}],
    })
    client = DriveClient(service)
    client.upload_text_file("folder-1", "2026-09-03.md", "# Revised report")
    assert len(service._files_resource.updated_files) == 1
    assert service._files_resource.updated_files[0][0] == "existing-file"
    assert service._files_resource.created_files == []


def test_download_text_file_returns_none_when_missing():
    query = "'folder-1' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
    service = FakeDriveServiceV2({query: []})
    client = DriveClient(service)
    assert client.download_text_file("folder-1", "missing.md") is None


def test_download_text_file_returns_decoded_content():
    query = "'folder-1' in parents and mimeType != 'application/vnd.google-apps.folder' and trashed = false"
    service = FakeDriveServiceV2({
        query: [{"id": "file-1", "name": "2026-09-03.md", "modifiedTime": "t", "parents": ["folder-1"]}],
    })
    client = DriveClient(service)
    content = client.download_text_file("folder-1", "2026-09-03.md")
    assert content == "content-of-file-1"

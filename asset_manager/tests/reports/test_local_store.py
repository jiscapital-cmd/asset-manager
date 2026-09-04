from asset_manager.reports.local_store import LocalFileStore


def test_find_or_create_subfolder_creates_directory(tmp_path):
    store = LocalFileStore(tmp_path)
    folder = store.find_or_create_subfolder(str(tmp_path), "champions_pointe")
    assert (tmp_path / "champions_pointe").is_dir()
    assert folder == str(tmp_path / "champions_pointe")


def test_find_or_create_subfolder_is_idempotent(tmp_path):
    store = LocalFileStore(tmp_path)
    first = store.find_or_create_subfolder(str(tmp_path), "champions_pointe")
    second = store.find_or_create_subfolder(str(tmp_path), "champions_pointe")
    assert first == second


def test_upload_text_file_writes_content(tmp_path):
    store = LocalFileStore(tmp_path)
    folder = store.find_or_create_subfolder(str(tmp_path), "champions_pointe")
    store.upload_text_file(folder, "2026-09-04.md", "# Report content")
    assert (tmp_path / "champions_pointe" / "2026-09-04.md").read_text(encoding="utf-8") == "# Report content"


def test_upload_text_file_overwrites_existing_file(tmp_path):
    store = LocalFileStore(tmp_path)
    folder = store.find_or_create_subfolder(str(tmp_path), "champions_pointe")
    store.upload_text_file(folder, "2026-09-04.md", "# First version")
    store.upload_text_file(folder, "2026-09-04.md", "# Revised version")
    assert (tmp_path / "champions_pointe" / "2026-09-04.md").read_text(encoding="utf-8") == "# Revised version"


def test_list_files_in_folder_returns_empty_list_when_folder_missing(tmp_path):
    store = LocalFileStore(tmp_path)
    result = store.list_files_in_folder(str(tmp_path / "does-not-exist"))
    assert result == []


def test_list_files_in_folder_returns_only_files(tmp_path):
    store = LocalFileStore(tmp_path)
    folder = store.find_or_create_subfolder(str(tmp_path), "champions_pointe")
    store.upload_text_file(folder, "2026-08-01.md", "# August")
    store.upload_text_file(folder, "2026-09-04.md", "# September")
    (tmp_path / "champions_pointe" / "subdir").mkdir()

    files = store.list_files_in_folder(folder)
    assert sorted(f.name for f in files) == ["2026-08-01.md", "2026-09-04.md"]


def test_download_text_file_returns_none_when_missing(tmp_path):
    store = LocalFileStore(tmp_path)
    folder = store.find_or_create_subfolder(str(tmp_path), "champions_pointe")
    assert store.download_text_file(folder, "missing.md") is None


def test_download_text_file_returns_content(tmp_path):
    store = LocalFileStore(tmp_path)
    folder = store.find_or_create_subfolder(str(tmp_path), "champions_pointe")
    store.upload_text_file(folder, "2026-09-04.md", "# Report content")
    assert store.download_text_file(folder, "2026-09-04.md") == "# Report content"

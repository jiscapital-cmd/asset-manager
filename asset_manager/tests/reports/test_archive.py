from asset_manager.ingestion.drive_client import DriveFile
from asset_manager.reports.archive import ReportArchive


class FakeDriveForArchive:
    def __init__(self):
        self.property_folders: dict[str, str] = {}
        self.saved_reports: dict[tuple[str, str], str] = {}
        self._next_folder_id = 1

    def find_or_create_subfolder(self, parent_folder_id, name):
        key = (parent_folder_id, name)
        if key not in self.property_folders:
            self.property_folders[key] = f"folder-{self._next_folder_id}"
            self._next_folder_id += 1
        return self.property_folders[key]

    def upload_text_file(self, folder_id, filename, content):
        self.saved_reports[(folder_id, filename)] = content

    def list_files_in_folder(self, folder_id):
        return [
            DriveFile(id="x", name=filename, modified_time="t", parents=[folder_id])
            for (fid, filename) in self.saved_reports
            if fid == folder_id
        ]

    def download_text_file(self, folder_id, filename):
        return self.saved_reports.get((folder_id, filename))


def test_save_report_writes_to_property_subfolder():
    drive = FakeDriveForArchive()
    archive = ReportArchive(drive, reports_root_folder_id="reports-root", today_fn=lambda: "2026-09-03")
    date_str = archive.save_report("champions-pointe", "# Report content")
    assert date_str == "2026-09-03"
    property_folder = drive.property_folders[("reports-root", "champions-pointe")]
    assert drive.saved_reports[(property_folder, "2026-09-03.md")] == "# Report content"


def test_get_latest_report_returns_none_when_no_reports_exist():
    drive = FakeDriveForArchive()
    archive = ReportArchive(drive, reports_root_folder_id="reports-root")
    assert archive.get_latest_report("champions-pointe") is None


def test_get_latest_report_returns_most_recent_by_date():
    drive = FakeDriveForArchive()
    archive = ReportArchive(drive, reports_root_folder_id="reports-root", today_fn=lambda: "2026-08-01")
    archive.save_report("champions-pointe", "# August report")

    archive2 = ReportArchive(drive, reports_root_folder_id="reports-root", today_fn=lambda: "2026-09-03")
    archive2.save_report("champions-pointe", "# September report")

    latest = archive.get_latest_report("champions-pointe")
    assert latest == "# September report"

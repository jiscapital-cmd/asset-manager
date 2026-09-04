"""Persists completed reports to Drive and retrieves the most recent one
per property, enabling risk-agent's history diffing (spec Section 2,
"Historical comparison")."""

from datetime import date


class ReportArchive:
    def __init__(self, drive, reports_root_folder_id: str, today_fn=lambda: date.today().isoformat()):
        self._drive = drive
        self._reports_root_folder_id = reports_root_folder_id
        self._today_fn = today_fn

    def save_report(self, property_id: str, content: str) -> str:
        date_str = self._today_fn()
        folder_id = self._drive.find_or_create_subfolder(self._reports_root_folder_id, property_id)
        self._drive.upload_text_file(folder_id, f"{date_str}.md", content)
        return date_str

    def get_latest_report(self, property_id: str) -> str | None:
        folder_id = self._drive.find_or_create_subfolder(self._reports_root_folder_id, property_id)
        files = self._drive.list_files_in_folder(folder_id)
        if not files:
            return None
        # Filenames are YYYY-MM-DD.md — lexicographic max is chronologically latest.
        latest_filename = max(f.name for f in files)
        return self._drive.download_text_file(folder_id, latest_filename)

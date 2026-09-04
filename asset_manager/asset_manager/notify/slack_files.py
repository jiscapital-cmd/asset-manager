"""Uploads a file to Slack.

SlackWebhookNotifier (slack.py) posts text only — Incoming Webhooks have no
file-upload capability. Sending an actual PDF/Word file requires Slack's
Web API instead, via the current (files.upload is deprecated) 3-step
external-upload flow: request an upload URL, PUT the bytes to it, then
finalize/share the file into a channel. This needs a Slack Bot Token
(scope: files:write) and the target channel's ID — different credentials
from the webhook URL used for text notifications.
"""

import requests


class SlackFileUploader:
    def __init__(self, bot_token: str, channel_id: str, post_fn=requests.post):
        self._bot_token = bot_token
        self._channel_id = channel_id
        self._post_fn = post_fn

    def upload(self, filename: str, content: bytes, initial_comment: str = "") -> None:
        headers = {"Authorization": f"Bearer {self._bot_token}"}

        get_url_response = self._post_fn(
            "https://slack.com/api/files.getUploadURLExternal",
            data={"filename": filename, "length": len(content)},
            headers=headers,
            timeout=10,
        ).json()
        if not get_url_response.get("ok"):
            raise RuntimeError(f"files.getUploadURLExternal failed: {get_url_response}")

        upload_url = get_url_response["upload_url"]
        file_id = get_url_response["file_id"]

        self._post_fn(upload_url, files={"file": (filename, content)}, timeout=30)

        complete_response = self._post_fn(
            "https://slack.com/api/files.completeUploadExternal",
            json={
                "files": [{"id": file_id, "title": filename}],
                "channel_id": self._channel_id,
                "initial_comment": initial_comment,
            },
            headers=headers,
            timeout=10,
        ).json()
        if not complete_response.get("ok"):
            raise RuntimeError(f"files.completeUploadExternal failed: {complete_response}")

import pytest

from asset_manager.notify.slack_files import SlackFileUploader


class FakePostFn:
    def __init__(self, responses):
        self.calls = []
        self._responses = responses  # one dict per call, in order

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))

        class FakeResponse:
            def __init__(self, data):
                self._data = data

            def json(self):
                return self._data

        return FakeResponse(self._responses[len(self.calls) - 1])


def test_upload_performs_three_step_flow_and_shares_to_channel():
    post_fn = FakePostFn([
        {"ok": True, "upload_url": "https://upload.example/put", "file_id": "F123"},
        {},  # the raw PUT-to-upload_url response body isn't used
        {"ok": True},
    ])
    uploader = SlackFileUploader(bot_token="xoxb-test", channel_id="C123", post_fn=post_fn)
    uploader.upload("report.pdf", b"%PDF-fake-bytes", initial_comment="Champions Pointe report")

    assert len(post_fn.calls) == 3

    url1, kwargs1 = post_fn.calls[0]
    assert url1 == "https://slack.com/api/files.getUploadURLExternal"
    assert kwargs1["data"]["filename"] == "report.pdf"
    assert kwargs1["data"]["length"] == len(b"%PDF-fake-bytes")
    assert kwargs1["headers"]["Authorization"] == "Bearer xoxb-test"

    url2, kwargs2 = post_fn.calls[1]
    assert url2 == "https://upload.example/put"

    url3, kwargs3 = post_fn.calls[2]
    assert url3 == "https://slack.com/api/files.completeUploadExternal"
    assert kwargs3["json"]["channel_id"] == "C123"
    assert kwargs3["json"]["files"] == [{"id": "F123", "title": "report.pdf"}]
    assert kwargs3["json"]["initial_comment"] == "Champions Pointe report"


def test_upload_raises_when_get_upload_url_fails():
    post_fn = FakePostFn([{"ok": False, "error": "invalid_auth"}])
    uploader = SlackFileUploader(bot_token="xoxb-bad", channel_id="C123", post_fn=post_fn)
    with pytest.raises(RuntimeError, match="invalid_auth"):
        uploader.upload("report.pdf", b"data")


def test_upload_raises_when_complete_upload_fails():
    post_fn = FakePostFn([
        {"ok": True, "upload_url": "https://upload.example/put", "file_id": "F123"},
        {},
        {"ok": False, "error": "channel_not_found"},
    ])
    uploader = SlackFileUploader(bot_token="xoxb-test", channel_id="bad-channel", post_fn=post_fn)
    with pytest.raises(RuntimeError, match="channel_not_found"):
        uploader.upload("report.pdf", b"data")

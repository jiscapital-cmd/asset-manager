from asset_manager.notify.slack import SlackWebhookNotifier


class FakePostFn:
    def __init__(self):
        self.calls = []

    def __call__(self, url, json, timeout=10):
        self.calls.append((url, json))

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                pass

        return FakeResponse()


def test_send_posts_message_as_slack_text_payload():
    post_fn = FakePostFn()
    notifier = SlackWebhookNotifier("https://hooks.slack.com/services/xxx", post_fn=post_fn)
    notifier.send("Champions Pointe review is ready.")
    assert len(post_fn.calls) == 1
    url, payload = post_fn.calls[0]
    assert url == "https://hooks.slack.com/services/xxx"
    assert payload == {"text": "Champions Pointe review is ready."}

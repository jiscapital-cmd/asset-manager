"""Sends a notification to a Slack incoming webhook."""

import requests


class SlackWebhookNotifier:
    def __init__(self, webhook_url: str, post_fn=requests.post):
        self._webhook_url = webhook_url
        self._post_fn = post_fn

    def send(self, message: str) -> None:
        response = self._post_fn(self._webhook_url, json={"text": message}, timeout=10)
        response.raise_for_status()

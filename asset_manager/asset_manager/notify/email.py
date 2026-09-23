"""Sends a report by email over SMTP, with optional file attachments.

Uses SMTP directly (e.g. Gmail with an App Password) rather than a
transactional email API — no new account/API key needed beyond what's
already in .env, consistent with the rest of notify/ (Slack) being
credential-light.
"""

import smtplib
from email.message import EmailMessage


class EmailNotifier:
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        sender: str,
        smtp_client_factory=smtplib.SMTP_SSL,
    ):
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._username = username
        self._password = password
        self._sender = sender
        self._smtp_client_factory = smtp_client_factory

    def send_report(
        self,
        subject: str,
        body: str,
        recipients: list[str],
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self._sender
        message["To"] = ", ".join(recipients)
        message.set_content(body)

        for filename, content, mime_type in attachments or []:
            maintype, subtype = mime_type.split("/", 1)
            message.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

        with self._smtp_client_factory(self._smtp_host, self._smtp_port) as client:
            client.login(self._username, self._password)
            client.send_message(message)

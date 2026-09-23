from asset_manager.notify.email import EmailNotifier


class FakeSMTPClient:
    instances = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.login_calls = []
        self.sent_messages = []
        FakeSMTPClient.instances.append(self)

    def login(self, username, password):
        self.login_calls.append((username, password))

    def send_message(self, message):
        self.sent_messages.append(message)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def make_notifier():
    FakeSMTPClient.instances = []
    return EmailNotifier(
        smtp_host="smtp.gmail.com",
        smtp_port=465,
        username="reports@example.com",
        password="app-password",
        sender="reports@example.com",
        smtp_client_factory=FakeSMTPClient,
    )


def test_send_report_logs_in_and_sends_to_all_recipients():
    notifier = make_notifier()
    notifier.send_report(
        subject="Champions Pointe — monthly review",
        body="See attached report.",
        recipients=["owner@example.com", "pm@example.com"],
    )

    client = FakeSMTPClient.instances[0]
    assert client.host == "smtp.gmail.com"
    assert client.port == 465
    assert client.login_calls == [("reports@example.com", "app-password")]
    assert len(client.sent_messages) == 1

    message = client.sent_messages[0]
    assert message["Subject"] == "Champions Pointe — monthly review"
    assert message["From"] == "reports@example.com"
    assert message["To"] == "owner@example.com, pm@example.com"
    assert message.get_content().strip() == "See attached report."


def test_send_report_attaches_files():
    notifier = make_notifier()
    notifier.send_report(
        subject="Report",
        body="See attached.",
        recipients=["owner@example.com"],
        attachments=[
            ("report.pdf", b"%PDF-fake-bytes", "application/pdf"),
            ("report.docx", b"docx-fake-bytes", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ],
    )

    message = FakeSMTPClient.instances[0].sent_messages[0]
    parts = list(message.iter_attachments())
    assert len(parts) == 2
    assert parts[0].get_filename() == "report.pdf"
    assert parts[0].get_content() == b"%PDF-fake-bytes"
    assert parts[1].get_filename() == "report.docx"


def test_send_report_with_no_attachments_sends_plain_message():
    notifier = make_notifier()
    notifier.send_report(subject="Report", body="Body text", recipients=["owner@example.com"])

    message = FakeSMTPClient.instances[0].sent_messages[0]
    assert list(message.iter_attachments()) == []

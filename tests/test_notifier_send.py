from ccdrop.notifier import TelegramNotifier


class FakeResponse:
    def __init__(self, ok):
        self.status_code = 200 if ok else 500


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        return self.responses.pop(0)


def test_successful_send_reports_true():
    session = FakeSession([FakeResponse(True)])

    assert TelegramNotifier("tok", "42", session).send("treść") is True


def test_failed_send_reports_false():
    session = FakeSession([FakeResponse(False)])

    assert TelegramNotifier("tok", "42", session).send("treść") is False


def test_posts_to_chat_id():
    session = FakeSession([FakeResponse(True)])
    TelegramNotifier("tok", "42", session).send("treść")

    assert session.calls[0][1]["chat_id"] == "42"

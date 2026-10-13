from dataclasses import dataclass

from huayapp_scraper.http_client import HttpClient


@dataclass
class FakeResponse:
    status_code: int
    text: str = "ok"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self):
        self.responses = [FakeResponse(503), FakeResponse(200, "<html>ok</html>")]
        self.calls = 0

    def get(self, url, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


def test_http_client_retries_transient_status_then_returns_html():
    session = FakeSession()
    sleeps = []
    client = HttpClient(session=session, max_retries=2, backoff_base=0.1, sleep=sleeps.append)

    assert client.get("https://huayapp.com/") == "<html>ok</html>"
    assert session.calls == 2
    assert sleeps == [0.1]

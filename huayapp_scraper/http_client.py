from __future__ import annotations

import time
from collections.abc import Callable

import requests


class HttpClientError(RuntimeError):
    pass


class HttpClient:
    _TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout: float = 20.0,
        max_retries: int = 3,
        backoff_base: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.backoff_base = max(0.0, backoff_base)
        self.sleep = sleep

    def get(self, url: str) -> str:
        headers = {"User-Agent": "HuayappHtmlScraper/1.0 (+respectful-public-fetch)"}
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(url, headers=headers, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise HttpClientError(f"GET failed after retries: {url}") from exc
                self.sleep(self.backoff_base * (2**attempt))
                continue

            if response.status_code == 200:
                return response.text
            if response.status_code not in self._TRANSIENT_STATUS:
                raise HttpClientError(f"GET {url} returned HTTP {response.status_code}")
            last_error = HttpClientError(f"GET {url} returned transient HTTP {response.status_code}")
            if attempt < self.max_retries:
                self.sleep(self.backoff_base * (2**attempt))

        raise HttpClientError(f"GET failed after retries: {url}") from last_error

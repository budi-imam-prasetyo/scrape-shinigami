"""Test HTTP client API Shinigami: retry, backoff, dan penanganan error.

Version: 1.0.0

Menguji `ApiClient.get_json` asli dengan session tiruan (tanpa jaringan).
Dijamin: retry untuk status transient, backoff, dan NON-retry untuk 4xx
permanen (404 dst).
"""

import sys
import unittest
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from manhwa_scraper.http import ApiClient, ApiClientError


class JsonResponse:
    """Tiruan requests.Response minimal."""

    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code
        self.text = body if isinstance(body, str) else str(body)

    def json(self):
        import json

        return json.loads(self._body) if isinstance(self._body, str) else self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"Status {self.status_code}")


class StubSession:
    def __init__(self):
        self.calls = 0
        self.headers = {}
        self.responses = []
        self.connection_fails = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        if self.connection_fails > 0:
            self.connection_fails -= 1
            raise requests.ConnectionError("simulated network failure")
        if self.responses:
            return self.responses.pop(0)
        return JsonResponse({"data": []})


class TestApiClient(unittest.TestCase):
    def test_retry_then_success(self):
        session = StubSession()
        session.connection_fails = 2
        client = ApiClient(session=session, max_retries=3, backoff_base=0.01)
        data = client.get_json("https://x/api", params={"a": 1})
        self.assertEqual(data, {"data": []})
        self.assertEqual(session.calls, 3)

    def test_retry_exhausted_raises(self):
        session = StubSession()
        session.connection_fails = 10
        client = ApiClient(session=session, max_retries=2, backoff_base=0.01)
        with self.assertRaises(ApiClientError):
            client.get_json("https://x/api")
        self.assertEqual(session.calls, 2)

    def test_non_retryable_404_not_retried(self):
        session = StubSession()
        session.responses = [JsonResponse("{}", status_code=404)]
        client = ApiClient(session=session, max_retries=3, backoff_base=0.01)
        with self.assertRaises(ApiClientError):
            client.get_json("https://x/api")
        self.assertEqual(session.calls, 1, "404 tidak boleh di-retry")

    def test_retryable_503_retried(self):
        session = StubSession()
        session.responses = [JsonResponse("{}", status_code=503), JsonResponse({"data": [1]})]
        client = ApiClient(session=session, max_retries=3, backoff_base=0.01)
        data = client.get_json("https://x/api")
        self.assertEqual(data, {"data": [1]})
        self.assertEqual(session.calls, 2)


if __name__ == "__main__":
    unittest.main()
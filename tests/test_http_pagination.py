"""Test HTTP client API Shinigami: retry, backoff, dan penanganan error.

Version: 1.0.0

Menguji `ApiClient.get_json` asli dengan session tiruan (tanpa jaringan).
Dijamin: retry untuk status transient, backoff, dan NON-retry untuk 4xx
permanen (404 dst).
"""

import sys
import unittest
from unittest.mock import patch
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
        session.responses = [
            JsonResponse("{}", status_code=503),
            JsonResponse({"data": [1]}),
        ]
        client = ApiClient(session=session, max_retries=3, backoff_base=0.01)
        data = client.get_json("https://x/api")
        self.assertEqual(data, {"data": [1]})
        self.assertEqual(session.calls, 2)

    def test_forbidden_is_fatal_by_default(self):
        session = StubSession()
        session.responses = [JsonResponse({}, status_code=403)]
        with self.assertRaises(ApiClientError):
            ApiClient(session=session).get_json("https://x/api")
        self.assertEqual(session.calls, 1)

    @patch("manhwa_scraper.http.time.sleep")
    def test_ci_forbidden_retries_then_succeeds(self, sleep):
        for method in ("get_json", "get_text"):
            with self.subTest(method=method):
                session = StubSession()
                session.responses = [JsonResponse({}, 403), JsonResponse({"data": []})]
                client = ApiClient(session=session, retry_forbidden=True)
                getattr(client, method)("https://x/api")
                self.assertEqual(session.calls, 2)

    @patch("manhwa_scraper.http.time.sleep")
    def test_permanent_forbidden_still_fails_after_limit(self, sleep):
        session = StubSession()
        session.responses = [JsonResponse({}, 403) for _ in range(3)]
        client = ApiClient(session=session, retry_forbidden=True, max_retries=3)
        with self.assertRaisesRegex(ApiClientError, "403"):
            client.get_json("https://x/api")
        self.assertEqual(session.calls, 3)
        self.assertEqual(sleep.call_count, 2)

    @patch("manhwa_scraper.http.time.sleep")
    def test_ci_does_not_retry_other_permanent_errors(self, sleep):
        for status in (400, 401, 404):
            with self.subTest(status=status):
                session = StubSession()
                session.responses = [JsonResponse({}, status)]
                with self.assertRaises(ApiClientError):
                    ApiClient(session=session, retry_forbidden=True).get_json("https://x/api")
                self.assertEqual(session.calls, 1)
        sleep.assert_not_called()

    def test_failure_logs_only_allowlisted_headers(self):
        session = StubSession()
        response = JsonResponse({"secret": "private-body"}, 403)
        response.headers = requests.structures.CaseInsensitiveDict({
            "Server": "cloudflare", "CF-Ray": "test-ray", "CF-Mitigated": "challenge",
            "Set-Cookie": "private-cookie", "Authorization": "private-token",
        })
        session.responses = [response]
        with self.assertLogs("manhwa_scraper.http", level="WARNING") as logs:
            with self.assertRaises(ApiClientError):
                ApiClient(session=session).get_json("https://x/api")
        message = " ".join(logs.output)
        self.assertIn("cf-ray=test-ray", message)
        self.assertIn("cf-mitigated=challenge", message)
        self.assertNotIn("private-", message)


if __name__ == "__main__":
    unittest.main()

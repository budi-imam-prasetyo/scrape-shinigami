"""Test pagination, deduplication, dan error handling (session tiruan, tanpa network)."""

import sys
import unittest
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from manhwa_scraper.http import HttpClient
from main import discover_next_page, parse_list_page, scrape_list_pages


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"Status {self.status_code}")


class FailingThenSuccessSession:
    def __init__(self):
        self.calls = 0
        self.headers = {}

    def get(self, url, timeout=None):
        self.calls += 1
        if self.calls < 3:
            raise requests.ConnectionError("simulated network failure")
        return FakeResponse("<html><body>ok</body></html>")


class AlwaysFailSession:
    def __init__(self):
        self.calls = 0
        self.headers = {}

    def get(self, url, timeout=None):
        self.calls += 1
        raise requests.Timeout("simulated timeout")


class SequentialSession:
    def __init__(self, pages):
        self.pages = list(pages)
        self.headers = {}

    def get(self, url, timeout=None):
        return FakeResponse(self.pages.pop(0))


LIST_PAGE_1 = """
<div class="bge"><div class="bgei"><a href="/manga/a/"><img src="https://t/a.jpg"/></a></div>
<div class="kan"><h3>Judul A</h3><p>Sinopsis A</p></div></div>
<div class="bge"><div class="bgei"><a href="/manga/b/"><img data-src="https://t/b.webp"/></a></div>
<div class="kan"><h3>Judul B</h3><p>Sinopsis B</p></div></div>
<span hx-get="https://api.komiku.org/manga/page/2/?tipe=manhwa"></span>
"""
LIST_PAGE_2 = """
<div class="bge"><div class="bgei"><a href="/manga/c/"><img src="https://t/c.jpg"/></a></div>
<div class="kan"><h3>Judul C</h3><p></p></div></div>
"""


class TestErrorHandling(unittest.TestCase):
    def test_retry_then_success(self):
        client = HttpClient(session=FailingThenSuccessSession(), backoff_base=0.01)
        self.assertEqual(client.get("https://x/"), "<html><body>ok</body></html>")
        self.assertEqual(client.session.calls, 3)

    def test_retry_exhausted_raises(self):
        client = HttpClient(session=AlwaysFailSession(), max_retries=2, backoff_base=0.01)
        with self.assertRaises(requests.Timeout):
            client.get("https://x/")
        self.assertEqual(client.session.calls, 2)


class TestListPagination(unittest.TestCase):
    def test_parse_list_page(self):
        items = parse_list_page(LIST_PAGE_1, "https://komiku.org/")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["judul"], "Judul A")
        self.assertEqual(items[1]["url_img"], "https://t/b.webp")
        self.assertEqual(items[0]["detail_url"], "https://komiku.org/manga/a/")

    def test_discover_next_page(self):
        nxt = discover_next_page(LIST_PAGE_1, "https://api.komiku.org/manga/?tipe=manhwa")
        self.assertEqual(nxt, "https://api.komiku.org/manga/page/2/?tipe=manhwa")
        self.assertIsNone(discover_next_page(LIST_PAGE_2, "https://x/"))

    def test_scrape_list_pages_follows_pagination(self):
        client = HttpClient(session=SequentialSession([LIST_PAGE_1, LIST_PAGE_2]), delay_range=(0, 0))
        items, failed = scrape_list_pages(client, max_pages=5)
        self.assertEqual(failed, 0)
        self.assertEqual([i["judul"] for i in items], ["Judul A", "Judul B", "Judul C"])

    def test_scrape_list_pages_stops_on_no_new_items(self):
        client = HttpClient(
            session=SequentialSession([LIST_PAGE_1, LIST_PAGE_1, LIST_PAGE_2]),
            delay_range=(0, 0),
        )
        items, failed = scrape_list_pages(client, max_pages=5)
        self.assertEqual([i["judul"] for i in items], ["Judul A", "Judul B"])
        self.assertEqual(failed, 0)

    def test_scrape_list_pages_request_failure_counts(self):
        client = HttpClient(session=AlwaysFailSession(), max_retries=1, delay_range=(0, 0))
        items, failed = scrape_list_pages(client, max_pages=3)
        self.assertEqual(items, [])
        self.assertEqual(failed, 1)


if __name__ == "__main__":
    unittest.main()

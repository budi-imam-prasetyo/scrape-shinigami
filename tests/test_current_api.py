"""Regresi kontrak API frontend Shinigami November 2026."""

import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from main import main
from manhwa_scraper.config import API_BASE, COMMENTS_URL, SITE_BASE
from manhwa_scraper.http import ApiClientError
from manhwa_scraper.normalize import normalize_manga_item
from manhwa_scraper.parser import parse_comments_payload
from manhwa_scraper.scraper import ShinigamiScraper, build_sections
from manhwa_scraper.storage import build_document

FIXTURES = Path(__file__).parent / "fixtures"


def page(ids, has_next):
    return {"retcode": 0, "meta": {"has_next": has_next},
            "data": [{"manga_id": mid, "title": mid} for mid in ids]}


class TestCurrentApi(unittest.TestCase):
    def test_offset_pagination_follows_metadata_even_for_short_pages(self):
        client = Mock()
        client.get_json.side_effect = [page(["a"], True), page(["b"], True), page(["c"], False)]
        items = ShinigamiScraper(client).scrape_section("latest")
        self.assertEqual([item["id"] for item in items], ["a", "b", "c"])
        self.assertEqual([call.kwargs["params"]["offset"] for call in client.get_json.call_args_list], [0, 1, 2])
        self.assertTrue(all(call.kwargs["params"]["limit"] == 100 for call in client.get_json.call_args_list))
        self.assertEqual(client.polite_delay.call_count, 2)

    def test_explicit_page_limit(self):
        client = Mock()
        client.get_json.return_value = page(["a"], True)
        self.assertEqual(len(ShinigamiScraper(client).scrape_section("rating", pages=1)), 1)
        client.get_json.assert_called_once()

    def test_repeated_page_does_not_loop_or_save_partial_results(self):
        client = Mock()
        client.get_json.return_value = page(["a"], True)
        with self.assertRaises(ApiClientError):
            ShinigamiScraper(client).scrape_section()
        self.assertEqual(client.get_json.call_count, 2)

    def test_invalid_payload_is_an_error(self):
        for payload in ({"retcode": 1, "message": "bad limit"}, {}, {"data": [None]}, {"data": [{}]}, page([], True)):
            with self.subTest(payload=payload):
                client = Mock()
                client.get_json.return_value = payload
                with self.assertRaises(ApiClientError):
                    ShinigamiScraper(client).scrape_section()

    def test_current_list_fixture_validates(self):
        client = Mock()
        payload = json.loads((FIXTURES / "list_current.json").read_text())
        payload["meta"]["has_next"] = False
        client.get_json.return_value = payload
        sections = build_sections(ShinigamiScraper(client), kinds=["latest"])
        doc = build_document(sections, "2026-11-19T00:00:00Z", SITE_BASE)
        self.assertEqual(len(doc["sections"][0]["items"]), 2)
        self.assertTrue(sections[0]["items"][0]["detail_url"].startswith(SITE_BASE))

    def test_top_uses_limit_and_enriches(self):
        client = Mock()
        client.get_json.side_effect = [json.loads((FIXTURES / "top_current.json").read_text()),
                                     {"data": {"taxonomy": {"Genre": [{"name": "Action"}]}}},
                                     {"data": {"taxonomy": {}}}]
        items = ShinigamiScraper(client).fetch_top()
        self.assertEqual(items[0]["genre"], ["Action"])
        self.assertEqual(client.get_json.call_args_list[0].args, (API_BASE + "/manga/top",))
        self.assertEqual(client.get_json.call_args_list[0].kwargs["params"], {"limit": 10})

    def test_comment_page_key_and_new_payload(self):
        client = Mock()
        client.get_json.return_value = {"comments": [
            {"id": 42, "nick": "Reader", "content": "<p>Bagus &amp; seru</p>",
             "date": "2026-11-19 19:00:00", "vote_up": 3, "visible": True},
            {"nick": "Hidden", "content": "hidden", "is_deleted": True}]}
        item = normalize_manga_item({"manga_id": "m", "title": "M", "latest_chapter_id": "c"})
        comments = ShinigamiScraper(client).fetch_comments(item)
        client.get_json.assert_called_once_with(COMMENTS_URL, params={"page_key": "manga:m:chapter:c", "offset": 0, "limit": 10})
        self.assertEqual(comments, [{"id": "42", "username": "Reader", "isi": "Bagus & seru", "tanggal": "2026-11-19", "suka": 3}])
        self.assertEqual(parse_comments_payload({"comments": []}), [])

    def test_api_error_preserves_existing_output(self):
        with patch("main.ApiClient") as factory, patch("main.save_atomic") as save:
            factory.return_value.get_json.return_value = {"retcode": 1, "message": "API changed"}
            self.assertEqual(main(["--kinds", "latest"]), 1)
            save.assert_not_called()

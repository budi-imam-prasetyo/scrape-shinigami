"""Unit test scraper orkestrasi (tanpa network: stub client).

Version: 1.0.0
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from manhwa_scraper.scraper import (
    ShinigamiScraper,
    build_sections,
    deduplicate_items,
    strip_internal,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class StubClient:
    """Client tiruan: kembalikan fixture JSON berdasarkan keyword URL."""

    def __init__(self):
        self.polite = 0

    def get_json(self, url, params=None):
        if "/manga/top" in url:
            return json.loads(fixture_text("top_page1.json"))
        if "/manga/list" in url:
            return json.loads(fixture_text("list_page1.json"))
        if "/manga/detail/" in url:
            return json.loads(fixture_text("detail_demonic.json"))
        if "commento.shngm.io" in url:
            return json.loads(fixture_text("waline_comments.json"))
        return {}

    def polite_delay(self):
        self.polite += 1


class TestScraper(unittest.TestCase):
    def test_fetch_top_enriches_taxonomy(self):
        scraper = ShinigamiScraper(client=StubClient())
        items = scraper.fetch_top()
        self.assertGreater(len(items), 0)
        # top dari fixture = Demonic Emperor (detail_demonic.json), jadi
        # setidaknya satu item harus dapat genre via detail enrichment.
        self.assertTrue(any(it.get("genre") for it in items))

    def test_fetch_latest_normalizes(self):
        scraper = ShinigamiScraper(client=StubClient())
        items = scraper.fetch_latest()
        self.assertEqual(len(items), 3)  # fixture page_size=3
        for it in items:
            self.assertTrue(it.get("id"))
            self.assertTrue(it.get("judul"))
            self.assertTrue(it.get("_waline_path"))

    def test_fetch_comments_uses_waline_path(self):
        scraper = ShinigamiScraper(client=StubClient())
        manga = {"_waline_path": "chapter/x", "id": "cid"}
        comments = scraper.fetch_comments(manga, limit=5)
        self.assertGreater(len(comments), 0)

    def test_fetch_comments_empty_when_no_path(self):
        scraper = ShinigamiScraper(client=StubClient())
        self.assertEqual(scraper.fetch_comments({"id": "x"}), [])

    def test_build_sections_strips_internal(self):
        scraper = ShinigamiScraper(client=StubClient())
        sections = build_sections(scraper, kinds=["latest"], with_comments=False)
        for s in sections:
            for it in s["items"]:
                self.assertFalse(any(k.startswith("_") for k in it))

    def test_build_sections_with_comments(self):
        scraper = ShinigamiScraper(client=StubClient())
        sections = build_sections(scraper, kinds=["latest"], with_comments=True)
        any_comment = any(
            it.get("komentar") for s in sections for it in s.get("items", [])
        )
        self.assertTrue(any_comment)

    def test_comments_cached_across_sections(self):
        """Item yang sama di beberapa section hanya memicu satu request komentar."""

        class CountingScraper(ShinigamiScraper):
            def __init__(self):
                super().__init__(client=StubClient())
                self.comment_calls = 0

            def fetch_comments(self, manga, limit=10):
                self.comment_calls += 1
                return super().fetch_comments(manga, limit=limit)

        scraper = CountingScraper()
        # Dua section dalam SATU pemanggilan attach_comments (seperti build_sections):
        # item 'x' yang punya _waline_path muncul di keduanya → fetch_comments
        # hanya dipanggil sekali untuk x.
        sections = [
            {
                "title": "Satu",
                "items": [
                    {"id": "x", "judul": "X", "_waline_path": "chapter/1"},
                    {"id": "y", "judul": "Y", "_waline_path": "chapter/2"},
                ],
            },
            {
                "title": "Dua",
                "items": [
                    {"id": "x", "judul": "X", "_waline_path": "chapter/1"},
                ],
            },
        ]
        from manhwa_scraper.scraper import attach_comments

        attach_comments(scraper, sections, limit=10)
        # section1 => x, y = 2 panggilan. section2 => x sudah di-cache => 0 baru.
        self.assertEqual(scraper.comment_calls, 2)
        # Cache menyalin komentar x dari section1 ke kemunculannya di section2
        # (bukti duplicate request dihindari, hasil reuse).
        self.assertEqual(
            sections[1]["items"][0]["komentar"], sections[0]["items"][0]["komentar"]
        )


class TestDeduplicate(unittest.TestCase):
    def test_merges_by_id(self):
        items = [
            {"id": "a", "judul": "A", "genre": ["X"]},
            {"id": "a", "judul": "A", "genre": []},  # duplikat, kosong
            {"id": "b", "judul": "B"},
        ]
        result, dups = deduplicate_items(items)
        self.assertEqual(len(result), 2)
        self.assertEqual(dups, 1)
        self.assertEqual(result[0]["genre"], ["X"])


class TestStripInternal(unittest.TestCase):
    def test_removes_underscore_keys(self):
        out = strip_internal({"id": "x", "_waline_path": "p", "judul": "J"})
        self.assertEqual(set(out.keys()), {"id", "judul"})


if __name__ == "__main__":
    unittest.main()

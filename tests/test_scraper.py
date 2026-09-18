"""Unit test dengan HTML fixture (tanpa network)."""

import json
import unittest
from pathlib import Path
from unittest import mock

from bs4 import BeautifulSoup

from manhwa_scraper.normalize import normalize_url, section_id
from manhwa_scraper.parser import parse_card_sections, parse_rank_sections
from manhwa_scraper.scraper import collect_sections, deduplicate_items, deduplicate_sections
from manhwa_scraper.storage import build_document, save_atomic, validate_document

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def parse_fixture(name, base_url="https://komiku.org/"):
    return BeautifulSoup(load_fixture(name), "html.parser"), base_url


class TestParser(unittest.TestCase):
    def test_parse_card_sections_fixture(self):
        soup, base = parse_fixture("komiku_home.html")
        sections = parse_card_sections(soup, base)
        by_id = {s["id"]: s for s in sections}
        self.assertIn("Terbaru", by_id)
        self.assertEqual(by_id["Terbaru"]["title"], "Baca Komik Terbaru")
        self.assertEqual(len(by_id["Terbaru"]["items"]), 3)
        item = by_id["Terbaru"]["items"][0]
        for field in ("judul", "url_img", "sinopsis", "detail_url"):
            self.assertIn(field, item)
        self.assertTrue(item["detail_url"].startswith("https://komiku.org/manga/"))
        self.assertNotIn("lazy", item["url_img"])

    def test_parse_rank_sections(self):
        soup, base = parse_fixture("komiku_home.html")
        sec = soup.select_one("section#Rekomendasi_Komik")
        panels = parse_rank_sections(sec, base)
        self.assertEqual(set(panels), {"harian", "mingguan"})
        self.assertEqual(panels["harian"][0]["rank"], 1)
        self.assertEqual(panels["harian"][0]["sub_section"], "harian")

    def test_missing_elements_skipped(self):
        html = "<main><section id='X'><h2>tanpa kartu</h2></section></main>"
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(parse_card_sections(soup, "https://komiku.org/"), [])


class TestDedupe(unittest.TestCase):
    def test_deduplicate_items(self):
        items = [
            {"judul": "A", "detail_url": "https://x/1/", "sinopsis": "", "url_img": "u1"},
            {"judul": "A", "detail_url": "https://x/1/", "sinopsis": "sinopsis A", "url_img": "u1"},
            {"judul": "B", "detail_url": "https://x/2/", "sinopsis": "sinopsis B", "url_img": "u2"},
        ]
        result, dupes = deduplicate_items(items)
        self.assertEqual(len(result), 2)
        self.assertEqual(dupes, 1)
        merged = next(i for i in result if i["detail_url"] == "https://x/1/")
        self.assertEqual(merged["sinopsis"], "sinopsis A")


class TestStorage(unittest.TestCase):
    def test_build_document_valid(self):
        sections = [
            {
                "title": "Baca Komik Terbaru",
                "items": [
                    {
                        "judul": "A",
                        "url_img": "https://img.komiku.org/a.webp",
                        "sinopsis": "s",
                        "detail_url": "https://komiku.org/manga/a/",
                        "section": "baca-komik-terbaru",
                        "section_title": "Baca Komik Terbaru",
                    }
                ],
            }
        ]
        doc = build_document(sections, "2026-09-17T00:00:00+00:00", "https://komiku.org/")
        self.assertEqual(doc["sections"][0]["id"], "baca-komik-terbaru")
        validate_document(doc)

    def test_build_document_rejects_empty(self):
        with self.assertRaises(ValueError):
            build_document([], "2026-09-17T00:00:00+00:00", "https://komiku.org/")

    def test_save_atomic(self):
        doc = {"schema_version": "0.2.0", "generated_at": "2026-09-17T00:00:00+00:00",
               "source": "https://komiku.org/", "sections": []}
        path = Path(self.id() + ".json")
        try:
            save_atomic(doc, path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), doc)
        finally:
            path.unlink(missing_ok=True)


class TestNormalize(unittest.TestCase):
    def test_normalize_url_detail(self):
        base = "https://komiku.org/"
        self.assertEqual(
            normalize_url("/manga/foo/", base, detail=True),
            "https://komiku.org/manga/foo/",
        )
        self.assertEqual(
            normalize_url("//komiku.org/manga/foo?x=1", base, detail=True),
            "https://komiku.org/manga/foo/",
        )
        self.assertEqual(normalize_url("javascript:alert(1)", base, detail=True), "")
        self.assertEqual(normalize_url("", base, detail=True), "")

    def test_section_id(self):
        self.assertEqual(section_id("Peringkat Komiku (harian)"), "peringkat-komiku-harian")


class TestCollect(unittest.TestCase):
    def test_collect_sections_stamps_and_excludes_rank_cards(self):
        soup, base = parse_fixture("komiku_home.html")
        sections = collect_sections(soup, base)
        titles = [s["title"] for s in sections]
        self.assertNotIn("Peringkat Komiku", titles)
        self.assertIn("Peringkat Komiku (harian)", titles)
        for section in sections:
            for item in section["items"]:
                self.assertIn("section", item)
                self.assertIn("section_title", item)


if __name__ == "__main__":
    unittest.main()

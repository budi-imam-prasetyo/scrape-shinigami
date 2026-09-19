"""Test enrichment sinopsis dari endpoint daftar (session tiruan, tanpa network)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from manhwa_scraper.http import HttpClient
from manhwa_scraper.parser import parse_detail_sinopsis
from manhwa_scraper.scraper import (
    blank_sinopsis_items,
    blank_sinopsis_urls,
    build_kategori_map,
    build_sinopsis_map,
    clear_placeholder_sinopsis,
    enrich_kategori,
    enrich_sinopsis,
    fill_from_detail_pages,
)
from main import scrape_list_pages
from test_http_pagination import (
    AlwaysFailSession,
    LIST_PAGE_1,
    LIST_PAGE_2,
    SequentialSession,
)

BASE = "https://komiku.org/"


def section(items):
    return [{"title": "S", "items": [dict(i) for i in items]}]


class TestSinopsisMap(unittest.TestCase):
    def test_build_map_skips_empty(self):
        items = [
            {"detail_url": "https://komiku.org/manga/a/", "sinopsis": "Sinopsis A"},
            {"detail_url": "https://komiku.org/manga/b/", "sinopsis": "  "},
            {"detail_url": "https://komiku.org/manga/c/", "sinopsis": ""},
        ]
        self.assertEqual(
            build_sinopsis_map(items, BASE),
            {"https://komiku.org/manga/a/": "Sinopsis A"},
        )

    def test_build_map_canonicalizes_urls(self):
        items = [
            {"detail_url": "/manga/a", "sinopsis": "S"},
            {"detail_url": "https://komiku.org/manga/b/?x=1", "sinopsis": "S"},
        ]
        result = build_sinopsis_map(items, BASE)
        self.assertIn("https://komiku.org/manga/a/", result)
        self.assertIn("https://komiku.org/manga/b/", result)


class TestKategoriMap(unittest.TestCase):
    def test_build_map_skips_invalid_and_empty(self):
        items = [
            {"detail_url": "https://komiku.org/manga/a/", "kategori": "Manhwa"},
            {"detail_url": "https://komiku.org/manga/b/", "kategori": "  "},
            {"detail_url": "https://komiku.org/manga/c/", "kategori": ".Unknown"},
            {"detail_url": " ", "kategori": "Manga"},
        ]
        self.assertEqual(
            build_kategori_map(items, BASE),
            {"https://komiku.org/manga/a/": "Manhwa"},
        )

    def test_enrich_fills_only_missing(self):
        sections = section([
            {"judul": "A", "detail_url": "https://komiku.org/manga/a/"},
            {"judul": "B", "detail_url": "https://komiku.org/manga/b/", "kategori": "Manhua"},
            {"judul": "C", "detail_url": "/manga/c/"},
        ])
        filled = enrich_kategori(
            sections,
            {"https://komiku.org/manga/a/": "Manga", "https://komiku.org/manga/c/": "Manhua"},
            BASE,
        )
        self.assertEqual(filled, 2)
        kats = {i["judul"]: i.get("kategori") for i in sections[0]["items"]}
        self.assertEqual(kats, {"A": "Manga", "B": "Manhua", "C": "Manhua"})


class TestPlaceholder(unittest.TestCase):
    def test_clear_placeholder_sinopsis(self):
        sections = section([
            {"judul": "A", "detail_url": "https://komiku.org/manga/a/", "sinopsis": "Belum ada isi."},
            {"judul": "B", "detail_url": "https://komiku.org/manga/b/", "sinopsis": "Nyata"},
        ])
        cleared = clear_placeholder_sinopsis(sections)
        self.assertEqual(cleared, 1)
        self.assertEqual(sections[0]["items"][0]["sinopsis"], "")
        self.assertEqual(sections[0]["items"][1]["sinopsis"], "Nyata")

    def test_build_map_skips_placeholder(self):
        items = [
            {"detail_url": "https://komiku.org/manga/a/", "sinopsis": "Belum ada isi."},
            {"detail_url": "https://komiku.org/manga/b/", "sinopsis": "Nyata"},
        ]
        self.assertEqual(
            build_sinopsis_map(items, BASE),
            {"https://komiku.org/manga/b/": "Nyata"},
        )

    def test_blank_urls_counts_placeholder_as_blank(self):
        sections = section([
            {"judul": "A", "detail_url": "https://komiku.org/manga/a/", "sinopsis": "Belum ada isi."},
        ])
        self.assertEqual(
            blank_sinopsis_urls(sections, BASE), {"https://komiku.org/manga/a/"}
        )


DETAIL_PAGE_DESC = """
<html><body><section id="Sinopsis"><h2>Sinopsis Lengkap Komik X</h2>
<div class="desc">Sinopsis dari elemen desc.</div></section></body></html>
"""
DETAIL_PAGE_P = """
<html><body><section id="Sinopsis"><h2>Sinopsis Lengkap Komik X</h2>
<p>Sinopsis dari paragraf.</p></section></body></html>
"""
DETAIL_PAGE_PLACEHOLDER = """
<html><body><section id="Sinopsis"><h2>Sinopsis Lengkap Komik X</h2>
<p>Belum ada isi.</p></section></body></html>
"""


class TestDetailFallback(unittest.TestCase):
    def test_parse_detail_sinopsis_desc(self):
        self.assertEqual(parse_detail_sinopsis(DETAIL_PAGE_DESC), "Sinopsis dari elemen desc.")

    def test_parse_detail_sinopsis_paragraph(self):
        self.assertEqual(parse_detail_sinopsis(DETAIL_PAGE_P), "Sinopsis dari paragraf.")

    def test_parse_detail_sinopsis_placeholder_and_missing(self):
        self.assertEqual(parse_detail_sinopsis(DETAIL_PAGE_PLACEHOLDER), "")
        self.assertEqual(parse_detail_sinopsis("<html><body>tanpa section</body></html>"), "")

    def test_fill_from_detail_pages(self):
        client = HttpClient(
            session=SequentialSession([DETAIL_PAGE_DESC, DETAIL_PAGE_DESC]),
            delay_range=(0, 0),
        )
        sections = section([
            {"judul": "A", "detail_url": "https://komiku.org/manga/a/", "sinopsis": ""},
            {"judul": "A-duplikat", "detail_url": "/manga/a/", "sinopsis": ""},
            {"judul": "B", "detail_url": "https://komiku.org/manga/b/", "sinopsis": ""},
        ])
        pairs = blank_sinopsis_items(sections, BASE)
        self.assertEqual(len(pairs), 2, "URL duplikat hanya di-request sekali")
        filled, failed = fill_from_detail_pages(sections, pairs, client, BASE)
        self.assertEqual((filled, failed), (3, 0))
        for item in sections[0]["items"]:
            self.assertEqual(item["sinopsis"], "Sinopsis dari elemen desc.")

    def test_fill_from_detail_pages_failure_counted(self):
        client = HttpClient(session=AlwaysFailSession(), max_retries=1, delay_range=(0, 0))
        sections = section([
            {"judul": "A", "detail_url": "https://komiku.org/manga/a/", "sinopsis": ""},
        ])
        filled, failed = fill_from_detail_pages(
            sections, blank_sinopsis_items(sections, BASE), client, BASE
        )
        self.assertEqual((filled, failed), (0, 1))


class TestEnrich(unittest.TestCase):
    def test_fills_only_blanks(self):
        sections = section([
            {"judul": "A", "detail_url": "https://komiku.org/manga/a/", "sinopsis": ""},
            {"judul": "B", "detail_url": "https://komiku.org/manga/b/", "sinopsis": "Tetap"},
            {"judul": "C", "detail_url": "https://komiku.org/manga/c/", "sinopsis": ""},
        ])
        filled = enrich_sinopsis(
            sections, {"https://komiku.org/manga/a/": "Baru A"}, BASE
        )
        self.assertEqual(filled, 1)
        items = sections[0]["items"]
        self.assertEqual(items[0]["sinopsis"], "Baru A")
        self.assertEqual(items[1]["sinopsis"], "Tetap")
        self.assertEqual(items[2]["sinopsis"], "")

    def test_matches_relative_urls(self):
        sections = section([
            {"judul": "A", "detail_url": "/manga/a/", "sinopsis": ""},
        ])
        filled = enrich_sinopsis(
            sections, {"https://komiku.org/manga/a/": "S"}, BASE
        )
        self.assertEqual(filled, 1)
        self.assertEqual(sections[0]["items"][0]["sinopsis"], "S")

    def test_blank_urls(self):
        sections = section([
            {"judul": "A", "detail_url": "https://komiku.org/manga/a/", "sinopsis": ""},
            {"judul": "B", "detail_url": "https://komiku.org/manga/b/", "sinopsis": "Ada"},
        ])
        self.assertEqual(
            blank_sinopsis_urls(sections, BASE), {"https://komiku.org/manga/a/"}
        )

    def test_end_to_end_with_list_pages(self):
        page2 = LIST_PAGE_2.replace("<p></p>", "<p>Sinopsis C</p>")
        client = HttpClient(
            session=SequentialSession([LIST_PAGE_1, page2]), delay_range=(0, 0)
        )
        sections = section([
            {"judul": "A", "detail_url": "https://komiku.org/manga/a/", "sinopsis": ""},
            {"judul": "C", "detail_url": "https://komiku.org/manga/c/", "sinopsis": ""},
        ])
        blanks = blank_sinopsis_urls(sections, BASE)
        pages, failed = scrape_list_pages(client, max_pages=5, need=blanks)
        self.assertEqual(failed, 0)
        filled = enrich_sinopsis(sections, build_sinopsis_map(pages, BASE), BASE)
        self.assertEqual(filled, 2)
        got = {i["judul"]: i["sinopsis"] for i in sections[0]["items"]}
        self.assertEqual(got, {"A": "Sinopsis A", "C": "Sinopsis C"})


class TestEarlyStop(unittest.TestCase):
    def test_stops_when_need_satisfied(self):
        sessions = SequentialSession([LIST_PAGE_1, LIST_PAGE_2])
        client = HttpClient(session=sessions, delay_range=(0, 0))
        items, _ = scrape_list_pages(
            client, max_pages=5,
            need={"https://komiku.org/manga/a/", "https://komiku.org/manga/b/"},
        )
        self.assertEqual([i["judul"] for i in items], ["Judul A", "Judul B"])
        self.assertEqual(len(sessions.pages), 1, "halaman 2 tidak boleh di-fetch")


if __name__ == "__main__":
    unittest.main()

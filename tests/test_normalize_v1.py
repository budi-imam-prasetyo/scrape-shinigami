"""Unit test modul normalize (transformasi field API Shinigami).

Version: 1.0.0
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from manhwa_scraper import normalize as n

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class TestCleanText(unittest.TestCase):
    def test_clean_text_normalizes_whitespace(self):
        self.assertEqual(n.clean_text("  a\n\t b  "), "a b")
        self.assertEqual(n.clean_text(None), "")
        self.assertEqual(n.clean_text(""), "")


class TestSafeUrl(unittest.TestCase):
    def test_only_http_https(self):
        self.assertEqual(n.safe_url("https://a.io/x.jpg"), "https://a.io/x.jpg")
        self.assertEqual(n.safe_url("http://a.io/x"), "http://a.io/x")
        self.assertEqual(n.safe_url("javascript:alert(1)"), "")
        self.assertEqual(n.safe_url("ftp://a.io"), "")
        self.assertEqual(n.safe_url("https://user:pass@a.io/"), "")


class TestNumberParse(unittest.TestCase):
    def test_parse_int(self):
        self.assertEqual(n.parse_int(5), 5)
        self.assertEqual(n.parse_int("2019"), 2019)
        self.assertEqual(n.parse_int("abc"), None)
        self.assertEqual(n.parse_int(None), None)

    def test_parse_float(self):
        self.assertEqual(n.parse_float(8.6), 8.6)
        self.assertEqual(n.parse_float("8.6"), 8.6)
        self.assertEqual(n.parse_float("4,5/5"), 4.5)


class TestMappings(unittest.TestCase):
    def test_status_label(self):
        self.assertEqual(n.status_label(1), "Ongoing")
        self.assertEqual(n.status_label(2), "Completed")
        self.assertEqual(n.status_label(99), "")

    def test_country_type(self):
        self.assertEqual(n.country_type("KR"), "Manhwa")
        self.assertEqual(n.country_type("CN"), "Manhua")
        self.assertEqual(n.country_type("JP"), "Manga")
        self.assertEqual(n.country_type("XX"), "")


class TestNormalizeMangaItem(unittest.TestCase):
    def test_full_item_from_detail(self):
        raw = load_fixture("detail_demonic.json")["data"]
        item = n.normalize_manga_item(raw)
        self.assertEqual(item["id"], raw["manga_id"])
        self.assertTrue(item["judul"])
        self.assertTrue(item["url_img"].startswith("https://"))
        self.assertTrue(
            item["detail_url"].startswith("https://11.shinigami.asia/series/")
        )
        self.assertIn("genre", item)
        self.assertIn("author", item)
        self.assertEqual(item["kategori"], "Manhua")
        self.assertEqual(item["status"], "Ongoing")
        self.assertEqual(item["rating"], 8.6)

    def test_country_id_empty_list_is_handled(self):
        # Kasus nyata: beberapa judul mengirim country_id sebagai list kosong.
        item = n.normalize_manga_item(
            {"title": "Y", "manga_id": "abc", "country_id": []}
        )
        self.assertEqual(item["kategori"], "")
        item2 = n.normalize_manga_item(
            {"title": "Z", "manga_id": "def", "country_id": ["KR"]}
        )
        self.assertEqual(item2["kategori"], "Manhwa")

    def test_missing_fields_produce_empties(self):
        raw = {"title": "X"}  # nyaris kosong
        item = n.normalize_manga_item(raw)
        self.assertEqual(item["id"], "")
        self.assertEqual(item["sinopsis"], "")
        self.assertEqual(item["kategori"], "")
        self.assertEqual(item["status"], "")
        self.assertNotIn("genre", item)  # opsional tak muncul jika kosong

    def test_internal_field_added_when_chapter_present(self):
        raw = {"title": "Y", "latest_chapter_id": "abc-123"}
        item = n.normalize_manga_item(raw)
        self.assertEqual(item["_waline_path"], "chapter/abc-123")

    def test_judul_alternatif_optional(self):
        item = n.normalize_manga_item({"title": "Z", "alternative_title": "Alt"})
        self.assertEqual(item.get("judul_alternatif"), "Alt")
        item2 = n.normalize_manga_item({"title": "Z2"})
        self.assertNotIn("judul_alternatif", item2)


class TestNormalizeDetail(unittest.TestCase):
    def test_extract_taxonomy(self):
        raw = load_fixture("detail_demonic.json")["data"]
        d = n.normalize_detail(raw, raw["manga_id"])
        self.assertIn("genre", d)
        self.assertIn("author", d)
        self.assertIsInstance(d["genre"], list)


if __name__ == "__main__":
    unittest.main()

"""Unit test storage: schema, validasi, build document, atomic write.

Version: 1.0.0
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from manhwa_scraper.storage import (
    SCHEMA_VERSION,
    build_document,
    save_atomic,
    validate_document,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def sample_item():
    return {
        "id": "abc",
        "judul": "Contoh",
        "detail_url": "https://11.shinigami.asia/series/abc",
        "url_img": "https://assets.shngm.id/x.jpg",
        "sinopsis": "Deskripsi.",
        "kategori": "Manhwa",
        "status": "Ongoing",
    }


class TestBuildDocument(unittest.TestCase):
    def test_valid_document(self):
        sections = [{"title": "Terbaru", "items": [sample_item()]}]
        doc = build_document(
            sections, "2026-09-21T00:00:00+00:00", "https://11.shinigami.asia"
        )
        self.assertEqual(doc["schema_version"], SCHEMA_VERSION)
        self.assertEqual(doc["sections"][0]["id"], "terbaru")
        validate_document(doc)  # no raise

    def test_rejects_malformed_section(self):
        with self.assertRaises((ValueError, KeyError)):
            build_document([{"title": "X"}], "2026-09-21T00:00:00Z", "src")

    def test_rejects_empty_sections(self):
        with self.assertRaises(ValueError):
            build_document([], "2026-09-21T00:00:00Z", "src")

    def test_rejects_internal_field(self):
        item = sample_item()
        item["_waline_path"] = "chapter/x"
        sections = [{"title": "T", "items": [item]}]
        with self.assertRaises(ValueError):
            build_document(sections, "t", "src")


class TestSaveAtomic(unittest.TestCase):
    def test_roundtrip(self):
        doc = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": "2026-09-21T00:00:00+00:00",
            "source": "https://11.shinigami.asia",
            "sections": [
                {"id": "terbaru", "title": "Terbaru", "items": [sample_item()]}
            ],
        }
        path = Path(self.id()).with_suffix(".json")
        try:
            save_atomic(doc, path)
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(written, doc)
        finally:
            path.unlink(missing_ok=True)


class TestRealItemValidates(unittest.TestCase):
    def test_detail_item_passes_schema(self):
        # Item asli hasil normalisasi harus lolos schema (regresi penting).
        from manhwa_scraper.normalize import normalize_manga_item

        raw = load_fixture("detail_demonic.json")["data"]
        item = normalize_manga_item(raw)
        item.pop("_waline_path", None)
        item.pop("_raw_manga_id", None)
        sections = [{"title": "Top", "items": [item]}]
        build_document(sections, "2026-09-21T00:00:00Z", "https://11.shinigami.asia")


if __name__ == "__main__":
    unittest.main()

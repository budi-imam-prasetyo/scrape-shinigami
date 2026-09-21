"""Unit test parser komentar Waline (fallback scraping/JSON).

Version: 1.0.0
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from manhwa_scraper.parser import parse_comments_payload

FIXTURES = Path(__file__).parent / "fixtures"


class TestParseComments(unittest.TestCase):
    def test_real_fixture(self):
        payload = json.loads((FIXTURES / "waline_comments.json").read_text(encoding="utf-8"))
        out = parse_comments_payload(payload, limit=10)
        self.assertGreater(len(out), 0)
        for c in out:
            self.assertIn("username", c)
            self.assertIn("isi", c)
            self.assertTrue(c["username"])
            self.assertTrue(c["isi"])

    def test_invalid_payload(self):
        self.assertEqual(parse_comments_payload(None), [])
        self.assertEqual(parse_comments_payload({"data": "x"}), [])

    def test_skips_empty_comment(self):
        payload = {
            "data": [
                {"nick": "A", "comment": "<p>Oke</p>", "objectId": 1},
                {"nick": "B", "comment": "", "objectId": 2},
                {"nick": "", "comment": "<p>anon</p>", "objectId": 3},
            ]
        }
        out = parse_comments_payload(payload)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["username"], "A")
        self.assertEqual(out[0]["isi"], "Oke")

    def test_strips_html(self):
        payload = {"data": [{"nick": "N", "comment": "<p>Halo <b>dunia</b><br>baris</p>", "objectId": 9}]}
        out = parse_comments_payload(payload)
        self.assertEqual(out[0]["isi"], "Halo dunia baris")

    def test_date_from_insertedAt(self):
        payload = {"data": [{"nick": "N", "comment": "c", "insertedAt": "2026-09-21 05:03:58"}]}
        out = parse_comments_payload(payload)
        self.assertEqual(out[0]["tanggal"], "2026-09-21")

    def test_limit_applied(self):
        data = [{"nick": f"u{i}", "comment": "c", "objectId": i} for i in range(20)]
        out = parse_comments_payload({"data": data}, limit=10)
        self.assertEqual(len(out), 10)


if __name__ == "__main__":
    unittest.main()
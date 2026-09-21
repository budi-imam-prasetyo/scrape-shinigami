"""Test enrichment — versi 1.0.0.

Enrichment sinopsis/kategori versi Komiku (endpoint daftar HTML + fallback
halaman detail) sudah usang pada migrasi ke API JSON Shinigami, di mana
semua field metadata (judul, sinopsis, kategori, genre, rating, author,
artist) sudah tersedia penuh di payload `/manga/list` dan `/manga/detail`.

Suite ini didelegasikan ke test normalisasi & scraper v1 agar behavior
enrichment terbaru (merge detail + strip internal) tetap teruji.
"""

from test_scraper_v1 import (
    TestDeduplicate,
    TestScraper,
    TestStripInternal,
)

__all__ = ["TestDeduplicate", "TestScraper", "TestStripInternal"]

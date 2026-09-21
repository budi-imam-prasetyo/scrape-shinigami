"""Orkestrasi pengambilan data dari JSON API Shinigami.

Version: 1.0.0

Tugas utama modul ini:
1. Mengambil halaman manga (list/top) dari API JSON Shinigami.
2. Menormalisasi tiap item lewat `normalize.normalize_manga_item`.
3. Me-merge item yang sama yang muncul di beberapa section (dedup):
   karena `manga/top` mengabaikan taxonomy dan field tambahan, item yang
   berdampingan diisi dari `manga/detail` bila diperlukan.
4. Mengambil komentar (Waline) secara opsional untuk chapter terbaru.

Catatan konfigurasi (hasil verifikasi struktur, lihat README bagian
"Struktur API"):
- `manga/top` mengabaikan parameter sort/type dan mengembalikan 10 item
  teratas yang sama.
- Hanya `sort` = latest / rating / bookmark yang valid.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from .config import (
    API_BASE,
    ENDPOINT_MANGA_DETAIL,
    ENDPOINT_MANGA_LIST,
    ENDPOINT_MANGA_TOP,
    LIST_PAGES,
    MAX_PAGE_SIZE,
)
from .http import ApiClient
from .normalize import normalize_detail, normalize_manga_item
from .parser import parse_comments_payload

LOGGER = logging.getLogger(__name__)


class RequestClient(Protocol):
    """Kontrak minimal klien HTTP yang dipakai scraper (mendukung stub)."""

    def get_json(self, url: str, params: dict[str, Any] | None = ...) -> Any: ...

    def polite_delay(self) -> None: ...


# URL tempat waline komentar user disimpan.
WALINE_BASE = "https://commento.shngm.io/comment"

# Section title default bila fungsi dipakai tanpa argumen section.
SECTION_DEFAULT = "Manhwa Terbaru"


class ShinigamiScraper:
    def __init__(self, client: RequestClient | None = None) -> None:
        self.client = client or ApiClient()

    # ---------------------------------------------------------------- helper
    def _get_data(self, path: str, params: dict[str, Any] | None = None) -> list[dict]:
        """GET endpoint API, kembalikan `data` list (atan [] bila kosong)."""
        payload = self.client.get_json(API_BASE + path, params=params)
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        return data if isinstance(data, list) else []

    def _detail_map(self, manga_ids: list[str]) -> dict[str, dict]:
        """Ambil taxonomy dari manga/detail untuk id yang belum punya genre."""
        need = [mid for mid in manga_ids if mid]
        result: dict[str, dict] = {}
        for mid in need:
            try:
                payload = self.client.get_json(
                    API_BASE + ENDPOINT_MANGA_DETAIL.format(manga_id=mid)
                )
                detail = payload.get("data") if isinstance(payload, dict) else None
                if isinstance(detail, dict):
                    result[mid] = normalize_detail(detail, mid)
            except Exception as error:  # noqa: BLE001
                LOGGER.warning("Detail gagal untuk %s: %s", mid, error)
            self.client.polite_delay()
        return result

    # --------------------------------------------------------------- fixtures
    def fetch_top(self) -> list[dict]:
        """Ranking teratas (manga/top). Item dari sini tidak membawa taxonomy."""
        raw = self._get_data(ENDPOINT_MANGA_TOP, {"page": 1, "page_size": 10})
        items = [normalize_manga_item(r) for r in raw if isinstance(r, dict)]
        # Lenkapi genre/author via detail (top tidak punya taxonomy).
        detail = self._detail_map([it["id"] for it in items])
        for it in items:
            it.update(detail.get(it["id"], {}))
        return items

    def _fetch_list_pages(
        self, sort: str, pages: int = LIST_PAGES, page_size: int = MAX_PAGE_SIZE
    ) -> list[dict]:
        """Gabung beberapa halaman manga/list untuk satu sort."""
        raw: list[dict] = []
        for page in range(1, pages + 1):
            items = self._get_data(
                ENDPOINT_MANGA_LIST,
                {
                    "page": page,
                    "page_size": page_size,
                    "sort": sort,
                    "sort_order": "desc",
                },
            )
            raw.extend(items)
            if len(items) < page_size:
                break  # halaman terakhir
        return raw

    def fetch_latest(self, pages: int = 1, page_size: int = MAX_PAGE_SIZE) -> list[dict]:
        raw = self._fetch_list_pages("latest", pages=pages, page_size=page_size)
        return [normalize_manga_item(r) for r in raw if isinstance(r, dict)]

    def fetch_rating(self, pages: int = 1, page_size: int = MAX_PAGE_SIZE) -> list[dict]:
        raw = self._fetch_list_pages("rating", pages=pages, page_size=page_size)
        return [normalize_manga_item(r) for r in raw if isinstance(r, dict)]

    # ------------------------------------------------------------- komentar
    def fetch_comments(self, manga: dict[str, Any], limit: int = 10) -> list[dict]:
        """Komentar user untuk chapter terbaru manga.

        Waline mengelompokkan komentar per chapter ('chapter/<id>'). Kita
        ambil untuk chapter terbaru saja supaya request minimal; jika tidak
        ada path atau gagal, kembalikan [].
        """
        path = manga.get("_waline_path") or manga.get("_raw_manga_id")
        if not path:
            return []
        try:
            payload = self.client.get_json(
                WALINE_BASE, params={"path": path, "page": 1, "pageSize": limit}
            )
        except Exception as error:  # noqa: BLE001
            LOGGER.warning("Komentar gagal untuk %s: %s", manga.get("id"), error)
            return []
        return parse_comments_payload(payload, limit=limit)

    # ----------------------------------------------------------- fitur utama
    def scrape_section(
        self, kind: str = "latest", pages: int = LIST_PAGES
    ) -> list[dict]:
        """Ambil satu section (latest/rating/top) dengan dedup + enrich.

        - kind = 'latest'  : manga/list sort=latest (section default).
        - kind = 'rating'  : manga/list sort=rating.
        - kind = 'top'     : manga/top (enrich via detail; selalu 10 item).
        """
        if kind == "top":
            return self.fetch_top()
        if kind == "rating":
            items = self.fetch_rating(pages=pages)
        else:
            items = self.fetch_latest(pages=pages)
        items, _dups = deduplicate_items(items)
        return items


# ------------------------------------------------------------------ utilitas
def merge_detail_into_item(
    item: dict[str, Any], detail: dict[str, Any]
) -> dict[str, Any]:
    """Isi field yang kosong di item dari vocabulary detail (non-destructif)."""
    merged = dict(item)
    for key in ("genre", "author", "artist", "format", "tipe"):
        if not merged.get(key) and detail.get(key):
            merged[key] = detail[key]
    return merged


def deduplicate_items(items: list[dict]) -> tuple[list[dict], int]:
    """Dedup berdasarkan `id` dalam satu kumpulan item.

    Kalau API mengirim item yang sama dua kali dalam satu respons (jarang),
    item pertama menang dan field kosong diisi dari item berikutnya yang
    sama. Catatan: ini dedup *dalam* satu section — bukan antar-section;
    setiap section tetap utuh dan independen di output.
    """
    result: dict[str, dict] = {}
    duplicates = 0
    for item in items:
        mid = item.get("id")
        if not mid:
            continue
        if mid in result:
            duplicates += 1
            for key, value in item.items():
                if key == "id":
                    continue
                if not result[mid].get(key) and value:
                    result[mid][key] = value
        else:
            result[mid] = dict(item)
    return list(result.values()), duplicates


def strip_internal(item: dict[str, Any]) -> dict[str, Any]:
    """Buang field yang diawali `_` (internal, bukan skema output)."""
    return {k: v for k, v in item.items() if not k.startswith("_")}


def attach_comments(
    scraper: ShinigamiScraper, sections: list[dict], limit: int = 10
) -> int:
    """Isi `komentar` pada tiap item yang memilikinya. Opsional: hanya
    ambil saat request tidak berlebihan. Kembalikan jumlah item dengan
    komentar ter-attach.

    Hasil komentar di-cache per `id` dalam satu run: bila item yang sama
    muncul di beberapa section (`--kinds top,latest,rating`), komentarnya
    hanya diambil sekali, lalu disalin ke kemunculan lain. Ini menghindari
    duplicate request ke Waline.
    """
    cache: dict[str, list[dict]] = {}
    touched = 0
    for section in sections:
        for item in section.get("items", []):
            if item.get("_waline_path") or item.get("_raw_manga_id"):
                item_id = item.get("id")
                if item_id in cache:
                    if cache[item_id]:
                        item["komentar"] = cache[item_id]
                        touched += 1
                else:
                    comments = scraper.fetch_comments(item, limit=limit)
                    cache[item_id] = comments
                    if comments:
                        item["komentar"] = comments
                        touched += 1
            scraper.client.polite_delay()
    return touched


def build_sections(
    scraper: ShinigamiScraper,
    kinds: list[str] | None = None,
    with_comments: bool = False,
) -> list[dict]:
    """Bangun daftar section final untuk dokumen output.

    kinds: subset ['top', 'latest', 'rating']. Dengan `with_comments=True`,
    setiap item di-enrich komentar dari chapter terbarunya (satu request
    per item). Field internal (diawali `_`) dibuang sebelum output.
    """
    if not kinds:
        kinds = ["top", "latest", "rating"]
    titles = {
        "top": "Peringkat Teratas",
        "latest": "Terbaru",
        "rating": "Rating Tertinggi",
    }
    sections: list[dict] = []
    for kind in kinds:
        items = scraper.scrape_section(kind)
        sections.append({"title": titles[kind], "items": items})

    if with_comments:
        attach_comments(scraper, sections)

    for section in sections:
        section["items"] = [strip_internal(i) for i in section["items"]]
    return sections

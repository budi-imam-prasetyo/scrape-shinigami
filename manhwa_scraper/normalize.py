"""Normalisasi dan transformasi data dari API Shinigami ke skema internal.

Version: 1.0.0

Field dari API tidak langsung ditulis ke output. Setiap field melewati
transformasi di sini supaya:
- URL dijamin hanya http/https (validasi ketat).
- Nilai string dibersihkan (whitespace ganda, strip).
- Field opsional tidak pernah menghasilkan key dengan nilai kosong.
- Status integer API dipetakan ke label human-readable.
- Duplikasi antar variabel (manga_id UUID vs id numerik) dipilih satu.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from .config import COUNTRY_LABELS, STATUS_LABELS, series_url

# API kadang menaruh deskripsi kosong/placeholder.
DESCRIPTION_PLACEHOLDER = re.compile(
    r"^(belum ada isi\.?|tidak ada deskripsi\.?)$", re.IGNORECASE
)


def clean_text(value: Any) -> str:
    """Normalisasi whitespace dan strip; none -> empty string."""
    return " ".join(str(value or "").split())


def is_real_description(value: Any) -> bool:
    text = clean_text(value)
    return bool(text) and not DESCRIPTION_PLACEHOLDER.match(text)


def safe_url(value: Any) -> str:
    """Hanya kembalikan URL http/https yang valid; selain itu kosong."""
    text = clean_text(value)
    if not text:
        return ""
    parsed = urlsplit(text)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    if parsed.username or parsed.password:
        return ""
    return text


def parse_float(value: Any) -> float | None:
    """Parse angka desimal ('8.6', 8.6, '4.5/5') -> float atau None."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = clean_text(value)
    match = re.search(r"\d+(?:[.,]\d+)?", text)
    return float(match.group(0).replace(",", ".")) if match else None


def parse_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    text = clean_text(value)
    match = re.search(r"-?\d+", text)
    return int(match.group(0)) if match else None


def parse_iso_date(value: Any) -> str:
    """ISO 8601 datetime -> tanggal 'YYYY-MM-DD' (bagian waktu dibuang)."""
    text = clean_text(value)
    if not text:
        return ""
    # API memakai format '2026-09-21T02:38:55Z'
    m = re.match(r"(\d{4}-\d{2}-\d{2})", text)
    return m.group(1) if m else ""


def status_label(value: Any) -> str:
    """Petakan integer status API ke label; kosong kalau tak dikenal."""
    num = parse_int(value)
    if num is None:
        return ""
    return STATUS_LABELS.get(num, "")


def country_type(value: Any) -> str:
    """Petakan kode negara ke tipe komik (Manhwa/Manhua/Manga)."""
    code = clean_text(value).upper()
    return COUNTRY_LABELS.get(code, "")


def _taxonomy_names(taxonomy: Mapping[str, Any], key: str) -> list[str]:
    """Daftar nama dari satu grup taxonomy ('Genre', 'Author', 'Artist')."""
    group = taxonomy.get(key) if isinstance(taxonomy, dict) else None
    if not isinstance(group, list):
        return []
    names = []
    for entry in group:
        if isinstance(entry, dict):
            name = clean_text(entry.get("name"))
            if name and name not in names:
                names.append(name)
    return names


def normalize_manga_item(raw: Mapping[str, Any]) -> dict:
    """Transformasi satu item manga (dari list/detail/top) ke model internal.

    Menghasilkan dict yang PASTI punya field wajib (juga saat raw tidak
    lengkap), dan field opsional hanya muncul bila nilainya ada. Ini
    membuat skema output konsisten dan tahan terhadap data yang berubah.
    """
    manga_id = clean_text(raw.get("manga_id") or raw.get("id"))
    title = clean_text(raw.get("title"))
    raw_tax = raw.get("taxonomy")
    taxonomy: dict[str, Any] = raw_tax if isinstance(raw_tax, dict) else {}
    genres = _taxonomy_names(taxonomy, "Genre")

    item: dict[str, Any] = {
        "id": manga_id,
        "judul": title,
        "detail_url": series_url(manga_id),
        "url_img": safe_url(raw.get("cover_image_url")),
        "url_img_portrait": safe_url(raw.get("cover_portrait_url")),
        "sinopsis": clean_text(raw.get("description")),
        "kategori": country_type(raw.get("country_id")),
        "status": status_label(raw.get("status")),
        "tahun": parse_int(raw.get("release_year")),
        "rating": parse_float(raw.get("user_rate")),
        "views": parse_int(raw.get("view_count")),
        "bookmark_count": parse_int(raw.get("bookmark_count")),
        "rank": parse_int(raw.get("rank")),
        "genre": genres,
        "author": _taxonomy_names(taxonomy, "Author"),
        "artist": _taxonomy_names(taxonomy, "Artist"),
        "format": _taxonomy_names(taxonomy, "Format"),
        "tipe": _taxonomy_names(taxonomy, "Type"),
        "updated_at": parse_iso_date(
            raw.get("latest_chapter_time") or raw.get("updated_at")
        ),
        "chapter_terbaru": parse_int(raw.get("latest_chapter_number")),
        "mutakhir": raw.get("is_recommended") is True,
    }

    alt = clean_text(raw.get("alternative_title"))
    if alt:
        item["judul_alternatif"] = alt

    # Path waline komentar (internal, tidak diekspor ke skema)
    chapter_uuid = clean_text(raw.get("latest_chapter_id"))
    if chapter_uuid:
        item["_waline_path"] = f"chapter/{chapter_uuid}"
        item["_raw_manga_id"] = manga_id

    # Hapus field yang nilainya kosong default (supaya output bersih).
    for key in (
        "url_img_portrait",
        "judul_alternatif",
        "genre",
        "author",
        "artist",
        "format",
        "tipe",
        "mutakhir",
        "updated_at",
        "chapter_terbaru",
    ):
        val = item.get(key)
        if val in (None, "", [], False):
            item.pop(key, None)

    return item


def normalize_detail(detail: Mapping[str, Any], manga_id: str) -> dict:
    """Halaman detail: kembalikan vocabulary tambahan yang tersedia di
    manga/detail. Dipakai untuk memperkaya item yang tipis (dari manga/top)
    yang tidak membawa taxonomy."""
    out: dict[str, Any] = {}
    raw_tax = detail.get("taxonomy")
    taxonomy: dict[str, Any] = raw_tax if isinstance(raw_tax, dict) else {}
    genres = _taxonomy_names(taxonomy, "Genre")
    if genres:
        out["genre"] = genres
    authors = _taxonomy_names(taxonomy, "Author")
    if authors:
        out["author"] = authors
    artists = _taxonomy_names(taxonomy, "Artist")
    if artists:
        out["artist"] = artists
    formats = _taxonomy_names(taxonomy, "Format")
    if formats:
        out["format"] = formats
    types = _taxonomy_names(taxonomy, "Type")
    if types:
        out["tipe"] = types
    return out


def section_id(title):
    return re.sub(r"[^\w]+", "-", clean_text(title).casefold()).strip("-")

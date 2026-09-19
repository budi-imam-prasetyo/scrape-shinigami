"""Penggabungan hasil parsing menjadi section final + deduplication.

Version: 0.2.2
"""

import logging

from .normalize import is_real_sinopsis, normalize_url, section_id
from .parser import parse_detail_kategori, parse_detail_sinopsis

LOGGER = logging.getLogger(__name__)

RANK_SECTION_TITLE = "Peringkat Komiku"


def stamp_section(items, section_title):
    result = []
    for item in items:
        item = dict(item)
        item["section"] = section_id(section_title)
        item["section_title"] = section_title
        result.append(item)
    return result


def collect_sections(soup, base_url):
    from .parser import parse_card_sections, parse_rank_sections

    sections = []
    for sec in parse_card_sections(soup, base_url):
        if sec["id"] == "Rekomendasi_Komik":
            continue
        sections.append(
            {"title": sec["title"], "items": stamp_section(sec["items"], sec["title"])}
        )

    for element in soup.select("main section#Rekomendasi_Komik"):
        for panel_name, items in parse_rank_sections(element, base_url).items():
            title = f"{RANK_SECTION_TITLE} ({panel_name})"
            sections.append({"title": title, "items": stamp_section(items, title)})
    return sections


def deduplicate_items(items):
    result = {}
    duplicates = 0
    for item in items:
        detail_url = item["detail_url"]
        if detail_url in result:
            duplicates += 1
            for key, value in item.items():
                if key in {"section", "section_title", "rank", "sub_section"}:
                    continue
                if not result[detail_url].get(key) and value:
                    result[detail_url][key] = value
        else:
            result[detail_url] = dict(item)
    return list(result.values()), duplicates


def canonical_detail_url(value, base_url):
    return normalize_url(value, base_url, detail=True)


def build_sinopsis_map(items, base_url):
    """Petakan canonical detail_url -> sinopsis (hanya sinopsis riil)."""
    result = {}
    for item in items:
        key = canonical_detail_url(item.get("detail_url", ""), base_url)
        sinopsis = (item.get("sinopsis") or "").strip()
        if key and is_real_sinopsis(sinopsis) and key not in result:
            result[key] = sinopsis
    return result


def blank_sinopsis_urls(sections, base_url):
    """Kumpulan canonical detail_url dari item yang sinopsisnya masih kosong."""
    blanks = set()
    for section in sections:
        for item in section.get("items", []):
            if not is_real_sinopsis(item.get("sinopsis")):
                key = canonical_detail_url(item.get("detail_url", ""), base_url)
                if key:
                    blanks.add(key)
    return blanks


def enrich_sinopsis(sections, sinopsis_map, base_url):
    """Isi sinopsis kosong/placeholder dari peta endpoint daftar."""
    filled = 0
    for section in sections:
        for item in section.get("items", []):
            if is_real_sinopsis(item.get("sinopsis")):
                continue
            key = canonical_detail_url(item.get("detail_url", ""), base_url)
            if key and key in sinopsis_map:
                item["sinopsis"] = sinopsis_map[key]
                filled += 1
    if filled:
        LOGGER.info("Enrichment sinopsis: %d item terisi", filled)
    return filled


def clear_placeholder_sinopsis(sections):
    """Kosongkan sinopsis placeholder situs (mis. "Belum ada isi.")."""
    cleared = 0
    for section in sections:
        for item in section.get("items", []):
            sinopsis = (item.get("sinopsis") or "").strip()
            if sinopsis and not is_real_sinopsis(sinopsis):
                item["sinopsis"] = ""
                cleared += 1
    if cleared:
        LOGGER.info("%d sinopsis placeholder dikosongkan", cleared)
    return cleared


def blank_sinopsis_items(sections, base_url):
    """Pasangan (detail_url, judul) dari item yang sinopsisnya masih kosong."""
    pairs = []
    seen = set()
    for section in sections:
        for item in section.get("items", []):
            if is_real_sinopsis(item.get("sinopsis")):
                continue
            key = canonical_detail_url(item.get("detail_url", ""), base_url)
            if key and key not in seen:
                seen.add(key)
                pairs.append((key, item.get("judul", "")))
    return pairs


def fill_from_detail_pages(sections, pairs, client, base_url):
    """Fallback terakhir: ambil sinopsis dari halaman detail per item.

    Dipakai untuk item peringkat/populer yang tidak muncul di halaman awal
    endpoint daftar. Jumlah request dibatasi jumlah item yang masih kosong.
    Sinopsis sekaligus kategori (dari tabel metadata) diambil dari halaman
    yang sama agar tidak ada request kedua.
    """
    filled = 0
    kategori_filled = 0
    failed = 0
    for detail_url, judul in pairs:
        try:
            html = client.get(detail_url)
        except Exception as error:
            LOGGER.warning("Halaman detail fallback gagal untuk %s: %s", detail_url, error)
            failed += 1
            continue
        key = canonical_detail_url(detail_url, base_url)
        targets = [
            item
            for section in sections
            for item in section.get("items", [])
            if canonical_detail_url(item.get("detail_url", ""), base_url) == key
        ]
        sinopsis = parse_detail_sinopsis(html)
        if sinopsis:
            for item in targets:
                if not is_real_sinopsis(item.get("sinopsis")):
                    item["sinopsis"] = sinopsis
                    filled += 1
            LOGGER.info("Sinopsis dari halaman detail: %s", judul or detail_url)
        kategori = parse_detail_kategori(html)
        if kategori:
            for item in targets:
                if not (item.get("kategori") or "").strip():
                    item["kategori"] = kategori
                    kategori_filled += 1
        client.polite_delay()
    if filled or kategori_filled or failed:
        LOGGER.info(
            "Fallback halaman detail: %d sinopsis terisi, %d kategori terisi, %d gagal",
            filled,
            kategori_filled,
            failed,
        )
    return filled, failed


def build_kategori_map(items, base_url):
    """Petakan canonical detail_url -> kategori (hanya nilai valid)."""
    result = {}
    for item in items:
        key = canonical_detail_url(item.get("detail_url", ""), base_url)
        kategori = (item.get("kategori") or "").strip()
        if key and kategori in {"Manga", "Manhwa", "Manhua"} and key not in result:
            result[key] = kategori
    return result


def enrich_kategori(sections, kategori_map, base_url):
    """Isi kategori yang belum ada dari peta endpoint daftar. Kembalikan jumlah."""
    filled = 0
    for section in sections:
        for item in section.get("items", []):
            if (item.get("kategori") or "").strip():
                continue
            key = canonical_detail_url(item.get("detail_url", ""), base_url)
            if key and key in kategori_map:
                item["kategori"] = kategori_map[key]
                filled += 1
    if filled:
        LOGGER.info("Enrichment kategori: %d item terisi", filled)
    return filled


def deduplicate_sections(sections):
    result = []
    total_duplicates = 0
    for section in sections:
        items, duplicates = deduplicate_items(section["items"])
        if duplicates:
            LOGGER.info("Section %s: %d duplikat dihapus", section["title"], duplicates)
        result.append({**section, "items": items})
        total_duplicates += duplicates
    return result, total_duplicates

"""CLI entry point scraper section Komiku.

Version: 0.2.2
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from manhwa_scraper.http import HttpClient
from manhwa_scraper.normalize import clean_text, normalize_url
from manhwa_scraper.scraper import (
    blank_sinopsis_items,
    blank_sinopsis_urls,
    build_kategori_map,
    build_sinopsis_map,
    clear_placeholder_sinopsis,
    collect_sections,
    deduplicate_sections,
    enrich_kategori,
    enrich_sinopsis,
    fill_from_detail_pages,
)
from manhwa_scraper.storage import build_document, save_atomic

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://komiku.org/"
# Endpoint daftar TANPA filter tipe: kartu memuat sinopsis untuk semua
# kategori (Manga/Manhwa/Manhua), sedangkan ?tipe=manhwa hanya meng-cover
# sebagian item homepage.
FIRST_PAGE_URL = "https://api.komiku.org/manga/"


def parse_list_page(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for card in soup.select("div.bge"):
        title_el = card.select_one(".kan h3")
        img_el = card.select_one(".bgei img")
        desc_el = card.select_one(".kan p")
        link_el = card.select_one(".bgei a[href]")
        if not (title_el and img_el and link_el):
            LOGGER.warning("Kartu tidak lengkap, dilewati: %s", bool(card))
            continue
        item = {
            "judul": " ".join(title_el.get_text().split()),
            "url_img": urljoin(base_url, img_el.get("data-src") or img_el.get("src") or ""),
            "sinopsis": " ".join(desc_el.get_text().split()) if desc_el else "",
            "detail_url": urljoin(base_url, link_el.get("href") or ""),
        }
        tipe_el = card.select_one(".tpe1_inf b")
        kategori = clean_text(tipe_el.get_text() if tipe_el else "")
        if kategori in {"Manga", "Manhwa", "Manhua"}:
            item["kategori"] = kategori
        items.append(item)
    return items


def discover_next_page(html, current_url):
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.select("[hx-get]"):
        next_url = el.get("hx-get")
        if next_url:
            absolute = urljoin(current_url, next_url)
            if absolute.rstrip("/") != current_url.rstrip("/"):
                return absolute
    for link in soup.select("a[rel=next]"):
        href = link.get("href")
        if href:
            return urljoin(current_url, href)
    return None


def scrape_list_pages(client, max_pages, start_url=FIRST_PAGE_URL, need=None):
    """Scrape halaman daftar. Jika `need` (set canonical detail_url) diberikan,
    berhenti lebih awal setelah semua URL tersebut ditemukan."""
    items = []
    seen = set()
    failed = 0
    url = start_url
    visited = set()
    pending = set(need) if need else None
    for page_num in range(1, max_pages + 1):
        if not url or url in visited:
            break
        visited.add(url)
        try:
            html = client.get(url)
        except requests.RequestException as error:
            LOGGER.error("Halaman %s gagal: %s", url, error)
            failed += 1
            break
        page_items = parse_list_page(html, BASE_URL)
        new_count = 0
        for item in page_items:
            if item["detail_url"] in seen:
                continue
            seen.add(item["detail_url"])
            items.append(item)
            new_count += 1
            if pending is not None:
                pending.discard(
                    normalize_url(item["detail_url"], BASE_URL, detail=True)
                )
        LOGGER.info("Halaman %d: %d item (%d baru, total %d)", page_num, len(page_items), new_count, len(items))
        if pending is not None and not pending:
            LOGGER.info("Semua sinopsis yang dibutuhkan sudah ditemukan, berhenti")
            break
        if new_count == 0:
            LOGGER.info("Tidak ada item baru di halaman %d, berhenti", page_num)
            break
        url = discover_next_page(html, url)
        if url:
            client.polite_delay()
    return items, failed


def deduplicate_by_detail_url(items):
    result = {}
    duplicates = 0
    for item in items:
        key = item["detail_url"]
        if key in result:
            duplicates += 1
            for field, value in item.items():
                if not result[key].get(field) and value:
                    result[key][field] = value
        else:
            result[key] = dict(item)
    return list(result.values()), duplicates


def scrape_homepage_sections(client):
    html = client.get(BASE_URL)
    soup = BeautifulSoup(html, "html.parser")
    sections = collect_sections(soup, BASE_URL)
    sections, duplicates = deduplicate_sections(sections)
    return sections, duplicates


def validate_items(items):
    for item in items:
        for field in ("judul", "url_img", "detail_url"):
            if not item.get(field):
                raise ValueError(f"Field '{field}' kosong pada item: {item}")


def run(args):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    client = HttpClient(
        max_retries=args.max_retries,
        backoff_base=args.backoff_base,
        delay_range=(args.min_delay, args.max_delay),
    )
    sections, homepage_duplicates = scrape_homepage_sections(client)
    if not sections:
        LOGGER.error(
            "Tidak ada section yang terdeteksi di %s. "
            "Kemungkinan penyebab: IP runner diblokir situs (cek log retry 403), "
            "halaman block/challenge, atau struktur HTML berubah. "
            "File %s tidak diubah.",
            BASE_URL,
            args.output,
        )
        return 2
    list_items, list_failed = ([], 0)
    list_duplicates = 0
    if args.include_list:
        list_items, list_failed = scrape_list_pages(client, args.max_pages)
        list_items, list_duplicates = deduplicate_by_detail_url(list_items)
        for item in list_items:
            item.setdefault("section", "daftar-terbaru")
            item.setdefault("section_title", "Daftar Terbaru")
        sections.append({"title": "Daftar Terbaru", "items": list_items})
    sinopsis_filled = 0
    kategori_filled = 0
    detail_filled = 0
    detail_failed = 0
    if not args.no_enrich_sinopsis:
        # Sinopsis placeholder situs ("Belum ada isi.") dianggap kosong.
        clear_placeholder_sinopsis(sections)
        blanks = blank_sinopsis_urls(sections, BASE_URL)
        if blanks:
            if args.include_list:
                # Tanpa request tambahan: pakai item daftar yang sudah diambil.
                enrich_pages, enrich_failed = list_items, 0
            else:
                enrich_pages, enrich_failed = scrape_list_pages(
                    client, args.enrich_pages, need=blanks
                )
                list_failed += enrich_failed
            sinopsis_filled = enrich_sinopsis(
                sections, build_sinopsis_map(enrich_pages, BASE_URL), BASE_URL
            )
            # Endpoint daftar memuat tipe asli (Manga/Manhwa/Manhua); pakai
            # untuk melengkapi kategori yang tidak ada di kartu homepage
            # (mis. kartu peringkat yang tidak punya data-tipe/alt tipe).
            kategori_filled = enrich_kategori(
                sections, build_kategori_map(enrich_pages, BASE_URL), BASE_URL
            )
        else:
            LOGGER.info("Semua item sudah punya sinopsis, enrichment dilewati")
        # Fallback terakhir untuk item yang tetap kosong (biasanya item
        # peringkat yang tidak muncul di halaman awal endpoint daftar):
        # ambil langsung dari halaman detail masing-masing.
        pairs = blank_sinopsis_items(sections, BASE_URL)
        if pairs:
            LOGGER.info("%d item masih kosong, fallback ke halaman detail", len(pairs))
            detail_filled, detail_failed = fill_from_detail_pages(
                sections, pairs, client, BASE_URL
            )
    for section in sections:
        validate_items(section["items"])
        LOGGER.info("Section '%s': %d item", section["title"], len(section["items"]))
    document = build_document(sections, datetime.now(timezone.utc).isoformat(), BASE_URL)
    save_atomic(document, args.output)
    item_count = sum(len(s["items"]) for s in document["sections"])
    unique = len({i["detail_url"] for s in document["sections"] for i in s["items"]})
    sinopsis_empty = sum(
        1
        for s in document["sections"]
        for i in s["items"]
        if not (i.get("sinopsis") or "").strip()
    )
    stats = {
        "sections": len(document["sections"]),
        "items_per_section": {s["title"]: len(s["items"]) for s in document["sections"]},
        "total_items": item_count,
        "unique_items": unique,
        "duplicates_removed": homepage_duplicates + list_duplicates,
        "sinopsis_filled": sinopsis_filled,
        "kategori_filled": kategori_filled,
        "detail_filled": detail_filled,
        "detail_failed": detail_failed,
        "detail_filled": detail_filled,
        "detail_failed": detail_failed,
        "sinopsis_empty": sinopsis_empty,
        "failed_requests": list_failed,
    }
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scraper section manhwa Komiku")
    parser.add_argument("--output", default="manhwa.json")
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--include-list", action="store_true", help="Tambah section pagination daftar terbaru (semua tipe)")
    parser.add_argument("--min-delay", type=float, default=1.0)
    parser.add_argument("--max-delay", type=float, default=2.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--backoff-base", type=float, default=2.0)
    parser.add_argument("--enrich-pages", type=int, default=10,
                        help="Batas halaman daftar untuk enrichment sinopsis")
    parser.add_argument("--no-enrich-sinopsis", action="store_true",
                        help="Nonaktifkan pengisian sinopsis dari endpoint daftar")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())

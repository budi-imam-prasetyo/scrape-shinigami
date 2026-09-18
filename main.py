"""CLI entry point scraper section Komiku.

Version: 0.2.0
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
from manhwa_scraper.scraper import collect_sections, deduplicate_sections
from manhwa_scraper.storage import build_document, save_atomic

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://komiku.org/"
PAGE_URL_TEMPLATE = "https://api.komiku.org/manga/page/{page}/?tipe=manhwa"
FIRST_PAGE_URL = "https://api.komiku.org/manga/?tipe=manhwa"


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
        items.append(
            {
                "judul": " ".join(title_el.get_text().split()),
                "url_img": urljoin(base_url, img_el.get("data-src") or img_el.get("src") or ""),
                "sinopsis": " ".join(desc_el.get_text().split()) if desc_el else "",
                "detail_url": urljoin(base_url, link_el.get("href") or ""),
            }
        )
    return items


def discover_next_page(html, current_url):
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.select("[hx-get]"):
        next_url = el.get("hx-get")
        if next_url and next_url.rstrip("/") != current_url.rstrip("/"):
            return next_url
    for link in soup.select("a[rel=next]"):
        href = link.get("href")
        if href:
            return urljoin(current_url, href)
    return None


def scrape_list_pages(client, max_pages, start_url=FIRST_PAGE_URL):
    items = []
    seen = set()
    failed = 0
    url = start_url
    visited = set()
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
        LOGGER.info("Halaman %d: %d item (%d baru, total %d)", page_num, len(page_items), new_count, len(items))
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
    if args.include_list:
        list_items, list_failed = scrape_list_pages(client, args.max_pages)
        list_items, list_duplicates = deduplicate_by_detail_url(list_items)
        for item in list_items:
            item.setdefault("section", "manhwa-terbaru")
            item.setdefault("section_title", "Manhwa Terbaru")
        sections.append({"title": "Manhwa Terbaru", "items": list_items})
    for section in sections:
        validate_items(section["items"])
        LOGGER.info("Section '%s': %d item", section["title"], len(section["items"]))
    document = build_document(sections, datetime.now(timezone.utc).isoformat(), BASE_URL)
    save_atomic(document, args.output)
    item_count = sum(len(s["items"]) for s in document["sections"])
    unique = len({i["detail_url"] for s in document["sections"] for i in s["items"]})
    stats = {
        "sections": len(document["sections"]),
        "items_per_section": {s["title"]: len(s["items"]) for s in document["sections"]},
        "total_items": item_count,
        "unique_items": unique,
        "duplicates_removed": homepage_duplicates,
        "failed_requests": list_failed,
    }
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scraper section manhwa Komiku")
    parser.add_argument("--output", default="manhwa.json")
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--include-list", action="store_true", help="Tambah section pagination daftar manhwa")
    parser.add_argument("--min-delay", type=float, default=1.0)
    parser.add_argument("--max-delay", type=float, default=2.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--backoff-base", type=float, default=2.0)
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())

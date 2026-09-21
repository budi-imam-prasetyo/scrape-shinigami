"""CLI entry point scraper metadata manga Shinigami.

Version: 1.0.0

Sumber: JSON API publik Shinigami (https://api.shngm.io). Tidak ada
parsing HTML situs; semua data adalah metadata (judul, sinopsis, rating,
genre, author, artist, dst) — bukan isi/chapter komik.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone

from manhwa_scraper import VERSION
from manhwa_scraper.config import SITE_BASE
from manhwa_scraper.http import ApiClient
from manhwa_scraper.scraper import ShinigamiScraper, build_sections
from manhwa_scraper.storage import build_document, save_atomic

LOGGER = logging.getLogger(__name__)

VALID_KINDS = ("top", "latest", "rating")


def _parse_kinds(text: str) -> list[str]:
    kinds = [k.strip() for k in text.split(",") if k.strip()]
    unknown = [k for k in kinds if k not in VALID_KINDS]
    if unknown:
        raise SystemExit(f"Section tidak dikenal: {unknown}. Pilih dari {VALID_KINDS}.")
    return kinds


def run(args) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    client = ApiClient(
        max_retries=args.max_retries,
        backoff_base=args.backoff_base,
        delays=(args.min_delay, args.max_delay),
    )
    scraper = ShinigamiScraper(client=client)

    kinds = _parse_kinds(args.kinds)
    try:
        sections = build_sections(
            scraper,
            kinds=kinds,
            with_comments=args.with_comments,
        )
    except Exception as error:  # noqa: BLE001
        LOGGER.error("Scraper gagal: %s", error)
        return 1

    if not any(s["items"] for s in sections):
        LOGGER.error(
            "Tidak ada section yang terdeteksi di %s (mungkin API berubah atau IP diblokir). "
            "File %s tidak diubah.",
            SITE_BASE,
            args.output,
        )
        return 2

    for section in sections:
        LOGGER.info("Section '%s': %d item", section["title"], len(section["items"]))

    document = build_document(
        sections,
        datetime.now(timezone.utc).isoformat(),
        SITE_BASE,
    )
    save_atomic(document, args.output)

    item_count = sum(len(s["items"]) for s in document["sections"])
    unique = len({i["id"] for s in document["sections"] for i in s["items"]})
    stats = {
        "sections": len(document["sections"]),
        "items_per_section": {
            s["title"]: len(s["items"]) for s in document["sections"]
        },
        "total_items": item_count,
        "unique_items": unique,
    }
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Scraper metadata manga dari Shinigami (JSON API)."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
        help="tampilkan versi lalu keluar",
    )
    parser.add_argument("--output", default="manhwa.json")
    parser.add_argument(
        "--kinds",
        default="top,latest,rating",
        help="Section yang diambil, dipisah koma. Opsi: top,latest,rating (default: top,latest,rating)",
    )
    parser.add_argument(
        "--with-comments",
        action="store_true",
        help="Ambil 10 komentar user (Waline) untuk chapter terbaru tiap item. "
        "Menambah request per item; gunakan bijak.",
    )
    parser.add_argument("--min-delay", type=float, default=1.0)
    parser.add_argument("--max-delay", type=float, default=2.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--backoff-base", type=float, default=2.0)
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())

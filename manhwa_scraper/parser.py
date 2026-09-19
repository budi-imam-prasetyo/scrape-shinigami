"""Parsing HTML halaman Komiku menjadi data terstruktur.

Version: 0.2.2
"""

import logging
import re

from bs4 import BeautifulSoup

from .normalize import clean_text, normalize_url

LOGGER = logging.getLogger(__name__)

TIPE_PATTERN = re.compile(r"^Baca\s+(Manga|Manhwa|Manhua)\b")

# Teks yang dipakai situs sebagai pengganti sinopsis kosong.
SINOPSIS_PLACEHOLDER = "belum ada isi."


def parse_kategori(card):
    """Ambil tipe komik: atribut data-tipe dulu, lalu prefix alt gambar."""
    tipe = clean_text(card.get("data-tipe") or "")
    if tipe in {"Manga", "Manhwa", "Manhua"}:
        return tipe
    img_el = card.select_one("a img, img")
    alt = clean_text(img_el.get("alt") if img_el is not None else "")
    match = TIPE_PATTERN.match(alt)
    return match.group(1) if match else ""


def parse_item(card, base_url, title_selector):
    title_el = card.select_one(title_selector)
    link_el = card.select_one("a[href]")
    if title_el is None or link_el is None:
        return None
    img_el = card.select_one("img")
    if img_el is None:
        return None
    image_src = img_el.get("data-src") or img_el.get("src") or ""
    if not image_src or "/asset/img/lazy" in image_src:
        return None
    detail_url = normalize_url(link_el.get("href", ""), base_url, detail=True)
    if not detail_url:
        return None
    desc_el = card.select_one("p")
    item = {
        "judul": clean_text(title_el.get_text()),
        "url_img": normalize_url(image_src, base_url),
        "sinopsis": clean_text(desc_el.get_text()) if desc_el else "",
        "detail_url": detail_url,
    }
    kategori = parse_kategori(card)
    if kategori:
        item["kategori"] = kategori
    return item


def parse_rank_sections(section, base_url):
    panels = {}
    for panel in section.select("div.rank-panel[id^='rank-']"):
        panel_name = clean_text(panel["id"].removeprefix("rank-"))
        items = []
        seen = set()
        for card in panel.select("article.ls4"):
            item = parse_item(card, base_url, title_selector=".ls4j h4 a")
            if item is None:
                continue
            rank_el = card.select_one(".rank-num")
            try:
                item["rank"] = int(clean_text(rank_el.get_text()) if rank_el else "")
            except (ValueError, TypeError):
                LOGGER.warning("Rank tidak terbaca untuk %s, dilewati", item["judul"])
            item["sub_section"] = panel_name
            if item["detail_url"] in seen:
                continue
            seen.add(item["detail_url"])
            items.append(item)
        if items:
            panels[panel_name] = items
    return panels


def parse_detail_sinopsis(html):
    """Ambil sinopsis dari halaman detail manga (elemen #Sinopsis)."""
    soup = BeautifulSoup(html, "html.parser")
    section = soup.select_one("#Sinopsis")
    if section is None:
        return ""
    text = ""
    desc = section.select_one(".desc")
    if desc is not None:
        text = desc.get_text()
    else:
        for p in section.select("p"):
            if clean_text(p.get_text()):
                text = p.get_text()
                break
    result = clean_text(text)
    if result.casefold() == SINOPSIS_PLACEHOLDER:
        return ""
    return result


def parse_detail_kategori(html):
    """Ambil tipe komik dari tabel metadata halaman detail (baris 'Tipe:')."""
    soup = BeautifulSoup(html, "html.parser")
    for row in soup.select("tr"):
        tds = row.select("td")
        if len(tds) >= 2 and clean_text(tds[0].get_text()) == "Tipe:":
            value = clean_text(tds[1].get_text())
            return value if value in {"Manga", "Manhwa", "Manhua"} else ""
    return ""


def parse_card_sections(soup, base_url):
    sections = []
    for sec in soup.select("main section[id]"):
        heading = sec.select_one("h1, h2")
        cards = sec.select("article.ls2")
        if heading is None or not cards:
            continue
        title = clean_text(heading.get_text())
        if not title:
            continue
        items = []
        seen = set()
        for card in cards:
            item = parse_item(card, base_url, title_selector="h3 a")
            if item is None or item["detail_url"] in seen:
                continue
            seen.add(item["detail_url"])
            items.append(item)
        if items:
            sections.append({"id": sec["id"], "title": title, "items": items})
    return sections

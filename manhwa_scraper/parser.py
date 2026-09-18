"""Parsing HTML halaman Komiku menjadi data terstruktur.

Version: 0.2.0
"""

import logging

from .normalize import clean_text, normalize_url

LOGGER = logging.getLogger(__name__)


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
    return {
        "judul": clean_text(title_el.get_text()),
        "url_img": normalize_url(image_src, base_url),
        "sinopsis": clean_text(desc_el.get_text()) if desc_el else "",
        "detail_url": detail_url,
    }


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
            item["rank"] = int(rank_el.get_text(strip=True))
            item["sub_section"] = panel_name
            if item["detail_url"] in seen:
                continue
            seen.add(item["detail_url"])
            items.append(item)
        if items:
            panels[panel_name] = items
    return panels


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

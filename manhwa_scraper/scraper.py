"""Penggabungan hasil parsing menjadi section final + deduplication.

Version: 0.2.0
"""

import logging

from .normalize import section_id

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

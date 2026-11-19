"""Parser komentar Shinigami API v2 dan payload Waline lama.

API baru mengembalikan comments dengan content/date/vote_up/id.
Payload lama memakai data dengan comment/insertedAt/like/objectId.
"""

from __future__ import annotations

import re
from html import unescape
from typing import Any

from .normalize import clean_text, parse_iso_date

# Batas komentar per manga supaya request tetap ringan.
MAX_COMMENTS = 10


def _strip_html(html: str) -> str:
    """Ubah HTML ringan komentar waline menjadi teks polos."""
    text = html
    text = text.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")
    text = text.replace("</p>", " ").replace("</div>", " ")
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    return clean_text(unescape(text))


def _comment_date(raw: dict) -> str:
    """Ekstrak tanggal dari field waline yang faktual.

    Prioritas: `insertedAt` (string 'YYYY-MM-DD HH:MM:SS'), lalu `time`
    (epoch ms), lalu `createdAt`. Helper ini menamai kasus field yang
    berbeda antar versi waline.
    """
    inserted = clean_text(raw.get("insertedAt"))
    if inserted:
        m = re.match(r"(\d{4}-\d{2}-\d{2})", inserted)
        if m:
            return m.group(1)
    times = raw.get("time")
    if isinstance(times, (int, float)) and times > 0:
        import datetime

        return datetime.datetime.fromtimestamp(
            times / 1000, datetime.timezone.utc
        ).strftime("%Y-%m-%d")
    return parse_iso_date(raw.get("date") or raw.get("createdAt"))


def parse_comments_payload(payload: Any, limit: int = MAX_COMMENTS) -> list[dict]:
    """Ubah payload komentar API baru atau Waline menjadi komentar bersih.

    Payload bentuk: {"page":N,"totalPages":N,"count":N,"data":[...]}.
    Setiap item punya field: comment (HTML), nick, createdAt, like,
    objectId. Hanya komentar dengan nick + isi teks yang dipakai.
    """
    if not isinstance(payload, dict):
        return []
    raw_items = payload.get("comments", payload.get("data"))
    if not isinstance(raw_items, list):
        return []

    out: list[dict] = []
    for raw in raw_items[:limit]:
        if not isinstance(raw, dict):
            continue
        if raw.get("is_deleted") or raw.get("is_pending") or raw.get("visible") is False:
            continue
        nick = clean_text(raw.get("nick") or raw.get("username"))
        text = _strip_html(clean_text(raw.get("content") or raw.get("comment")))
        if not nick or not text:
            continue
        entry: dict[str, Any] = {
            "username": nick,
            "isi": text,
            "tanggal": _comment_date(raw),
            "suka": int(raw.get("vote_up", raw.get("like")))
            if isinstance(raw.get("vote_up", raw.get("like")), (int, float))
            else 0,
        }
        oid = raw.get("id", raw.get("objectId"))
        if oid not in (None, ""):
            entry["id"] = str(oid)
        out.append(entry)
    return out

"""Parser untuk data yang tidak tersedia lewat JSON API Shinigami.

Version: 1.0.0

Catatan arsitektur: mayoritas metadata diambil dari JSON API Shinigami
(manga/list, manga/detail, manga/top) sehingga modul ini tidak menangani
parsing DOM situs. Fungsinya hanya untuk data komentar pengguna yang
diambil dari layanan komentar Waline Shinigami (`https://commento.shngm.io`),
yang komentarnya dikelompokkan per chapter.

Komentar waline disimpan di dalam payload JSON berisi field HTML mentah,
jadi di sini ada pembersihan HTML -> teks polos.
"""

from __future__ import annotations

import re
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
    return clean_text(text)


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

        return datetime.datetime.fromtimestamp(times / 1000, datetime.timezone.utc).strftime("%Y-%m-%d")
    return parse_iso_date(raw.get("createdAt"))


def parse_comments_payload(payload: Any, limit: int = MAX_COMMENTS) -> list[dict]:
    """Ubah payload JSON Waline (/comment) menjadi daftar komentar bersih.

    Payload bentuk: {"page":N,"totalPages":N,"count":N,"data":[...]}.
    Setiap item punya field: comment (HTML), nick, createdAt, like,
    objectId. Hanya komentar dengan nick + isi teks yang dipakai.
    """
    if not isinstance(payload, dict):
        return []
    raw_items = payload.get("data")
    if not isinstance(raw_items, list):
        return []

    out: list[dict] = []
    for raw in raw_items[:limit]:
        if not isinstance(raw, dict):
            continue
        nick = clean_text(raw.get("nick"))
        text = _strip_html(clean_text(raw.get("comment")))
        if not nick or not text:
            continue
        entry: dict[str, Any] = {
            "username": nick,
            "isi": text,
            "tanggal": _comment_date(raw),
            "suka": int(raw["like"]) if isinstance(raw.get("like"), (int, float)) else 0,
        }
        oid = raw.get("objectId")
        if oid not in (None, ""):
            entry["id"] = str(oid)
        out.append(entry)
    return out
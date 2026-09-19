import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

# Teks yang dipakai situs Komiku sebagai pengganti sinopsis kosong.
SINOPSIS_PLACEHOLDER = "belum ada isi."


def clean_text(value):
    return " ".join(str(value or "").split())


def is_real_sinopsis(value):
    """True jika teks layak dipakai sebagai sinopsis (bukan kosong/placeholder)."""
    text = clean_text(value)
    return bool(text) and text.casefold() != SINOPSIS_PLACEHOLDER


def normalize_url(value, base_url, detail=False):
    value = clean_text(value)
    if not value:
        return ""
    parsed = urlsplit(urljoin(base_url, value))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    path = re.sub(r"/{2,}", "/", parsed.path) or "/"
    query = parsed.query
    if detail:
        if not re.fullmatch(r"/manga/[^/]+/?", path):
            return ""
        path = path.rstrip("/") + "/"
        query = ""
    else:
        query = urlencode(sorted(parse_qsl(query, keep_blank_values=True)))
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, query, ""))


def section_id(title):
    return re.sub(r"[^\w]+", "-", clean_text(title).casefold()).strip("-")

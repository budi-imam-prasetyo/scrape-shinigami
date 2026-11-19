"""Konfigurasi endpoint dan konstanta sumber data Shinigami.

Version: 1.1.0

Sumber data: REST API publik Shinigami (dipakai oleh frontend
https://s1.shinigami.mx). Tidak ada HTML parsing sama sekali — seluruh data
diambil dari endpoint JSON, sehingga tidak rentan terhadap perubahan DOM.

Diverifikasi pada 2026-11-19 dari frontend publik s1.shinigami.mx:
- API katalog memakai offset/limit dan meta.has_next.
- Batas request yang telah diuji: limit=100; limit=500 ditolak.
- Ranking memakai limit/cursor; scraper mengambil 10 teratas.
- Komentar memakai comment/api/v2/comments dengan page_key.
"""

API_BASE = "https://api.shinigami.io/v1"

SITE_BASE = "https://s1.shinigami.mx"

COMMENTS_URL = "https://api.shinigami.io/comment/api/v2/comments"

# Detail manga di situs: /series/{manga_id}/{slug}
SERIES_URL_TEMPLATE = SITE_BASE + "/series/{manga_id}"

# Sort yang benar-benar didukung API.
VALID_SORTS = ("latest", "rating", "bookmark")

DEFAULT_SORT = "latest"

# Ukuran halaman yang didukung API baru (500 ditolak).
MAX_PAGE_SIZE = 100

# None: ambil semua halaman sampai meta.has_next=False.
LIST_PAGES = None

# Status manga: nilai integer dari API -> label.
STATUS_LABELS = {
    1: "Ongoing",
    2: "Completed",
    3: "Hiatus",
    4: "Dropped",
}

# Negara asal -> label tipe yang lazim dipakai pembaca.
COUNTRY_LABELS = {
    "KR": "Manhwa",
    "CN": "Manhua",
    "JP": "Manga",
    "TW": "Manhua",
    "US": "Comic",
}

# Header wajib: API memeriksa Origin/Referer dari situs.
DEFAULT_HEADERS = {
    "User-Agent": (
        "ShinigamiMetadataScraper/1.1.0 (personal use; metadata only; Python requests)"
    ),
    "Accept": "application/json",
    "Accept-Language": "id-ID,id;q=0.9",
    "Origin": SITE_BASE,
    "Referer": SITE_BASE + "/",
}

# Jalan (path) relatif terhadap API_BASE untuk tiap sumber data.
ENDPOINT_MANGA_LIST = "/manga/list"
ENDPOINT_MANGA_TOP = "/manga/top"
ENDPOINT_MANGA_DETAIL = "/manga/detail/{manga_id}"
ENDPOINT_GENRE_LIST = "/genre/list"
ENDPOINT_ANNOUNCEMENT_LIST = "/announcement/list"


def series_url(manga_id):
    """URL halaman detail di situs (untuk dikonsumsi manusia)."""
    return SERIES_URL_TEMPLATE.format(manga_id=manga_id)

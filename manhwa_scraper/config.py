"""Konfigurasi endpoint dan konstanta sumber data Shinigami.

Version: 1.0.0

Sumber data: REST API publik Shinigami (dipakai oleh frontend
https://11.shinigami.asia). Tidak ada HTML parsing sama sekali — seluruh data
diambil dari endpoint JSON, sehingga tidak rentan terhadap perubahan DOM.

Catatan hasil verifikasi struktur (lihat README bagian "Sumber data"):
- `sort` yang valid: latest, rating, bookmark. Nilai lain mengembalikan 400.
- `manga/top` mengabaikan parameter `sort`/`type`; selalu 10 item teratas.
- Item dari `manga/top` TIDAK menyertakan `taxonomy`, sehingga genre/author/
  artist harus dilengkapi dari `manga/detail/{id}`.
- Endpoint `notice` (komentar) mengembalikan `data: null` untuk pengguna
  anonim; komentar hanya tersedia jika ada kredensial.
"""

API_BASE = "https://api.shngm.io/v1"

SITE_BASE = "https://11.shinigami.asia"

# Detail manga di situs: /series/{manga_id}/{slug}
SERIES_URL_TEMPLATE = SITE_BASE + "/series/{manga_id}"

# Sort yang benar-benar didukung API.
VALID_SORTS = ("latest", "rating", "bookmark")

DEFAULT_SORT = "latest"

# Batas yang diterima API untuk page_size (diverifikasi: 100 diterima).
MAX_PAGE_SIZE = 100

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
        "ShinigamiMetadataScraper/1.0.0 "
        "(personal use; metadata only; Python requests)"
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
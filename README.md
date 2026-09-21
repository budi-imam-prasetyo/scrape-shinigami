# Shinigami Manga Metadata Scraper

Scraper Python untuk mengambil **metadata manga** dari Shinigami
(`https://11.shinigami.asia`) melalui **JSON API publik**, dikelompokkan
dalam section yang dapat dikonfigurasi.

> **Penting (etika & skop):** alat ini HANYA mengambil informasi/katalog
> manga (judul, cover, sinopsis, rating, genre, author, artist, status,
> update terbaru, komentar). **TIDAK** mengambil isi/chapter komik.

> Grafik edisi sebelumnya memindai HTML `komiku.org`. Mulai **v1.0.0**
> sumber berubah total ke Shinigami (JSON API) — lihat
> [Riwayat versi](#riwayat-versi) dan [Migrasi Komiku → Shinigami](#migrasi-komiku--shinigami).

## Sumber data

Shinigami adalah SPA SvelteKit — halaman HTML-nya kosong (data dirender
client-side). Alat ini memakai **JSON API publik** yang dipakai frontend-nya:

| Endpoint | Fungsi |
| --- | --- |
| `GET https://api.shngm.io/v1/manga/list` | Daftar manga (sort: `latest`, `rating`, `bookmark`) |
| `GET https://api.shngm.io/v1/manga/top` | Peringkat 10 teratas |
| `GET https://api.shngm.io/v1/manga/detail/{id}` | Detail + taxonomy (genre, author, artist, dll) |
| `GET https://commento.shngm.io/comment?path=...` | Komentar user (Waline) |

Keunggulan vs HTML scraping: data terstruktur, stabil, tidak rentan terhadap
perubahan DOM, dan sudah menyertakan rating/status/genre yang lengkap.

## Struktur output (`manhwa.json`)

```json
{
  "schema_version": "1.0.0",
  "generated_at": "2026-09-21T00:00:00+00:00",
  "source": "https://11.shinigami.asia",
  "sections": [
    {
      "id": "terbaru",
      "title": "Terbaru",
      "items": [
        {
          "id": "90f99e6c-...",
          "judul": "Goblin Inc",
          "judul_alternatif": "고블린 주식회사",
          "detail_url": "https://11.shinigami.asia/series/90f99e6c-...",
          "url_img": "https://assets.shngm.id/thumbnail/...jpg",
          "url_img_portrait": "https://assets.shngm.id/thumbnail/...jpg",
          "sinopsis": "Seorang pekerja kantoran biasa...",
          "kategori": "Manhwa",
          "status": "Ongoing",
          "tahun": 2026,
          "rating": 8.5,
          "views": 548422,
          "bookmark_count": 9270,
          "rank": 9999,
          "updated_at": "2026-09-21",
          "chapter_terbaru": 14,
          "genre": ["Action", "Fantasy"],
          "author": ["Mon"],
          "artist": ["Beonin"],
          "format": ["Manhwa"],
          "tipe": ["Project"],
          "mutakhir": true,
          "komentar": [
            {"username": "Ivan", "isi": "Pas seru^", "tanggal": "2026-09-20", "suka": 0, "id": "6333899"}
          ]
        }
      ]
    }
  ]
}
```

### Field mapping API → internal

| API Shinigami | Internal (output) | Keterangan |
| --- | --- | --- |
| `manga_id` / `id` | `id` | UUID unik |
| `title` | `judul` | — |
| `alternative_title` | `judul_alternatif` | opsional |
| `cover_image_url` | `url_img` | via `safe_url` (hanya http/https) |
| `cover_portrait_url` | `url_img_portrait` | opsional |
| `description` | `sinopsis` | placeholder dibersihkan |
| `country_id` (`KR`/`CN`/`JP`) | `kategori` | Manhwa/Manhua/Manga |
| `status` (1-4) | `status` | Ongoing/Completed/Hiatus/Dropped |
| `release_year` | `tahun` | int |
| `user_rate` | `rating` | float |
| `view_count` | `views` | int |
| `bookmark_count` | `bookmark_count` | int |
| `rank` | `rank` | int (top selalu `9999` dari API) |
| `latest_chapter_time` | `updated_at` | `YYYY-MM-DD` |
| `latest_chapter_number` | `chapter_terbaru` | int |
| `is_recommended` | `mutakhir` | bool |
| `taxonomy.Genre[]` | `genre` | list, dari `manga/detail` |
| `taxonomy.Author[]` | `author` | list, dari `manga/detail` |
| `taxonomy.Artist[]` | `artist` | list, dari `manga/detail` |
| `taxonomy.Format[]` | `format` | list, dari `manga/detail` |
| `taxonomy.Type[]` | `tipe` | list, dari `manga/detail` |
| Waline `chapter/<id>` comments | `komentar` | opsional, `--with-comments` |

Catatan skema:
- Field opsional (`judul_alternatif`, `genre`, `rating`, dst) **hanya muncul**
  jika nilainya ada. `additionalProperties: false` di jsonschema menjaga output
  konsisten — item harus lolos `validate_document`.
- Field internal (diawali `_`, mis. `_waline_path`) tidak ikut diexport ke JSON.

### Section yang tersedia

| `--kinds` | Title | Endpoint |
| --- | --- | --- |
| `top` | Peringkat Teratas | `manga/top` (10 item, di-enrich taxonomy via detail) |
| `latest` (default) | Terbaru | `manga/list?sort=latest` (100 item) |
| `rating` | Rating Tertinggi | `manga/list?sort=rating` (100 item) |

## Cara menjalankan

```bash
# Default: top + latest + rating
python3 main.py --output manhwa.json

# Pilih section tertentu (dipisah koma)
python3 main.py --output manhwa.json --kinds top,latest

# Tambah komentar user untuk chapter terbaru tiap item (request per item)
python3 main.py --output manhwa.json --with-comments

# Tuning request (CI: agresif retry, delay kecil)
python3 main.py --output manhwa.json --max-retries 5 --backoff-base 3.0 --min-delay 0.3 --max-delay 0.8
```

Argumen penuh:

| Argumen | Default | Keterangan |
| --- | --- | --- |
| `--output` | `manhwa.json` | Path output |
| `--kinds` | `top,latest,rating` | Section, dipisah koma |
| `--with-comments` | off | Ambil 10 komentar chapter terbaru (menambah request) |
| `--min-delay`, `--max-delay` | `1.0`, `2.0` | Jeda acak antar request |
| `--max-retries` | `3` | Retry per request |
| `--backoff-base` | `2.0` | Basis exponential backoff |

Jika tidak ada section terdeteksi (API berubah/berubah, IP diblokir), scraper
keluar dengan kode **2** dan `manhwa.json` tidak diubah. Jika request gagal
total, keluar dengan kode **1** beserta traceback. Statistik akhir dicetak ke
stdout (jumlah section, item per section, total, unique).

## Komentar (Waline)

Komentar user tidak tersedia dari `api.shngm.io`. Ditemukan saat recon bahwa
Shinigami memakai **Waline** (`https://commento.shngm.io`) dan mengelompokkan
komentar per **chapter** (`path=chapter/<id>`). Scraper mengambil komentar
untuk **chapter terbaru** saja (10 komentar) untuk menjaga request tetap
minimal dan tidak menyentuh isi komik. Aktifkan dengan `--with-comments`.

## Refresh otomatis harian (GitHub Actions)

Workflow `.github/workflows/refresh.yml` automatis setiap hari pukul 18:00
UTC (01:00 WIB) via `schedule.cron`, dan bisa dipicu manual via tab Actions.

Step:
1. Checkout (full history `fetch-depth: 0`), Python 3.12, install deps.
2. Run tests (`python -m unittest discover -s tests -v`).
3. Run scraper.
4. Validasi JSON (`python -m json.tool manhwa.json`).
5. Commit + push **hanya jika berubah**, via
   `fetch → rebase -X theirs → push HEAD:main` (tahan race condition).

## Menjalankan test

```bash
python3 -m unittest discover -s tests -v
```

Test memakai fixture JSON aktual (`tests/fixtures/*.json`) dari API Shinigami
+ HTTP session tiruan (tanpa jaringan). Suite mencakup: normalisasi field,
parser komentar, retry/backoff HTTP, dedup, build/validasi document, strip
field internal.

## Arsitektur

| Modul | Tanggung jawab |
| --- | --- |
| `main.py` | CLI, orkestrasi, statistik |
| `manhwa_scraper/config.py` | Endpoint, sort valid, mapping status/negara, header |
| `manhwa_scraper/http.py` | `ApiClient` (JSON) + retry/backoff/rate guard |
| `manhwa_scraper/scraper.py` | Orkestrasi API, dedup, enrich detail, attach komentar |
| `manhwa_scraper/normalize.py` | Transformasi field API → model internal |
| `manhwa_scraper/parser.py` | Parser komentar Waline (fallback yang butuh parsing) |
| `manhwa_scraper/storage.py` | Skema JSON (1.0.0), validasi, atomic write |

## Perilaku penting & reliabilitas

- **Atomic write**: `manhwa.json` via tempfile + `os.replace` — file lama
  tidak pernah corrupt walau proses mati di tengah.
- **Retry/backoff**: status retryable `{429, 500, 502, 503, 504}` di-retry
  dengan exponential backoff + jitter; **4xx permanen (404 dst) tidak di-retry**.
- **Duplikat**: dedup berdasarkan `id` **dalam satu section** (menghindari
  item ganda bila API mengirim duplikat). Setiap section (`top`/`latest`/
  `rating`) utuh dan independen di output; tidak ada konsolidasi antar-section
  karena satu item bisa wajar muncul di beberapa section berbeda.
- **Detail enrichment**: `manga/top` tidak menyertakan taxonomy, jadi genre/
  author/artist diisi lewat `manga/detail` (satu request per id top).
- **Rate politeness**: semua request serial + `polite_delay`; tidak ada
  concurrency agresif. Gunakan `--min-delay`/`--max-delay` bijak.
- **Keamanan URL**: `safe_url` hanya mengizinkan `http/https`, membuang
  kredensial, menghindari URL berbahaya (`javascript:` dst).
- **Missing data**: field kosong dianggap tidak ada (opsional tidak muncul),
  bukan nilai palsu.

## Migrasi Komiku → Shinigami (v0.2.x → v1.0.0)

Perombakan total karena arsitektur target berbeda:

| Aspek | v0.2.x (Komiku) | v1.0.0 (Shinigami) |
| --- | --- | --- |
| Sumber | HTML `komiku.org` + `api.komiku.org` (HTML/htx) | JSON API `api.shngm.io/v1` |
| Parsing | BeautifulSoup selectors (`article.ls2`, `#Sinopsis`, dll) | JSON terstruktur, tanpa DOM |
| Metadata | judul, url_img, sinopsis, kategori, rank | + rating, status, tahun, genre, author, artist, format, views |
| Ranking | panel `#rank-harian`/`#rank-mingguan` (HTML) | `manga/top` (10 besar) |
| Komentar | tidak ada | Waline `commento.shngm.io` (`--with-comments`) |
| Skema output | `schema_version: 0.2.0` | `schema_version: 1.0.0` |
| Linimasa | pastikan tidak backup item lama | build dari nol per run |

**`beautifulsoup4` dihapus** dari `requirements.txt` — tidak ada lagi HTML
parsing; semua data lewat JSON.

## Riwayat versi

- **1.0.0** (2026-09-21): Migrasi sumber data total dari Komiku (HTML) ke
  Shinigami (JSON API). Skema output dirombak (`schema_version: 1.0.0`),
  field metadata diperluas (rating, status, genre, author, artist, dst),
  komentar Waline opsional, modul di-refactor bersih (config/http/scraper/
  normalize/parser/storage), `beautifulsoup4` dihapus, suite test baru
  dengan fixture JSON. **Ini MAJOR** (API/schema/behavior berubah).
- 0.2.x (Komiku): versi sebelumnya berbasis HTML scraping; dihentikan.
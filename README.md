# Shinigami Manga Metadata Scraper

Scraper Python untuk **metadata katalog** Shinigami. Tidak mengunduh isi
atau gambar halaman chapter komik. Output tetap memakai schema `1.0.0`.

## Perubahan situs November 2026 (scraper 1.1.0)

Diverifikasi pada 19 November 2026 melalui frontend publik dan respons API:

- Situs lama `https://11.shinigami.asia` mengalihkan pengunjung melalui
  `https://redirect.shinigami.gg` ke `https://s1.shinigami.mx`.
- Frontend kini aplikasi React; data katalog berasal dari
  `https://api.shinigami.io/v1`, menggantikan `api.shngm.io`.
- Daftar memakai `offset` dan `limit`, menggantikan `page` / `page_size`.
  Scraper memakai 100 item per request (500 ditolak API baru).
- Scraper mengikuti `meta.has_next` sampai halaman terakhir, bukan berhenti
  setelah dua halaman atau mengasumsikan katalog selalu 1.000 judul.
- Saat uji langsung, masing-masing sort `latest` dan `rating` tetap berhenti
  pada 1.000 item dari API; gabungan tiga section menghasilkan 1.261 judul unik.
  `meta.has_next=false` adalah batas hasil API, bukan bukti seluruh katalog
  tersedia dalam satu sort.
- Komentar berganti dari Waline ke `/comment/api/v2/comments`, dengan
  `page_key=manga:<manga_id>:chapter:<chapter_id>`. Parser membaca `comments`,
  `content`, `date`, `vote_up`, dan `id`; payload Waline lama tetap bisa diparse.

## Menjalankan

```bash
python3 -m pip install -r requirements.txt
python3 main.py --output manhwa.json

# Pilih section
python3 main.py --output manhwa.json --kinds top,latest

# Komentar chapter terbaru (satu request tambahan per judul unik)
python3 main.py --output manhwa.json --with-comments
```

| Argumen | Default | Fungsi |
| --- | --- | --- |
| `--output` | `manhwa.json` | File hasil |
| `--kinds` | `top,latest,rating` | Section dipisahkan koma |
| `--with-comments` | off | Hingga 10 komentar chapter terbaru |
| `--min-delay`, `--max-delay` | `1.0`, `2.0` | Jeda acak dalam detik |
| `--max-retries` | `3` | Jumlah percobaan request |
| `--backoff-base` | `2.0` | Basis exponential backoff |
| `--retry-forbidden` | off | Retry 403 sementara sampai batas `--max-retries` (dipakai CI) |
| `--version` | — | Tampilkan versi |

Request serial; jeda diterapkan antar halaman katalog, pengambilan detail,
dan komentar. Pengambilan komentar seluruh katalog dapat memakan waktu lama.

## Endpoint

| Endpoint | Pemakaian |
| --- | --- |
| `GET https://api.shinigami.io/v1/manga/list` | `offset`, `limit=100`, `sort=latest/rating`, `sort_order=desc` |
| `GET https://api.shinigami.io/v1/manga/top` | `limit=10`; API juga mendukung cursor, scraper mengambil 10 pertama |
| `GET https://api.shinigami.io/v1/manga/detail/{id}` | Melengkapi taxonomy item top |
| `GET https://api.shinigami.io/comment/api/v2/comments` | `page_key`, `offset=0`, `limit=10` |

`SITE_BASE`, `API_BASE`, `COMMENTS_URL`, dan ukuran halaman ada di
`manhwa_scraper/config.py`. Domain situs dapat berganti lagi; sesuaikan
konstanta dari redirect/frontend publik saat itu.

## Output

```json
{
  "schema_version": "1.0.0",
  "generated_at": "2026-11-19T00:00:00+00:00",
  "source": "https://s1.shinigami.mx",
  "sections": [
    {
      "id": "terbaru",
      "title": "Terbaru",
      "items": [
        {
          "id": "manga-uuid",
          "judul": "Judul Manga",
          "detail_url": "https://s1.shinigami.mx/series/manga-uuid",
          "url_img": "https://cdn.shinigami.gg/assets/cover/example.jpg",
          "sinopsis": "Ringkasan cerita",
          "kategori": "Manhwa",
          "status": "Ongoing",
          "tahun": 2026,
          "rating": 8.5,
          "genre": ["Action", "Fantasy"],
          "author": ["Penulis"],
          "chapter_terbaru": 21,
          "updated_at": "2026-11-19"
        }
      ]
    }
  ]
}
```

Metadata tambahan yang tersedia: `judul_alternatif`, `url_img_portrait`,
`views`, `bookmark_count`, `rank`, `artist`, `format`, `tipe`, `mutakhir`, dan
`komentar` (username, isi, tanggal, suka, id). Kategori dipetakan dari kode
negara; bisa tidak tersedia bila API tidak mengirim negara. Field internal
berawalan `_` dibuang sebelum ekspor.

Item dideduplikasi berdasarkan ID dalam setiap section. Judul yang sama
boleh muncul di section berbeda. Komentar di-cache per ID selama satu run.

## Penanganan kegagalan

- HTTP 429/500/502/503/504 dan kegagalan jaringan dicoba ulang dengan backoff.
  Error 4xx permanen langsung gagal.
- CI mengaktifkan `--retry-forbidden`: respons 403 sementara dicoba ulang
  dengan backoff, maksimal lima percobaan. Jika tetap diblokir, job gagal
  dan katalog lama tidak diganti. Header diagnostik publik (server,
  content-type, cf-ray, cf-mitigated, retry-after) dicatat tanpa body/cookie.
- `retcode` gagal, struktur daftar berubah, identitas manga kosong, atau
  paginasi berulang menyebabkan proses gagal agar hasil parsial tidak
  menggantikan katalog lama.
- Kegagalan detail/komentar opsional dicatat; katalog tetap dapat disimpan.
- Tidak ada item: exit code 2. Request katalog gagal: exit code 1.
- Output divalidasi dengan JSON Schema lalu ditulis secara atomic.

## Pengujian dan refresh

```bash
python3 -m unittest discover -s tests -v
```

Tes tanpa jaringan mencakup fixture API lama dan baru, offset pagination,
`meta.has_next`, halaman berulang, error API, normalisasi metadata,
komentar baru/Waline, dedup, cache, validasi schema, dan penyimpanan atomic.

Workflow `.github/workflows/refresh.yml` menjalankan tes, scraper, validasi,
dan commit hasil setiap 18:00 UTC (01:00 WIB), atau lewat `workflow_dispatch`.
Log scraper tersedia pada artifact `scraper-diagnostics` selama tujuh hari,
termasuk saat gagal. Dispatch pada branch selain `main` menjalankan tes dan
scrape tanpa menerbitkan hasil branch ke `main`.

## Modul

| Modul | Fungsi |
| --- | --- |
| `main.py` | CLI dan statistik |
| `config.py` | Endpoint, header, mapping |
| `http.py` | HTTP, retry, backoff, jeda |
| `scraper.py` | Katalog, paginasi, dedup, detail, komentar |
| `normalize.py` | Mapping metadata ke schema output |
| `parser.py` | Komentar API baru dan Waline |
| `storage.py` | JSON Schema, validasi, atomic write |

Versi 1.0.0 sebelumnya memigrasikan scraper Komiku berbasis HTML ke JSON API
Shinigami. Versi 1.1.0 menyesuaikan kontrak API dan frontend November 2026.

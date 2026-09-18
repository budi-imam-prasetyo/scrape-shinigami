# Scraper Section Manhwa Komiku

Scraper Python untuk mengambil manhwa dari halaman depan Komiku, dikelompokkan
berdasarkan section yang benar-benar ada di halaman (bukan dikarang).

## Struktur output (`manhwa.json`)

```json
{
  "schema_version": "0.2.0",
  "generated_at": "2026-09-17T13:59:30+00:00",
  "source": "https://komiku.org/",
  "sections": [
    {
      "id": "baca-komik-terbaru",
      "title": "Baca Komik Terbaru",
      "items": [
        {
          "judul": "...",
          "url_img": "...",
          "sinopsis": "...",
          "detail_url": "...",
          "section": "baca-komik-terbaru",
          "section_title": "Baca Komik Terbaru"
        }
      ]
    }
  ]
}
```

### Struktur yang dipilih dan alasannya

Struktur `{"sections": [{"id", "title", "items"}]}` dipilih di atas bentuk
`{"rekomendasi": [...], "terbaru": [...]}` karena:

1. Frontend bisa me-render daftar section secara generik tanpa tahu nama
   section di muka (cukup map over `sections`).
2. Section baru dari situs otomatis ikut terbaca tanpa perubahan konsumen.
3. `id` stabil (slug dari judul) untuk key/pencarian; `title` tetap tersimpan
   untuk tampilan.
4. Metadata per item (`section`, `rank`, `sub_section`) tetap ada sehingga
   relasi lintas section dan deduplication bisa dilakukan di sisi konsumen.

### Section yang terdeteksi (hasil audit HTML aktual)

Section diambil dinamis dari `main section[id]` di `https://komiku.org/`,
bukan di-hardcode:

| Section (title asli)       | id                          | Sumber data             |
| -------------------------- | --------------------------- | ----------------------- |
| Baca Komik Terbaru         | `baca-komik-terbaru`        | kartu `article.ls2`     |
| Baru Ditambahkan           | `baru-ditambahkan`          | kartu `article.ls2`     |
| Peringkat Komiku (harian)  | `peringkat-komiku-harian`   | panel `#rank-harian`    |
| Peringkat Komiku (mingguan)| `peringkat-komiku-mingguan` | panel `#rank-mingguan`  |

Catatan:

- Section homepage memang tidak menyertakan sinopsis per kartu, jadi field
  `sinopsis` berisi string kosong. Sinopsis terisi ketika mode
  `--include-list` dipakai (endpoint daftar menyertakan sinopsis singkat).
- Jika situs menambah/mengubah section, scraper otomatis mengikuti selama
  pola kartunya sama. Section tanpa kartu atau tanpa judul dilewati.

## Cara menjalankan

```bash
# Default: section dari homepage
python3 main.py --output manhwa.json

# Tambah section paginated dari endpoint daftar manhwa (ada sinopsis)
python3 main.py --include-list --max-pages 5 --output manhwa.json

# Opsi lain
python3 main.py --min-delay 1.5 --max-delay 3 --output manhwa.json
```

Statistik akhir dicetak ke stdout: jumlah section, item per section, total
item, item unik, duplikat dihapus, dan request gagal.

## Refresh otomatis harian (GitHub Actions)

Workflow `.github/workflows/refresh.yml` berjalan otomatis setiap hari
pukul 18:00 UTC (01:00 WIB) via `schedule.cron`, dan bisa dipicu manual
lewat tab Actions → "Refresh manhwa.json" → Run workflow (`workflow_dispatch`).

Langkah workflow:

1. Checkout repo, setup Python 3.12, install `requirements.txt`.
2. Jalankan test suite (`python -m unittest discover -s tests -v`).
3. Jalankan scraper (`python main.py --output manhwa.json`).
4. Validasi JSON (`python -m json.tool manhwa.json`).
5. Commit + push `manhwa.json` **hanya jika ada perubahan**
   (`git diff --cached --quiet`), dengan pesan `chore: daily refresh manhwa.json`.

Concurrency group `refresh-manhwa` mencegah dua run refresh berjalan bersamaan.

## Menjalankan test

```bash
python3 -m unittest discover -s tests -v
```

Test memakai HTML fixture (`tests/fixtures/komiku_home.html`) dan HTTP session
tiruan, sehingga tidak ada network call saat test.

## Menambah section baru

1. Buka `https://komiku.org/`, inspect section yang diinginkan.
2. Jika section memakai kartu `article.ls2` dengan judul di `h3 a`, tidak ada
   perubahan kode: section otomatis terdeteksi karena scraper membaca semua
   `main section[id]` yang punya heading dan kartu.
3. Jika strukturnya berbeda (mis. seperti panel ranking), tambahkan parser di
   `manhwa_scraper/parser.py` (fungsi `parse_*` baru) dan sambungkan di
   `manhwa_scraper/scraper.py::collect_sections`.
4. Tambahkan/ubah fixture di `tests/fixtures/` dan test di `tests/` agar
   parser baru tercakup.

## Arsitektur

| Modul                          | Tanggung jawab                                        |
| ------------------------------ | ----------------------------------------------------- |
| `main.py`                      | CLI, orkestrasi, statistik                            |
| `manhwa_scraper/http.py`       | Session, User-Agent, retry+backoff, delay antar-request |
| `manhwa_scraper/parser.py`     | Parsing HTML menjadi item/section                     |
| `manhwa_scraper/scraper.py`    | Penggabungan section, stamping metadata, deduplication |
| `manhwa_scraper/normalize.py`  | Normalisasi teks dan URL, slug id section             |
| `manhwa_scraper/storage.py`    | Schema JSON, validasi, penulisan atomic               |

## Perilaku penting

- **Atomic write**: `manhwa.json` ditulis lewat file temporer lalu `os.replace`,
  sehingga file lama tidak pernah corrupt walau proses mati di tengah jalan.
- **Deduplication**: berdasarkan `detail_url`, per section. Item duplikat
  menyatu dan field kosong diisi dari duplikatnya.
- **Request gagal**: retry 3x dengan exponential backoff + jitter; status
  retryable: 403, 408, 429, 500, 502, 503, 504. Kegagalan final tercatat di
  statistik.
- **Delay**: 1-2 detik (bisa diatur) antar request halaman daftar.
- **Tidak ada request detail per item** secara default; sinopsis diambil dari
  endpoint daftar jika `--include-list` aktif.

## Riwayat versi

- **0.2.0** (2026-09-17): Output berubah dari array datar menjadi dokumen
  per-section (`schema_version: "0.2.0"`). Ditambahkan: deteksi section
  dinamis, pagination deduplication, validasi schema (jsonschema), atomic
  write, retry+backoff, metadata `section`/`rank`/`sub_section`, test suite
  dengan fixture, CLI baru. Ini perubahan **minor**: fitur baru yang backward
  compatible secara fungsi (4 field lama tetap ada), meskipun bentuk output
  berubah dari array menjadi objek.
- **0.1.0**: Versi awal, satu array flat dari endpoint daftar.

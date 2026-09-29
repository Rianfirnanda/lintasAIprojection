# Pemantauan Harga Pangan Berbasis AI dan Big Data — BPS Kabupaten Bengkulu Tengah

Sistem pemantauan harga 10 komoditas / 21 varian pangan untuk TPID Kabupaten Bengkulu Tengah. Sistem ini adalah
**pipeline data**, bukan hanya dashboard:

```
Sumber → Pengambilan → Integrasi → Penyimpanan → Quality Gate → Analisis AI → Dashboard → Keputusan TPID → Umpan balik
```

Seluruh sistem berjalan di GitHub tanpa server: **GitHub Actions** menjalankan pipeline terjadwal,
**GitHub Pages** menyajikan dashboard statis, **git** menjadi audit trail/versioning/backup, dan **GitHub Issues**
menjadi alur tindak lanjut sinyal.

## Komponen

| Lapisan | Implementasi |
|---|---|
| Sumber data | BPS (survei harga), pasar/pedagang (formulir petugas luring-ke-daring), Pemda (harga/stok/distribusi), AI Data Finder, Big Data sah (cuaca Open-Meteo, kalender hari raya) |
| Pengambilan & integrasi | Berkas CSV/Excel di `data/masuk/`, konektor API terjadwal (`pipeline/konektor_cuaca.py`), standardisasi kode & satuan (`pipeline/masukan.py`) |
| Penyimpanan | Data mentah = berkas di repo; metadata = checksum SHA-256 per berkas; audit trail = riwayat git; keluaran terstruktur = JSON di `site/data/` |
| Quality gate | Deduplikasi, data hilang, batas kewajaran, pencilan, konfirmasi silang/persistensi, rekonsiliasi antar-sumber, validasi manusia, ketepatan waktu (`pipeline/kualitas.py`) |
| Analisis AI | Baseline, proyeksi 14 hari (naif, rata-rata 7 hari, Holt damped, profil hari raya), rolling-origin backtesting, interval konformal 90%, deteksi anomali, drift (`pipeline/analisis.py`) |
| Sinyal & konteks | Anomali harga, proyeksi naik, risiko hari raya, data terlambat, drift + konteks cuaca/hari raya/pembanding/stok (`pipeline/sinyal.py`) |
| AI Data Finder | Claude + web search, keluaran terstruktur, URL dicek silang dengan hasil pencarian (`pipeline/pencari_data.py`) |
| Layanan | Dashboard GitHub Pages (`site/`), GitHub Issues, unduhan CSV |

Halaman dashboard: **Dashboard**, **Sinyal & Tindak Lanjut**, **Quality Gate**, **Mutu Model**, **Sumber Data**,
**Input Harga** (dapat dipakai tanpa sinyal/PWA), **Metodologi**.

## Menerbitkan ke GitHub Pages (sekali saja)

1. Gabungkan kode ini ke cabang `main`.
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. **Actions → Pipeline & Dashboard → Run workflow** (atau tunggu jadwal). Setelah selesai, dashboard tersedia di
   `https://<pemilik>.github.io/<nama-repo>/`.
4. (Opsional, untuk AI Data Finder) **Settings → Secrets and variables → Actions → New repository secret**:
   `ANTHROPIC_API_KEY`.
5. (Disarankan) **Settings → Branches**: lindungi `main` dan batasi kolaborator yang boleh mengunggah data.

Selama `data/masuk/harga/` belum berisi berkas CSV/Excel, sistem berjalan dalam **mode demo** dengan data sintetis
berlabel jelas. Mode demo otomatis mati saat berkas harga nyata pertama diunggah.

## Operasional harian

Panduan lengkap per peran: [`docs/PANDUAN_OPERASIONAL.md`](docs/PANDUAN_OPERASIONAL.md).

1. **Petugas** mencatat harga di halaman *Input Harga* → *Unduh CSV* / *Bagikan*.
2. **Operator** mengunggah CSV ke `data/masuk/harga/` → pipeline berjalan otomatis → dashboard diperbarui.
3. **Validator** memutuskan antrean di halaman *Quality Gate* → unggah berkas keputusan ke `data/validasi/`.
4. **Analis/TPID** memverifikasi sinyal lewat GitHub Issues berlabel `sinyal-harga` (label `status: …`).

## Menjalankan secara lokal

```bash
pip install -r requirements.txt
python -m pytest -q                                   # 66 uji otomatis
python -m pipeline periksa                            # validasi berkas di data/masuk
python -m pipeline jalankan --keluaran site/data --tanpa-github
python -m http.server -d site 8000                    # buka http://localhost:8000
python -m pipeline ambil-cuaca                        # konektor cuaca (butuh internet)
ANTHROPIC_API_KEY=... python -m pipeline cari-sumber --komoditas "cabai rawit merah" --periode "Oktober 2026"
```

## Konfigurasi (`config/`)

| Berkas | Isi |
|---|---|
| `komoditas.csv` | 10 komoditas / 21 varian (Tabel 2 Rancangan Aksi Perubahan) + 9 item tambahan kajian Bapokting (`aktif=0`), satuan, kelompok, batas kewajaran |
| `wilayah.csv` | Bengkulu Tengah (target), Kepahiang & Kota Bengkulu (pembanding) |
| `pasar.csv` | Pasar, koordinat, status blank spot |
| `sumber.csv` | Inventaris sumber data, metode akses, status, prioritas rekonsiliasi |
| `kalender.csv` | Hari raya & libur (status `pasti`/`perkiraan`) |
| `pengaturan.json` | Ambang quality gate, sinyal, model, target kinerja, privasi, tindak lanjut |

## Yang wajib dikonfirmasi sebelum dipakai sebagai dasar keputusan

- Daftar komoditas final (10/21 Rancangan vs 21 Bapokting kajian) — keduanya sudah tersedia di `komoditas.csv`.
- Batas kewajaran harga per varian dan koordinat pasar (saat ini nilai awal/perkiraan).
- Daftar pasar target lengkap (baru Pasar Taba Penanjung dan Karang Tinggi) dan 8 wilayah blank spot.
- Izin pengambilan otomatis sumber eksternal (PIHPS, Panel Harga Bapanas) — saat ini berstatus kandidat.
- Kebijakan publikasi: repo & situs **publik**; pastikan data per pasar dan diskusi tindak lanjut boleh dibuka.
- Ambang model (sMAPE, F1, recall, cakupan) adalah target rancangan; kalibrasi ulang setelah baseline pilot.

## Keamanan & privasi

- Jangan pernah mengunggah nama, NIK, nomor HP, atau alamat pedagang. Berkas dengan kolom semacam itu ditolak otomatis.
- Kunci API hanya disimpan sebagai GitHub Secrets.
- Angka pada dashboard adalah alat bantu analisis, bukan rilis resmi BPS; sinyal wajib diverifikasi manusia.

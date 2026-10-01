# Lintas Benteng Projection: Pemantauan Harga Pangan BPS Kabupaten Bengkulu Tengah

Pemantauan harga pangan berbasis AI dan Big Data untuk TPID.

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
| AI Data Finder | **Gratis**: Gemini + pencarian Google (utama), GitHub Models (cadangan, tanpa pencarian); Claude opsional. URL dicek silang dengan hasil pencarian dan dicek dapat dibuka (`pipeline/pencari_data.py`) |
| Buletin & laporan | Buletin mingguan, analisis bulanan, bahan rapat TPID triwulanan, evaluasi semesteran, laporan tahunan, siap cetak/PDF (`pipeline/laporan.py`, `site/laporan.html`) |
| Indikator kinerja | Indikator SMART Rancangan: ketepatan waktu, koreksi supervisor, kinerja model, stabilitas antar-segmen, uptime, waktu respons, IKM, persetujuan model (`pipeline/kinerja.py`, `site/kinerja.html`) |
| Notifikasi | Sinyal prioritas & buletin mingguan ke Telegram dan/atau email, tanpa kiriman ganda (`pipeline/notifikasi.py`) |
| Layanan publik | Pengaduan data & Survei Kepuasan Masyarakat (9 unsur PermenPANRB 14/2017) lewat GitHub Issue Forms (`pipeline/layanan.py`) |
| Layanan | Dashboard GitHub Pages (`site/`), GitHub Issues, unduhan CSV, log uptime per jam (`.github/workflows/uptime.yml`) |

Desain memakai gaya kaca (*glassmorphism*) dengan warna logo BPS. Tampilan bawaan terang. Ikon kecil di bagian bawah halaman (bukan di navbar) mengganti tampilan secara bergantian: Otomatis, Terang, Gelap. Hasil cetak selalu terang.

### Peran dan menu

Tiap peran punya menu dan beranda sendiri. Pengunjung tanpa login dianggap **Masyarakat**.

| Peran | Beranda | Menu |
|---|---|---|
| Masyarakat (tanpa login) | Harga Hari Ini | Beranda, Harga, Laporan, Tentang |
| Petugas Lapangan | Tugas Hari Ini | Beranda, Catat Harga, Harga, Tentang |
| Operator Data | Kondisi Data | Beranda, Cek Data, Sumber, Harga, Tentang |
| Analis | Meja Analis, lalu dashboard TPID di bawahnya | Beranda, Peringatan, Cek Data, Akurasi, Laporan, Harga, Tentang |
| TPID | Dashboard TPID (tata letak Gambar 12) | Beranda, Peringatan, Laporan, Capaian, Harga, Alur, Tentang |
| Administrator | Kondisi Sistem (ada bagian Data statis dan Data dinamis, lalu dashboard TPID di bawahnya) | semua menu, termasuk Pengaturan dan Pengguna |

Halaman: **Beranda** (berbeda per peran), **Harga**, **Peringatan**, **Laporan**, **Capaian**, **Cek Data** (Quality Gate), **Akurasi** (Mutu Model), **Sumber**, **Catat Harga** (dapat dipakai tanpa sinyal/PWA), **Alur** (tiruan Gambar 10 dan 11), **Pengguna**, **Tentang** (Tabel 4 dan 13).

### Login

Ada dua cara masuk, dipilih otomatis oleh pipeline (`meta.login`):

1. **Akun contoh** (bawaan). Akun ada di `config/pengguna.json` dengan kata sandi yang di-*hash* (SHA-256 berkaram). Lima akun peragaan tersedia: `petugas`, `operator`, `analis`, `tpid`, `admin`, semuanya berkata sandi `lintas2026`. Tambah akun dengan `python -m pipeline sandi NAMA "kata sandi" --nama "Nama Lengkap" --peran analis`, lalu salin hasilnya ke `config/pengguna.json`. **Ganti atau hapus akun contoh sebelum dipakai sungguhan**, karena kata sandinya tertulis di dokumen ini.
2. **Firebase Authentication** (belum diuji dengan proyek Firebase sungguhan). Salin `config/firebase.contoh.json` menjadi `config/firebase.json` dan isi konfigurasi web Firebase (kunci ini memang publik, keamanannya ada di aturan Firestore). Peran tiap pengguna diambil dari dokumen Firestore `pengguna/{uid}` berisi `peran` dan `nama`. Bila `config/firebase.json` terisi, akun contoh tidak dipakai lagi.

**Batas yang perlu dipahami:** situs ini statis, jadi login hanya mengatur *tampilan* (menu dan beranda). Berkas di `data/` tetap dapat dibuka siapa pun yang tahu alamatnya. Pembatasan sungguhan membutuhkan Firebase Authentication dengan aturan Firestore, dan data sensitif disimpan di tempat yang tertutup.

### Panel pengaturan (admin)

Halaman **Pengaturan** (hanya Administrator) mengumpulkan semua yang perlu diatur di satu tempat, tanpa membuka GitHub:

| Tab | Isinya |
|---|---|
| AI | AI yang dipakai, urutan cadangan, nama model, dan kunci Gemini atau Claude |
| Notifikasi | Kapan pesan dikirim, kunci Telegram dan email, catatan tindak lanjut di GitHub Issues |
| Prakiraan | Jarak prakiraan, harga normal, pengujian, hari raya |
| Peringatan | Kapan harga dianggap janggal atau polanya berubah |
| Data | Jenis data (contoh atau asli), hari dan jam kirim, pemeriksaan data |
| Target dan layanan | Target kinerja dan tautan pengaduan atau survei |
| Jalankan | Perbarui data sekarang, atau cari sumber data dengan AI |

Cara kerjanya:

- Admin menyambungkan panel dengan **token GitHub** miliknya sendiri (lihat "Cara membuat token" di halaman). Sebaiknya token *fine-grained*, hanya untuk repositori ini, dengan izin **Contents**, **Secrets**, dan **Actions** = *Read and write*, berumur pendek.
- **Isian pengaturan** disimpan sebagai satu commit pada `config/pengaturan.json`. Commit itu memicu pembaruan otomatis. Yang ditimpa hanya isian yang diubah, jadi perubahan orang lain tidak hilang. Kalau isian yang sama berubah di GitHub, panel menolak dan meminta dimuat ulang.
- **Kunci API** dienkripsi di browser (*sealed box*, sama dengan libsodium) lalu disimpan sebagai **GitHub Secrets**. GitHub tidak pernah mengembalikan nilainya, jadi panel hanya bisa menampilkan "sudah diisi" dan mengganti atau menghapusnya.
- Token hanya hidup di tab yang sedang dibuka (`sessionStorage`) dan hilang saat tab ditutup. Halaman ini dikunci dengan *Content-Security-Policy*: hanya skrip dari situs sendiri dan hanya boleh berhubungan dengan situs sendiri dan `api.github.com`. Pustaka enkripsinya (`site/vendor/sealedbox/`) ikut di repositori, tidak dimuat dari CDN.
- Semua isian punya rentang aman yang sama di panel dan di pipeline (`config/skema_pengaturan.json`, diperiksa oleh `pipeline/pengaturan.py`). Nilai di luar rentang ditolak panel, dan kalau ada yang lolos lewat penyuntingan manual, pipeline berhenti dengan pesan jelas dan dashboard lama tetap tampil.

**Yang sengaja tidak ada di panel:** jadwal otomatis (`.github/workflows/`), daftar kolom terlarang untuk menjaga privasi, `wilayah_target` dan `zona_waktu`, serta akun login. Semuanya tetap diubah lewat berkas di repositori.

**Yang perlu dipahami:** peran Administrator hanya mengatur tampilan. Yang benar-benar melindungi panel adalah token GitHub, karena tanpa token halaman ini hanya bisa dibaca dan tidak bisa mengubah apa pun.

Menambah isian baru: tambahkan di `config/skema_pengaturan.json` (label, rentang, bantuan) dan pakai nilainya di kode pipeline. Panel dan validasi ikut menyesuaikan. Kalau menambah `secrets.NAMA` di workflow, daftarkan juga namanya di bagian `rahasia` skema (ada uji yang memeriksa keduanya sama).

## Menerbitkan ke GitHub Pages (sekali saja)

1. Gabungkan kode ini ke cabang `main`.
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. **Actions → Pipeline & Dashboard → Run workflow** (atau tunggu jadwal). Setelah selesai, dashboard tersedia di
   `https://<pemilik>.github.io/<nama-repo>/`.
4. (Opsional) Isi kunci lewat halaman **Pengaturan** (lebih mudah), atau langsung di **Settings → Secrets and variables → Actions → New repository secret**. Semuanya gratis:
   - `GEMINI_API_KEY`: AI Data Finder dengan pencarian Google (kunci gratis dari https://aistudio.google.com/apikey).
     Tanpa kunci ini AI Data Finder otomatis memakai GitHub Models (gratis, tanpa pencarian web).
   - `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`: notifikasi ke grup Telegram TPID.
   - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_KE` (+ `EMAIL_DARI`): notifikasi email (mis. Gmail + App Password).
   - `ANTHROPIC_API_KEY`: hanya bila memilih Claude (berbayar).
5. (Disarankan) **Settings → Branches**: lindungi `main` dan batasi kolaborator yang boleh mengunggah data.

Selama `data/masuk/harga/` belum berisi berkas CSV/Excel, sistem berjalan dalam **mode demo** dengan data sintetis
berlabel jelas. Mode demo otomatis mati saat berkas harga nyata pertama diunggah.

## Operasional harian

Panduan lengkap per peran: [`docs/PANDUAN_OPERASIONAL.md`](docs/PANDUAN_OPERASIONAL.md).

1. **Petugas** masuk, lalu mencatat harga di halaman *Catat Harga* → *Unduh CSV* / *Bagikan*.
2. **Operator** mengunggah CSV ke `data/masuk/harga/` → pipeline berjalan otomatis → dashboard diperbarui.
3. **Validator** memutuskan antrean di halaman *Cek Data* → unggah berkas keputusan ke `data/validasi/`.
4. **Analis/TPID** memverifikasi sinyal lewat GitHub Issues berlabel `sinyal-harga` (label `status: …`).

## Menjalankan secara lokal

```bash
pip install -r requirements.txt
python -m pytest -q                                   # 124 uji otomatis (termasuk uji JavaScript panel admin bila Node.js 20+ terpasang)
node --test tests_js/*.test.mjs                       # hanya uji JavaScript (enkripsi kunci, klien GitHub, validasi)
python -m pipeline periksa                            # validasi berkas di data/masuk
python -m pipeline jalankan --keluaran site/data --tanpa-github
python -m http.server -d site 8000                    # buka http://localhost:8000
python -m pipeline ambil-cuaca                        # konektor cuaca (butuh internet)
GEMINI_API_KEY=... python -m pipeline cari-sumber --komoditas "cabai rawit merah" --periode "Oktober 2026"
```

## Konfigurasi (`config/`)

| Berkas | Isi |
|---|---|
| `komoditas.csv` | 10 komoditas / 21 varian (Tabel 2 Rancangan Aksi Perubahan) + 9 item tambahan kajian Bapokting (`aktif=0`), satuan, kelompok, batas kewajaran |
| `wilayah.csv` | Bengkulu Tengah (target), Kepahiang & Kota Bengkulu (pembanding) |
| `pasar.csv` | Pasar, koordinat, status blank spot |
| `sumber.csv` | Inventaris sumber data, metode akses, status, prioritas rekonsiliasi |
| `kalender.csv` | Hari raya & libur (status `pasti`/`perkiraan`) |
| `batas_wilayah.geojson` | (Opsional) batas kecamatan/kabupaten dari BPS. Bila ada, otomatis tampil di peta beranda |
| `pengguna.json` | Akun contoh untuk login per peran (kata sandi di-*hash*). Diterbitkan ke `site/data/pengguna.json` |
| `firebase.json` | (Opsional, salin dari `firebase.contoh.json`) Konfigurasi web Firebase untuk login sungguhan |
| `skema_pengaturan.json` | Daftar isian yang bisa diubah lewat panel Pengaturan: label, rentang aman, dan nama kunci GitHub Secrets. Dipakai panel dan validasi pipeline |
| `pengaturan.json` | Ambang quality gate, sinyal, model, target kinerja, privasi, tindak lanjut, penyedia AI, notifikasi, layanan |

## Yang wajib dikonfirmasi sebelum dipakai sebagai dasar keputusan

- Daftar komoditas final (10/21 Rancangan vs 21 Bapokting kajian); keduanya sudah tersedia di `komoditas.csv`.
- Batas kewajaran harga per varian dan koordinat pasar (saat ini nilai awal/perkiraan).
- Daftar pasar target lengkap (baru Pasar Taba Penanjung dan Karang Tinggi) dan 8 wilayah blank spot.
- Izin pengambilan otomatis sumber eksternal (PIHPS, Panel Harga Bapanas), saat ini berstatus kandidat.
- Kebijakan publikasi: repo & situs **publik**; pastikan data per pasar dan diskusi tindak lanjut boleh dibuka.
- Ambang model (sMAPE, F1, recall, cakupan) adalah target rancangan; kalibrasi ulang setelah baseline pilot.

## Keamanan & privasi

- Jangan pernah mengunggah nama, NIK, nomor HP, atau alamat pedagang. Berkas dengan kolom semacam itu ditolak otomatis.
- Kunci API hanya disimpan sebagai GitHub Secrets (diisi lewat panel Pengaturan atau langsung di GitHub). Token GitHub admin hanya hidup di tab panel dan tidak pernah disimpan di repositori.
- Angka pada dashboard adalah alat bantu analisis, bukan rilis resmi BPS; sinyal wajib diverifikasi manusia.

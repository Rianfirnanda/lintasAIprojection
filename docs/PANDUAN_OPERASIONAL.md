# Panduan Operasional

Panduan per peran untuk sistem pemantauan harga pangan BPS Kabupaten Bengkulu Tengah.

## 1. Petugas lapangan (pencatat harga)

1. Buka halaman **Input Harga** di dashboard satu kali saat ada sinyal (halaman tersimpan untuk dipakai luring).
   Di ponsel Android/iOS dapat dipasang ke layar utama ("Tambahkan ke layar utama").
2. Isi tanggal, pasar, kode petugas, dan kode responden anonim (R1, R2, …). **Jangan** menulis nama/NIK/HP pedagang.
3. Isi harga per varian. Satuan dapat diubah (mis. ons); sistem mengonversi otomatis ke kg/liter.
   Peringatan merah berarti harga di luar batas kewajaran. Periksa ulang, tetapi data tetap boleh disimpan.
4. Tekan **Simpan ke antrean perangkat**. Data tetap tersimpan walau tidak ada sinyal (wilayah blank spot).
5. Saat ada sinyal, tekan **Unduh CSV** atau **Bagikan** (WhatsApp/email) ke operator.
6. Setelah operator mengonfirmasi, tekan **Hapus yang sudah dikirim**.

Batas tepat waktu: data hari pencatatan diinput paling lambat pukul 14.00 WIB (`jam_batas_tepat_waktu`).

## 2. Operator data

1. Terima CSV dari petugas (atau siapkan CSV/Excel sesuai `docs/templat/templat_harga.csv`).
2. Di GitHub buka `data/masuk/harga/` → **Add file → Upload files** → seret berkas → **Commit changes**.
   Gunakan nama berkas unik, mis. `2026-10-09_PSR01_PTG01.csv`. **Jangan mengedit atau menghapus berkas lama**, karena
   berkas mentah adalah jejak audit; koreksi dilakukan lewat keputusan validator.
3. Pipeline berjalan otomatis (tab **Actions → Pipeline & Dashboard**). Bila ingin memeriksa sebelum masuk `main`,
   unggah ke cabang baru dan buat pull request: workflow **Periksa data & kode** akan melaporkan baris yang ditolak.
4. Data Pemda (stok, pasokan, biaya angkut) diunggah ke `data/masuk/konteks/` dengan format
   `docs/templat/templat_konteks.csv`. Nama indikator stok/pasokan diawali `stok_` atau `pasokan_` agar muncul sebagai
   konteks sinyal.

### Kode yang dipakai

- Pasar: `config/pasar.csv` (PSR01 Taba Penanjung, PSR02 Karang Tinggi, PSR91 Kepahiang, PSR92 Panorama).
- Varian: `config/komoditas.csv` (BRS01–BRS06, DAY01, TLR01, DSP01–02, BWM01, BWP01, CMR01–02, CRW01–02, MGR01–03, GLP01–02).
- Sumber: `config/sumber.csv` (PSR-ENUM, BPS-HRG, PMD-DISDAG, …).

## 3. Validator (quality gate)

1. Buka halaman **Quality Gate**. Bagian *Antrean validasi manusia* berisi observasi yang ditahan beserta tandanya:
   - `di_luar_batas_wajar`: kemungkinan salah ketik/satuan.
   - `perubahan_ekstrem` / `pencilan_statistik`: lonjakan yang tidak didukung pasar/responden lain.
   - `duplikat_konflik`: kunci sama, harga berbeda.
2. Konfirmasi ke petugas bila perlu, pilih **Terima** atau **Tolak**, isi alasan dan nama validator.
3. Tekan **Unduh berkas keputusan** dan unggah ke `data/validasi/`. Pada jalannya pipeline berikutnya, observasi yang
   diterima masuk analisis; yang ditolak dikeluarkan (berkas mentah tetap utuh).

Catatan: lonjakan yang dikonfirmasi oleh pasar/responden lain pada hari yang sama, atau bertahan pada observasi
berikutnya di pasar yang sama, otomatis dianggap nyata dan tidak perlu divalidasi manual.

## 4. Analis & TPID (tindak lanjut sinyal)

1. Dashboard → **Komoditas prioritas** dan halaman **Sinyal & Tindak Lanjut**.
2. Sinyal anomali berkeparahan tinggi (data nyata) otomatis dibuatkan **GitHub Issue** berlabel `sinyal-harga`
   (maks. 5 per jalan). Di issue:
   - verifikasi ke lapangan/sumber pendukung (konteks otomatis tercantum di issue),
   - pasang **satu** label status: `status: terverifikasi`, `status: false-alarm`, `status: ditindaklanjuti`, `status: selesai`,
   - tulis temuan dan tindakan di komentar; tutup issue bila selesai.
3. Tanpa Issues, gunakan buku `data/tindak_lanjut/` (baris dibuat dari halaman Sinyal).
4. Bila ada gejolak nyata yang **tidak** terdeteksi, catat `anomali_terlewat` agar recall model terukur.
5. Target Rancangan: ≥ 75% sinyal prioritas tervalidasi ditindaklanjuti; forum TPID minimal triwulanan.

## 5. AI Data Finder (gratis)

1. (Disarankan) Buat kunci gratis Gemini di https://aistudio.google.com/apikey lalu simpan sebagai secret
   `GEMINI_API_KEY` (**Settings → Secrets and variables → Actions → New repository secret**). Kuota gratis dapat
   berubah; cek ketentuan terbaru Google AI Studio.
2. **Actions → AI Data Finder → Run workflow**, isi komoditas, periode, jenis data, wilayah, dan penyedia
   (`otomatis` = Gemini, lalu GitHub Models bila Gemini belum diatur/kuota habis).
3. Hasil tersimpan di `data/sumber/kandidat_ai.json` dan tampil di halaman **Sumber Data**:
   - *URL di hasil pencarian?* "tidak" = URL tidak muncul di hasil pencarian Google, jadi periksa dengan saksama.
   - *URL dapat dibuka?* "tidak" = alamat tidak bisa dibuka (kemungkinan dikarang/berubah).
   - Hasil GitHub Models ditandai **tanpa pencarian web**: semua URL wajib dicek manual.
4. Verifikasi kandidat (izin, lisensi, cakupan, keandalan). Bila layak, tambahkan ke `config/sumber.csv`.
   Kandidat tidak pernah otomatis menjadi sumber data.

## 6. Buletin, laporan, dan notifikasi

- Halaman **Laporan**: buletin mingguan, analisis bulanan, bahan rapat TPID triwulanan. Pilih periode lalu
  **Cetak / Simpan PDF**. Rekomendasi di dalamnya disusun otomatis dan wajib ditelaah analis.
- **Notifikasi Telegram** (gratis): buat bot lewat @BotFather → salin token → tambahkan bot ke grup TPID →
  dapatkan `chat_id` grup (mis. kirim pesan di grup lalu buka `https://api.telegram.org/bot<TOKEN>/getUpdates`).
  Simpan sebagai secret `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID`.
- **Notifikasi email** (gratis, mis. Gmail): aktifkan verifikasi 2 langkah → buat *App Password* → secret
  `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=465`, `SMTP_USER`, `SMTP_PASSWORD` (App Password), `EMAIL_KE`.
- Yang dikirim: sinyal aktif keparahan ≥ sedang yang belum pernah dikirim, dan buletin mingguan setelah minggu
  berakhir. Catatan kiriman di `data/notifikasi/terkirim.json`. Mode demo tidak mengirim notifikasi.

## 7. Indikator kinerja, persetujuan model, dan layanan publik

- Halaman **Kinerja** menampilkan capaian indikator SMART Rancangan (ketepatan waktu, koreksi supervisor, model,
  uptime, waktu respons, IKM, dll.). Indikator yang belum dapat dihitung ditandai jelas beserta alasannya.
- **Persetujuan model**: di halaman **Mutu Model** centang model rekomendasi yang disetujui → isi nama penyetuju →
  *Unduh berkas persetujuan* → unggah ke `data/persetujuan_model/`. Untuk mewajibkan persetujuan, ubah
  `analisis.wajib_persetujuan_model` menjadi `true` di `config/pengaturan.json`.
- **Uptime**: workflow **Uptime** memeriksa dashboard setiap jam; log di cabang `log-uptime` (jangan dihapus).
- **Pengaduan & SKM**: tautan di kaki setiap halaman membuka formulir GitHub (butuh akun GitHub; bersifat publik).
  Untuk responden tanpa akun GitHub, isi `layanan.url_pengaduan_eksternal` (mis. tautan WhatsApp/PST) dan
  `layanan.url_survei_eksternal` (mis. Google Form) di `config/pengaturan.json`. Tanggapi pengaduan di kolom komentar
  issue lalu tutup issue bila selesai.

## 8. Admin

- **Menambah pasar**: tambahkan baris di `config/pasar.csv` (isi koordinat dari peta, `koordinat_terverifikasi=1`,
  `blank_spot=1` bila perlu).
- **Mengaktifkan item kajian Bapokting**: ubah `aktif` menjadi `1` di `config/komoditas.csv`.
- **Mengubah ambang**: `config/pengaturan.json` (setiap perubahan tercatat di git, jadi tulis alasan di pesan commit).
- **Tanggal hari raya**: perbarui `config/kalender.csv` setelah SKB 3 Menteri terbit (`status=pasti`).
- **Jadwal**: `.github/workflows/pipeline.yml` (cron dalam UTC; WIB = UTC+7). GitHub menonaktifkan workflow terjadwal
  pada repo publik yang tidak ada aktivitas selama 60 hari. Commit data rutin mencegah hal ini.
- **Mode demo**: `mode_demo` di `pengaturan.json` (`otomatis` / `ya` / `tidak`) atau input saat *Run workflow*.

## 9. Pemecahan masalah

| Gejala | Penyebab umum | Tindakan |
|---|---|---|
| Dashboard masih "DATA DEMO" | Belum ada CSV/Excel di `data/masuk/harga/` | Unggah berkas harga pertama |
| Berkas "GAGAL" di Quality Gate | Kolom wajib hilang / kolom data pribadi | Perbaiki header sesuai templat |
| Banyak baris ditolak | Kode pasar/varian salah, tanggal masa depan, satuan tak dikenal | Lihat alasan per baris di Quality Gate |
| Notifikasi tidak terkirim | Secret belum diatur, mode demo, atau kanal menolak | Lihat `pesan_notifikasi` di `site/data/meta.json` / log Actions |
| Issue tidak dibuat | Mode demo, keparahan < tinggi, atau `github_issues=false` | Periksa `pengaturan.json` dan pesan sinkronisasi di halaman Sinyal |
| Workflow deploy gagal "Pages not enabled" | Pages belum diaktifkan | Settings → Pages → Source: GitHub Actions |
| Cuaca tidak bertambah | API Open-Meteo tidak terjangkau | Langkah konektor bersifat `continue-on-error`; cek log Actions |

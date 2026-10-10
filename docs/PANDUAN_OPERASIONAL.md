# Panduan Operasional

Panduan per peran untuk sistem pemantauan harga pangan BPS Kabupaten Bengkulu Tengah.

## 0. Masuk sesuai peran

Buka halaman **Masuk** (tombol di kanan atas). Setiap peran melihat menu dan beranda yang berbeda. Tanpa login, Anda melihat tampilan **Masyarakat**.

| Peran | Akun contoh | Untuk apa |
|---|---|---|
| Petugas Lapangan | `petugas` | Mencatat harga di pasar |
| Operator Data | `operator` | Mengunggah berkas dan memantau mutu data |
| Analis | `analis` | Memeriksa data, peringatan, dan model |
| TPID | `tpid` | Memantau dashboard dan mengambil keputusan |
| Administrator | `admin` | Mengelola sistem dan pengguna |

Kata sandi semua akun contoh: `lintas2026`. Akun ini hanya untuk peragaan.

**Setelah Firebase aktif** (lihat `docs/FIREBASE.md`), akun contoh tidak dipakai lagi. Halaman Masuk berganti menjadi
tombol **Masuk dengan Google**. Akun baru menunggu persetujuan admin, lalu admin memberi peran dan izin halaman.

Ingat: login dan persetujuan dijaga aturan Firestore, tetapi berkas data dashboard tetap terbuka bagi umum.

## 1. Petugas lapangan (pencatat harga)

1. Masuk sebagai petugas, lalu buka halaman **Catat Harga** di dashboard satu kali saat ada sinyal (halaman tersimpan untuk dipakai luring).
   Di ponsel Android/iOS dapat dipasang ke layar utama ("Tambahkan ke layar utama").
2. Isi tanggal, pasar, kode petugas, dan kode responden anonim (R1, R2, …). **Jangan** menulis nama/NIK/HP pedagang.
3. Isi harga per varian. Satuan dapat diubah (mis. ons); sistem mengonversi otomatis ke kg/liter.
   Peringatan merah berarti harga di luar batas kewajaran. Periksa ulang, tetapi data tetap boleh disimpan.
4. Tekan **Simpan**. Data tetap tersimpan walau tidak ada sinyal (wilayah blank spot).
5. **Dengan login Google:** tombolnya **Simpan dan kirim**. Harga langsung terkirim ke sistem; tanpa sinyal, harga
   aman di HP dan terkirim sendiri begitu ada sinyal. Kolom *Dikirim* menjadi *ya* setelah diterima. Selesai.
6. **Tanpa login Google:** saat ada sinyal, tekan **Unduh CSV** atau **Bagikan** (WhatsApp/email) ke operator. Setelah
   operator mengonfirmasi, tekan **Bersihkan yang terkirim**.

Batas tepat waktu: data hari pencatatan diinput paling lambat pukul 14.00 WIB (`jam_batas_tepat_waktu`).

## 2. Operator data

**Dengan login Google:** buka **Cek Data** → kartu **Unggah berkas harga** → pilih berkas CSV → **Kirim ke sistem**.
Keputusan terima/tolak disimpan dengan **Simpan keputusan** di halaman yang sama. Tidak perlu membuka GitHub. Langkah
di bawah hanya untuk situs tanpa login Google.

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

1. Buka halaman **Cek Data** (Quality Gate). Bagian *Antrean validasi manusia* berisi observasi yang ditahan beserta tandanya:
   - `di_luar_batas_wajar`: kemungkinan salah ketik/satuan.
   - `perubahan_ekstrem` / `pencilan_statistik`: lonjakan yang tidak didukung pasar/responden lain.
   - `duplikat_konflik`: kunci sama, harga berbeda.
2. Konfirmasi ke petugas bila perlu, pilih **Terima** atau **Tolak**, isi alasan dan nama validator.
3. Tekan **Unduh berkas keputusan** dan unggah ke `data/validasi/`. Pada jalannya pipeline berikutnya, observasi yang
   diterima masuk analisis; yang ditolak dikeluarkan (berkas mentah tetap utuh).

Catatan: lonjakan yang dikonfirmasi oleh pasar/responden lain pada hari yang sama, atau bertahan pada observasi
berikutnya di pasar yang sama, otomatis dianggap nyata dan tidak perlu divalidasi manual.

## 4. Analis & TPID (tindak lanjut sinyal)

1. Dashboard → **Komoditas prioritas** dan halaman **Peringatan**. Klik kotak **Sinyal prioritas** di bagian atas
   untuk melihat komoditas mana yang sedang jadi prioritas, harganya dibanding harga biasa, sejak kapan, statusnya,
   dan langkah berikutnya. Kotak lain (ketepatan waktu, *blank spot*, dan seterusnya) juga bisa diklik.
   Kartu komoditas menampilkan harga sekarang, harga sebulan lalu, dan kenaikannya dalam rupiah.
2. Sinyal anomali berkeparahan tinggi (data nyata) otomatis dibuatkan **GitHub Issue** berlabel `sinyal-harga`
   (maks. 5 per jalan). Di issue:
   - verifikasi ke lapangan/sumber pendukung (konteks otomatis tercantum di issue),
   - pasang **satu** label status: `status: terverifikasi`, `status: false-alarm`, `status: ditindaklanjuti`, `status: selesai`,
   - tulis temuan dan tindakan di komentar; tutup issue bila selesai.
3. Tanpa Issues, gunakan buku `data/tindak_lanjut/` (baris dibuat dari halaman Sinyal).
4. Bila ada gejolak nyata yang **tidak** terdeteksi, catat `anomali_terlewat` agar recall model terukur.
5. Target Rancangan: ≥ 75% sinyal prioritas tervalidasi ditindaklanjuti; forum TPID minimal triwulanan.

## 4b. Big Data resmi otomatis (BMKG dan PIHPS)

Setiap kali pipeline jalan, `python -m pipeline ambil-resmi` mengambil:

- **Prakiraan cuaca BMKG** 3 hari ke depan (api.bmkg.go.id, data terbuka; sebutkan BMKG sebagai sumber) untuk desa
  Taba Terunjam (Karang Tinggi, Bengkulu Tengah) dan Pagar Dewa (Kota Bengkulu). Disimpan di
  `data/masuk/konteks/prakiraan_bmkg_<tahun>.csv`. Bila hujan 3 hari ke depan diperkirakan 60 mm atau lebih,
  peringatan harga menyebutkannya.
- **Harga PIHPS Bank Indonesia**: rata-rata pasar tradisional Provinsi Bengkulu untuk 21 varian yang sama dengan
  daftar varian sistem. Disimpan di `data/masuk/konteks/harga_pihps_<tahun>.csv` (riwayat sekitar setahun diambil
  sekali, lalu 45 hari terakhir tiap jalan). Tampil sebagai garis pembanding "Provinsi Bengkulu (PIHPS BI)" di grafik
  harga dan disebut di peringatan ("harga Bengkulu Tengah +x% dari rata-rata provinsi").
- **PIHPS tingkat kabupaten/kota.** Daftar kabupaten/kota PIHPS Provinsi Bengkulu dibaca otomatis (`GetRefRegency`), lalu yang namanya sama dengan
  wilayah di `config/wilayah.csv` (mis. Kota Bengkulu) diambil harganya ke `data/masuk/konteks/pihps_kota_<tahun>.csv`. Wilayah yang tidak ada di PIHPS
  dilewati, tidak ditebak. Hasilnya muncul sebagai garis pembanding di grafik dan panel perbandingan wilayah di Dasbor Analitik, tanpa masuk ke harga utama.
  **Temuan penjajakan (10 Oktober 2026):** di PIHPS, Provinsi Bengkulu hanya punya **satu kota, Kota Bengkulu** (satu pasar tradisional, empat pasar modern,
  17 pedagang besar, dan produsen). Angka "Provinsi Bengkulu" yang dipakai sementara sebenarnya adalah harga pasar Kota Bengkulu. Kepahiang dan Bengkulu
  Tengah tidak ada di PIHPS.
- **Panel Harga Bapanas** belum bisa diambil otomatis: server datanya tidak menjawab permintaan dari luar Indonesia
  (server GitHub ada di luar negeri). Perlu akses API resmi dari Bapanas, atau unduh tabelnya dan unggah manual.

Bila salah satu sumber gangguan, pipeline tetap jalan; galatnya tercatat di log langkah "Ambil prakiraan BMKG dan
harga PIHPS".

## 4c. Data asli sementara: PIHPS Provinsi Bengkulu

Harga tingkat Kabupaten Bengkulu Tengah hanya dimiliki BPS dan petugas lapangan. Sebelum datanya masuk, sistem berjalan dalam
**mode data asli** memakai rata-rata harga pasar tradisional **Provinsi Bengkulu** dari PIHPS Bank Indonesia. Dashboard menampilkan
pita "Data asli sementara" supaya tidak ada yang mengira ini harga Bengkulu Tengah.

- **Alurnya.** Konektor mengambil PIHPS (`data/masuk/konteks/harga_pihps_*.csv`), lalu `python -m pipeline pihps-ke-harga` menyalinnya menjadi
  `data/masuk/harga/pihps_provinsi_<tahun>.csv` (pasar `PHP17`). Berkas hasil salinan selalu ditulis ulang otomatis; jangan diedit tangan.
  Adanya berkas harga mematikan mode demo dengan sendirinya.
- **Wilayah sasaran.** `wilayah_target` di `config/pengaturan.json` sementara bernilai `17` (Provinsi Bengkulu).
- **Menambah riwayat beberapa tahun.** Jalankan alur kerja **Riwayat harga PIHPS** di GitHub Actions (isi jumlah hari, bawaan 1460 = 4 tahun).
  Ia mengambil per 90 hari dengan jeda, menyalin ke harga utama, lalu memperbarui dashboard. Pembaruan harian biasa hanya 45 hari terakhir.
  Bila ada periode yang gagal diambil, alasannya ada di log langkah "Ambil riwayat PIHPS".
- **Beralih ke data BPS Bengkulu Tengah.** Unggah berkas harga BPS ke `data/masuk/harga/`, ubah `wilayah_target` menjadi `1709`, hapus berkas
  `pihps_provinsi_*.csv`, dan hapus langkah "Salin harga PIHPS" di `.github/workflows/pipeline.yml`. Pita sementara hilang sendiri.
- **Yang perlu dipahami saat membaca hasilnya.** Ini harga rata-rata provinsi, bukan Bengkulu Tengah. Harga PIHPS sangat mulus (sering sama
  berhari-hari), sehingga cara paling sederhana (harga terakhir) sulit dikalahkan model lain. Target "10% lebih baik dari cara sederhana" wajar
  tidak tercapai pada data ini, dan itu bukan kesalahan model.

## 4d. Proyeksi, status Valid/Eksperimen, dan Dasbor Analitik

Halaman **Dasbor Analitik** (menu Analis, TPID, dan Admin) memuat semua yang diminta rancangan: indikator di atas, pilihan varian dan
horizon 7/14/30 hari, tabel 21 varian (bisa diurutkan dan diekspor ke CSV), grafik tren dan proyeksi, diagnostik deret waktu, kinerja
model, proyeksi hari raya, proyeksi triwulanan/semesteran/tahunan, rekomendasi netral, dan jejak data. Angkanya dibaca dari
`analitik.json`, `proyeksi_acara.json`, dan `proyeksi_periodik.json` yang dibuat tiap pipeline jalan.

- **Proyeksi harian.** 7, 14, dan 30 hari ke depan dengan rentang 80%. Rentang dibentuk dari selisih prakiraan dan kenyataan pada uji data
  lama (konformal), bukan dari rumus tebakan.
- **Uji akhir (holdout).** 90 hari terakhir disisihkan dan tidak dipakai memilih cara prakiraan. Hasilnya dinilai dengan sMAPE, MASE, bias,
  akurasi arah, dan cakupan rentang 80%. MASE memakai skala galat cara naif pada horizon yang sama, dihitung dari data sebelum masa uji.
- **Status.** **Valid** hanya bila semua syarat Protokol Validasi lolos: riwayat minimal 730 hari, kelengkapan minimal 95%, sMAPE di bawah
  batas kelompok (pokok dan pabrikan 5%, protein 10%, volatil 15%), bias paling banyak 3% (kelas rendah) atau 5%, MASE di bawah 1, cakupan 75
  sampai 85%, dan khusus komoditas volatil akurasi arah minimal 60%. Selain itu **Eksperimen**: tetap tampil, berlabel eksperimen, dan bukan
  angka resmi. Syarat yang gagal tertera di panel "Kinerja model pada data uji akhir".
- **Tingkat keyakinan.** Tinggi bila semua syarat lolos, Sedang bila hanya satu syarat gagal, Rendah bila lebih. Ini aturan, bukan angka karangan.
- **Uji Diebold-Mariano.** Mesin belajar atau gabungan yang terbukti lebih buruk dari cara naif pada masa uji akhir dikembalikan ke juara
  cara sederhana.
- **Hari raya.** Menuju Hari H dari H-7 dan H-3, sesudahnya H+3, H+7, H+14, untuk Idul Fitri, Idul Adha, dan Natal. Cara: harga titik asal
  dikalikan median perubahan pada hari raya sejenis sebelumnya, diuji dengan menyisihkan satu hari raya bergiliran (butuh minimal 3).
  Proyeksi aktif baru muncul setelah titik asalnya tiba (mis. Natal mulai 18 Desember), dihitung dari harga pada hari itu. Selama hari raya
  sejenis kurang dari 8, cakupan rentang belum bisa dinilai, jadi statusnya Eksperimen. Kalender `config/kalender.csv` kini memuat 2022
  sampai 2027; tanggal 2022 sampai 2026 sesuai keputusan sidang isbat dan SKB pemerintah.
- **Triwulanan, semesteran, tahunan.** Rata-rata harga bulanan dengan skenario rendah, dasar, tinggi (kuantil 10%, 50%, 90% galat uji
  bulanan). Syarat riwayat: 36 bulan (triwulanan), 48 bulan (semesteran), 60 bulan (tahunan). Yang belum terpenuhi tampil "Menunggu data" beserta
  kekurangannya, tanpa angka.
- **Faktor yang terukur.** Perubahan 7 dan 30 hari, rezim naik-turun harga, kekuatan pola mingguan, kenaikan puncak menjelang hari raya, dan
  pergeseran pola (PSI). Ini **bukan SHAP**: model yang dipakai belum menghasilkan penjelasan per fitur.
- **Yang menunggu data.** Harga Kepahiang dan Kota Bengkulu, skor kesepakatan antar sumber (butuh minimal dua sumber harga pada tanggal yang
  sama). Panel terkait terisi otomatis begitu datanya masuk; sampai saat itu tertulis "menunggu data".
- **Jejak dan versi.** Setiap keluaran mencatat versi data (hash berkas harga), versi konfigurasi (hash pengaturan), commit, dan SHA-256 tiap
  berkas sumber. Model deterministik, jadi data dan konfigurasi yang sama selalu memberi hasil yang sama. Registri model
  (`data/registry/model_registry.json`) mencatat keadaan terkini dan riwayat pergantian cara prakiraan tiap varian; ditulis hanya untuk data asli
  dan disimpan ke repositori oleh pipeline. Kartu model per varian (tujuan, data, cara memilih, keterbatasan) ada di panel Ringkasan varian.
- **Mengubah batas.** Semua ambang protokol ada di satu tempat, `VALIDASI_BAWAAN` di `pipeline/analisis.py`. Mengubahnya sebaiknya lewat
  keputusan tim, karena menggeser definisi "Valid" untuk semua varian. Horizon (30 hari) dan tingkat rentang (80%) ada di panel Pengaturan.

## 5. AI Data Finder (gratis)

1. (Disarankan) Buat kunci gratis Gemini di https://aistudio.google.com/apikey. Gemini satu-satunya AI gratis di sini
   yang bisa mencari di Google, jadi URL hasilnya paling bisa dipercaya.
2. (Cadangan, disarankan juga) Buat kunci gratis AI lain supaya pencarian tetap jalan saat kuota Gemini habis:

   | AI | Tempat membuat kunci | Nama kunci |
   |---|---|---|
   | Groq | https://console.groq.com/keys | `GROQ_API_KEY` |
   | Cerebras | https://cloud.cerebras.ai (menu API Keys) | `CEREBRAS_API_KEY` |
   | OpenRouter | https://openrouter.ai/keys | `OPENROUTER_API_KEY` |
   | Mistral | https://console.mistral.ai/api-keys (paket Experiment, perlu verifikasi nomor HP) | `MISTRAL_API_KEY` |

   Isi kuncinya di menu **Pengaturan → AI → Kunci AI** (atau sebagai GitHub Secret dengan nama di atas). Semuanya
   gratis tanpa kartu kredit; besar kuota gratis bisa berubah sewaktu-waktu sesuai kebijakan tiap layanan.
3. (Sangat disarankan) **Pencarian web gratis dengan Tavily.** AI gratis tidak bisa mencari di Google sendiri (Gemini
   versi 3 tidak menyediakan pencarian Google di kuota gratis). Tavily mencarikannya: mesin mencari di web lebih dulu
   (3 pencarian tiap permintaan, gratis 1.000 per bulan, tanpa kartu kredit), lalu AI menyusun kandidat hanya dari
   hasil pencarian itu.
   1. Buka https://app.tavily.com, pilih **Sign up**, lalu **Continue with Google**.
   2. Di halaman **Overview**, bagian **API Keys**, salin kunci *default* (berawalan `tvly-`). Pastikan paketnya
      **Researcher (Free)**.
   3. Tempel di **Pengaturan → AI → Pencarian web → Kunci Tavily**, lalu **Simpan kunci yang diisi**.
   Bila kuota habis atau Tavily gangguan, AI tetap bekerja tanpa pencarian dan alasannya dicatat ("dilewati: tavily").
4. **Actions → AI Data Finder → Run workflow** (atau Pengaturan → Jalankan → *Cari sumber data dengan AI*), isi
   komoditas, periode, jenis data, wilayah, dan penyedia. `otomatis` mencoba AI sesuai *Urutan kalau memilih Otomatis*,
   lalu AI gratis lain yang belum disebut. AI yang kuncinya belum diisi, kena batas pemakaian, atau jawabannya rusak
   dilewati, dan alasannya dicatat di hasil ("dilewati: ...").
5. Hasil tersimpan di `data/sumber/kandidat_ai.json` dan tampil di halaman **Sumber Data**:
   - *URL di hasil pencarian?* "tidak" = URL tidak muncul di hasil pencarian Google, jadi periksa dengan saksama.
   - *URL dapat dibuka?* "tidak" = alamat tidak bisa dibuka (kemungkinan dikarang/berubah).
   - Hasil tanpa Tavily (dan selain Claude) ditandai **tanpa pencarian web**: semua URL wajib dicek manual.
6. Verifikasi kandidat (izin, lisensi, cakupan, keandalan). Bila layak, tambahkan ke `config/sumber.csv`.
   Kandidat tidak pernah otomatis menjadi sumber data.

## 5b. Berita lokal harian

Mesin mencari berita lokal tentang harga pangan, membaca isinya, mengambil harga yang disebut sebagai **kandidat**, lalu
menyusun kesimpulan harian. Hasilnya tampil di halaman **Berita Lokal** (menu Lainnya untuk analis, TPID, operator, dan admin).

**Jadwal.** Berjalan sendiri sekali sehari. Penjaga (`antrean.yml`) melihat bahwa jam 07.00 WIB sudah lewat dan berita hari
ini belum dicari, lalu memicu pembaruan harian yang memuat langkah ini. Jam mulainya bisa diubah di **Pengaturan → Berita lokal**.
Mau hasilnya sekarang: **Actions → Berita lokal → Run workflow** (atau, tanpa GitHub, Pengaturan → Jalankan → *Cari berita lokal sekarang*; permintaan dari panel tetap berjalan walau hari ini sudah dicari).
Prosesnya tercatat di **Log proses AI** (halaman Sumber Data) dengan keterangan "Berita lokal harian".

**Yang dikerjakan setiap hari:**

1. **Mencari.** Pencarian berita Tavily (hasilnya sudah memuat isi artikel), umpan RSS Google Berita untuk tiap kata kunci,
   dan umpan RSS portal berita yang diisi admin (`berita.umpan_rss` di `config/pengaturan.json`).
2. **Menyaring.** Duplikat dibuang (tautan yang sama, atau judul yang sama dari portal lain), begitu pula berita lebih lama
   dari `umur_maks_hari` dan yang berasal dari media sosial atau video. Berita yang tidak menyebut wilayah Bengkulu
   beserta topik pangan dibuang.
3. **Membaca.** Halaman artikel diunduh hanya bila `robots.txt` situsnya mengizinkan, dengan jeda antar permintaan, batas ukuran,
   dan nama bot yang jelas (`LintasBentengBot`). Halaman yang melarang, berbayar, atau memakai JavaScript hanya tampil dengan judulnya.
4. **Mengambil harga.** Dengan aturan baku (bukan AI): kalimat yang memuat komoditas, angka rupiah, dan satuan kg atau liter.
   Selisih kenaikan ("naik Rp 5.000"), harga per butir atau ikat, dan angka di luar batas wajar komoditas tidak dihitung
   sebagai harga. Setiap kandidat membawa kalimat buktinya dan wilayah yang disebut (Bengkulu Tengah, pembanding, provinsi,
   nasional, atau tidak jelas).
5. **Meringkas dan menyimpulkan.** AI gratis (rotasi yang sama dengan AI Data Finder) meringkas berita yang paling relevan dan menyusun
   kesimpulan harian. AI hanya boleh memakai fakta dari teks berita, dan kalimat yang memuat angka yang tidak ada di berita
   dibuang otomatis. Bila semua AI sedang tidak bisa dipakai, ringkasan dan kesimpulan disusun otomatis dari kalimat berita
   dan ditandai "ringkasan otomatis".

**Aturan yang tidak boleh dilanggar:**

- Harga dari berita **tidak pernah** masuk deret harga resmi atau perhitungan prakiraan. Statusnya selalu "kandidat, belum
  diverifikasi". Analis memeriksa kalimat buktinya dan membuka beritanya; bila layak dipakai, catat sebagai data biasa lewat
  jalur harga yang sudah ada.
- Isi lengkap artikel **tidak disimpan** (hak cipta penerbit). Yang disimpan: tautan, judul, ringkasan, kutipan pendek, kalimat bukti,
  dan sidik SHA-256 isi artikel pada saat dibaca (`data/berita/berita.json`).
- Berita sering menyebut harga di wilayah lain atau rata-rata nasional. Kolom "Berlaku untuk" di halaman menunjukkan wilayahnya.

**Pengaturan** (Pengaturan → Berita lokal): hidup/mati, jam mulai, umur berita paling lama, jumlah berita yang diringkas AI per hari,
dan pakai AI atau tidak. Kata kunci pencarian dan umpan RSS tambahan diubah di `config/pengaturan.json` bagian `berita`.
Pemakaian kuota Tavily: satu pencarian per kata kunci per hari (bawaan 6 kata kunci, sekitar 180 kredit per bulan). Ditambah AI Data
Finder harian (sekitar 180), totalnya sekitar 360 dari 1.000 kredit gratis per bulan. Tanpa kunci Tavily, pencarian tetap jalan dari Google Berita, tetapi isi artikelnya lebih sering tidak terbaca.

**Yang belum terbukti.** Seluruh uji otomatis memakai berkas tiruan. Berapa banyak berita yang benar-benar terbaca dari Google Berita
dan portal Bengkulu baru diketahui setelah beberapa hari berjalan; lihat "Catatan proses terakhir" di halaman Berita Lokal.

## 6. Buletin, laporan, dan notifikasi

- Halaman **Laporan**: buletin mingguan, analisis bulanan, bahan rapat TPID triwulanan, evaluasi semesteran, dan laporan tahunan. Pilih periode lalu
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
- **Persetujuan model**: di halaman **Akurasi** centang model rekomendasi yang disetujui → isi nama penyetuju →
  *Unduh berkas persetujuan* → unggah ke `data/persetujuan_model/`. Untuk mewajibkan persetujuan, ubah
  `analisis.wajib_persetujuan_model` menjadi `true` di `config/pengaturan.json`.
- **Uptime**: workflow **Uptime** memeriksa dashboard setiap jam; log di cabang `log-uptime` (jangan dihapus).
- **Pengaduan & SKM**: tautan di kaki setiap halaman membuka formulir GitHub (butuh akun GitHub; bersifat publik).
  Untuk responden tanpa akun GitHub, isi `layanan.url_pengaduan_eksternal` (mis. tautan WhatsApp/PST) dan
  `layanan.url_survei_eksternal` (mis. Google Form) di `config/pengaturan.json`. Tanggapi pengaduan di kolom komentar
  issue lalu tutup issue bila selesai.

## 8. Admin

### Menyetujui akun (bila memakai Firebase)

1. Buka **Pengguna**. Akun Google yang baru mendaftar ada di tab **Menunggu persetujuan**. Beranda admin juga
   menampilkan pengingat bila ada yang menunggu.
2. Pilih **Peran**. Izin halaman bisa **Ikuti peran**, atau **Atur sendiri** untuk menambah atau mengurangi halaman
   tertentu.
3. Tekan **Setujui** atau **Tolak**. Orang yang disetujui langsung masuk ke berandanya.
4. Di tab **Aktif**, peran dan izin bisa diubah atau akun dinonaktifkan. Akun yang ditolak atau nonaktif bisa
   diaktifkan lagi atau dihapus.
5. Semua tindakan tercatat di **Jejak tindakan admin**. Admin tidak bisa mencabut hak adminnya sendiri.

### Panel Pengaturan (AI, kunci, dan fungsi)

Menu **Pengaturan** mengumpulkan semua yang perlu diatur. Langkahnya:

1. **Buat token GitHub** (sekali, lalu diganti berkala). Buka https://github.com/settings/personal-access-tokens/new, pilih *Only select repositories* lalu repositori ini, atur *Repository permissions*: **Contents**, **Secrets**, dan **Actions** = *Read and write*. Pilih masa berlaku pendek (misalnya 30 hari), klik *Generate token*, dan salin.
2. Buka **Pengaturan**, tempel token di kolom *Token GitHub*, lalu **Sambungkan**. Token hanya tersimpan di tab itu dan hilang saat tab ditutup.
3. **Isi kunci AI**: tab *AI*, isi *Kunci Gemini* (gratis dari https://aistudio.google.com/apikey) dan sebaiknya juga kunci gratis Groq, Cerebras, OpenRouter, atau Mistral sebagai cadangan (lihat bagian AI Data Finder), klik **Simpan kunci yang diisi**. Kunci dienkripsi di browser dan disimpan di GitHub Secrets. Setelah tersimpan, kolomnya kosong lagi dan statusnya "sudah diisi". Nilainya memang tidak bisa dilihat, hanya bisa diganti atau dihapus.
4. **Pilih AI dan modelnya** di tab yang sama, lalu klik **Simpan perubahan** di bilah bawah. Perubahan tercatat sebagai commit dan dashboard diperbarui otomatis 2 sampai 3 menit kemudian.
5. **Coba AI**: tab *Jalankan* → *Cari sumber data dengan AI* → isi komoditas dan periode → *Jalankan sekarang*. Statusnya tampil di sebelah tombol.
6. **Notifikasi**: tab *Notifikasi* untuk kunci Telegram (token bot dari @BotFather dan ID obrolan) dan email (server SMTP, pengguna, kata sandi aplikasi, penerima), serta kapan pesan dikirim.

Kalau muncul masalah:

| Pesan | Artinya | Yang dilakukan |
|---|---|---|
| Token ditolak | Salah salin, kedaluwarsa, atau dicabut | Buat token baru |
| Token belum punya izin ... | Izin token kurang | Tambahkan izin yang disebut, buat token baru |
| Tidak ditemukan | Nama repositori salah atau token belum diberi akses ke repositori ini | Periksa nama dan akses token |
| Berkasnya baru saja berubah / sudah diubah orang lain | Ada perubahan lain di GitHub | Klik *Muat ulang dari GitHub*, ulangi perubahan |
| Cabang ini dilindungi | `main` hanya menerima pull request | Izinkan akun admin mengubah langsung, atau ubah `config/pengaturan.json` lewat pull request |
| Tidak bisa menghubungi GitHub | Internet terputus, atau VPN dan pemblokir iklan menghalangi `api.github.com` | Matikan penghalang lalu coba lagi |

Yang tidak diatur lewat panel: jadwal otomatis, daftar kolom terlarang privasi, wilayah target, zona waktu, dan akun login.
Di repositori publik, panel hanya bisa mengubah sesuatu bila token valid, jadi jangan bagikan token dan cabut setelah selesai.

### Pengaturan lain lewat berkas

- **Menambah pasar**: tambahkan baris di `config/pasar.csv` (isi koordinat dari peta, `koordinat_terverifikasi=1`,
  `blank_spot=1` bila perlu).
- **Mengaktifkan item kajian Bapokting**: ubah `aktif` menjadi `1` di `config/komoditas.csv`.
- **Batas wilayah di peta**: letakkan berkas GeoJSON batas kecamatan/kabupaten (dari BPS) di `config/batas_wilayah.geojson`. Setelah pipeline berjalan, batasnya tampil di peta beranda.
- **Blank spot**: isi `blank_spot=1` pada `config/pasar.csv` untuk wilayah yang dimaksud. Jumlahnya tampil di kartu "Wilayah blank spot" beranda (target 8).
- **Mengubah ambang**: lewat panel **Pengaturan**, atau langsung di `config/pengaturan.json` (setiap perubahan tercatat di git). Nilai di luar rentang ditolak pipeline dengan pesan yang jelas.
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
| Halaman Berita Lokal kosong | Pencarian pertama belum jalan, atau dimatikan di Pengaturan → Berita lokal | Jalankan **Berita lokal** lewat Actions; cek Log proses AI |
| Banyak berita "hanya judul" | Situs melarang robot, berbayar, atau memakai JavaScript; tautan Google Berita tidak mengarah ke artikel | Isi kunci Tavily (isi artikel ikut terambil), atau tambahkan umpan RSS portal di `berita.umpan_rss` |

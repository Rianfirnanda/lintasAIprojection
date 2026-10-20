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

**Menu.** Bilah atas berisi paling banyak lima menu: **Beranda**, **Pantau** (Dashboard Internal, Harga, Peringatan, Berita Lokal),
**Data** (Catat Harga, Cek Data, Sumber, Kamus Data), **Laporan** (Laporan, Kebijakan, Capaian, Akurasi), dan **Kelola** (Pengaturan,
Pengguna). Isi tiap menu menyesuaikan peran; menu yang isinya satu halaman tampil langsung sebagai tautan. **Alur** dan **Tentang** ada di
menu akun (klik nama Anda). Di ponsel semua menu dibuka lewat tombol **Menu**.

**Tampilan.** Bawaannya mode gelap. Tombol bulan/matahari di kaki halaman mengganti ke mode terang, dan pilihan itu diingat di perangkat.

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

**Harga yang tidak diperbarui sumbernya (data beku).** Sumber resmi kadang terus melaporkan angka yang sama persis,
misalnya cabai merah besar di Pasar Panorama tercatat Rp35.000 setiap hari sejak September 2025, padahal harga cabai di
pasar dan sumber lain sudah bergeser lebih dari 70%. Mesin menandai angka seperti ini sebagai `data_beku` bila:
- angkanya sama persis selama sedikitnya 14 hari (cabai dan bawang) atau 30 hari (lainnya), dan
- median harga barang yang sama di pasar dan sumber lain (jendela 7 hari) sudah bergeser sedikitnya 20% (cabai dan bawang),
  12% (protein), atau 10% (beras, gula, minyak, dan barang pabrikan) dari awal masa itu.

Hanya angka sesudah pergeseran melewati ambang yang tidak dipakai; awal masa itu tetap dipakai karena saat itu harganya
masih sejalan. Angka beku tidak dipakai di perhitungan, peringatan, prakiraan, maupun pembanding harga berita, dan tidak
masuk antrean keputusan (jumlahnya bisa ratusan). Daftarnya ada di halaman **Cek Data**, bagian *Harga yang tidak
diperbarui sumbernya*. Deret yang masih beku sampai data terakhir memunculkan peringatan **Data tidak diperbarui**
(keparahan sedang untuk pasar Bengkulu Tengah, rendah untuk pasar pembanding). Tindak lanjutnya: minta petugas mencatat
harga langsung di pasar itu, atau laporkan ke pengelola sumber. Bila validator sudah mengecek ke pasar dan harganya memang
tetap, keputusan **Terima** pada angka itu dihormati. Pemeriksaan ini bisa dimatikan di Pengaturan → Data
(*Abaikan harga yang tidak diperbarui sumbernya*).

Dampaknya pada ketepatan prakiraan jujur dicatat: setelah angka beku dikeluarkan (17 Oktober 2026), kesalahan prakiraan
cabai naik (cabai rawit merah dari 10,7% menjadi 16,6%, cabai merah keriting dari 8,1% menjadi 11,3%), karena angka beku
sebelumnya membuat cabai tampak lebih mudah ditebak daripada kenyataannya. Bila angka beku berada di ujung data, deretnya
terputus dan evaluasi model untuk varian itu menunggu 14 hari data bersambung (keterangannya muncul di halaman Model).

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

## 4c. Harga harian Bengkulu Tengah: SP2KP Kemendag, dengan cadangan PIHPS Provinsi Bengkulu

Sistem selalu memakai data asli (`mode_demo: tidak` di `config/pengaturan.json`) dan wilayah sasarannya **Kabupaten Bengkulu Tengah**
(`wilayah_target: 1709`).

- **Sumber harian Bengkulu Tengah.** SP2KP (Sistem Pemantauan Pasar dan Kebutuhan Pokok, Kementerian Perdagangan) mencatat harga eceran
  harian di satu pasar acuan tiap kabupaten/kota: **Pasar Taba Penanjung** (Bengkulu Tengah, `PSR01`), **Pasar Kepahiang** (`PSR91`), dan
  **Pasar Panorama** (Kota Bengkulu, `PSR92`). Datanya terbuka tanpa login dan tersedia sejak **1 Februari 2024** (sebelum itu SP2KP belum
  memuat data pasar-pasar ini).
- **Alurnya.** `python -m pipeline ambil-sp2kp` mengambil harga harian (per 30 hari, dengan jeda) dan menyimpannya apa adanya di
  `data/mentah/sp2kp/harian_<tahun>.csv` (nama varian dan satuan asli SP2KP). `python -m pipeline sp2kp-ke-harga` lalu menyalin varian yang
  pemetaannya **disetujui** di `config/peta_varian_sp2kp.csv` menjadi `data/masuk/harga/sp2kp_<tahun>.csv`. Keduanya berjalan otomatis di
  pembaruan harian. Riwayat penuh bisa diambil ulang lewat alur kerja **Penjajakan sumber data** dengan pilihan `sp2kp`.
- **Tabel pemetaan varian.** Setiap varian SP2KP punya status `setuju` (dipakai), `tinjau` (belum dipakai, perlu keputusan), `tolak`, atau
  `baru` (varian yang baru muncul di SP2KP, otomatis ditambahkan dan tidak dipakai sampai ditinjau). Contoh keputusan: Beras Medium → BRS03,
  Beras Premium → BRS05, Daging Sapi Paha Belakang → DSP01, Minyakita **tidak** disamakan dengan Minyak Goreng Kemasan Bermerek II.
- **Cadangan per varian.** SP2KP tidak mencatat semua varian sistem (beras kualitas bawah I/II, medium II, super II, minyak goreng curah, dan
  kemasan bermerek II). Untuk varian itu saja, sistem memakai rata-rata Provinsi Bengkulu dari PIHPS Bank Indonesia (`wilayah_cadangan: 17`),
  dengan tanda "harga pengganti" di grafik, tabel model, dan kartu model. Deret dua wilayah **tidak** disambung.
- **Pembanding.** Kepahiang dan Kota Bengkulu memakai SP2KP (sumber yang sama dengan Bengkulu Tengah) sehingga ukuran perbandingan
  antarwilayah sebanding. PIHPS Provinsi dan PIHPS Kota Bengkulu tampil sebagai garis pembanding tambahan.
- **Kecocokan antar-sumber.** Untuk Kota Bengkulu, harga SP2KP Pasar Panorama dibandingkan dengan PIHPS Kota Bengkulu pada tanggal dan varian
  yang sama (skor konsensus, target ≥ 0,80). Ini ukuran keandalan SP2KP karena Bengkulu Tengah sendiri baru punya satu sumber harian.
- **Libur pencatatan.** Hari kerja ketika ketiga pasar SP2KP sama-sama tidak mencatat (libur nasional, cuti bersama) dikenali dari data dan
  tidak dihitung sebagai data hilang.
- **Isian hari kosong.** Hari kosong diisi harga terakhir paling banyak 3 hari pencatatan (sesuai rancangan; akhir pekan dan libur pencatatan
  tidak dihitung). Celah lebih panjang (mis. libur Lebaran 2022 dan 2024) dibiarkan kosong, dan model memakai data sesudahnya.
- **Syarat rentang 80%.** Dinilai tiap minggu selama setahun terakhir (52 titik uji, kalibrasi selalu dari masa sebelumnya). Penilaian 90 hari
  terakhir saja (13 titik yang saling tumpang tindih) tetap ditampilkan, tetapi terlalu sedikit untuk dijadikan syarat.
- **Kalibrasi rentang adaptif.** Selisih prakiraan dan kenyataan dari dua tahun uji mingguan diberi bobot menurut umur (separuh tiap 8 minggu,
  paling kecil 0,1), lalu lebar rentang dikoreksi tiap minggu memakai harga yang sudah terjadi (Adaptive Conformal Inference, sasaran 82%).
  Setelan ini dipilih dari uji Oktober 2024 sampai Oktober 2025 dan diperiksa pada Oktober 2025 sampai Oktober 2026: cakupan 21 dari 21 varian
  masuk 75 sampai 85% pada kedua tahun (cara lama 14 dari 21). Untuk harga yang jarang berubah, rentang bisa berupa satu angka; situs
  menulisnya "tetap Rp…" karena harga itu paling mungkin tidak berubah.
- **Target ketepatan prakiraan.** Halaman Akurasi dan Capaian memakai target laporan pengembangan model: rata-rata meleset (nilai tengah
  sMAPE semua varian) di bawah 5%, dan rentang 80% tepat (75 sampai 85%) di sedikitnya 85% varian. Keduanya bisa diubah di Pengaturan, tab
  Target dan layanan. Target lama dari rancangan ("10% lebih tepat dari harga terakhir") tetap dihitung sebagai keterangan pembanding di tabel
  per varian. Untuk harga yang jarang berubah, harga terakhir sudah tebakan terbaik, sehingga sebagian besar varian memakai cara itu; varian
  yang harganya sama sekali tidak berubah selama masa uji dicatat "tidak dapat dinilai" pada perbandingan itu.
- **Peringatan dini.** Ambang ditala per kelompok gejolak (rendah, sedang, tinggi) pada 70% masa awal riwayat, dinilai pada 30% masa akhir.
  Dasbor juga menampilkan seberapa dini peringatan muncul (sebelum, pada, atau sesudah hari pertama lonjakan).
- **Yang perlu dipahami.** Riwayat SP2KP baru sekitar 637 hari pencatatan; syarat status Valid adalah 730, jadi varian Bengkulu Tengah
  berstatus **Eksperimen** sampai sekitar awal 2027 meskipun angkanya sudah bisa dipakai sebagai bahan pertimbangan. Harga pasar acuan sering
  sama berhari-hari, sehingga cara paling sederhana (harga terakhir) sulit dikalahkan; mesin belajar hanya dipakai bila terbukti lebih tepat.
- **Data petugas BPS.** Bila petugas mencatat harga di Taba Penanjung atau Karang Tinggi (formulir Input Harga), datanya otomatis didahulukan
  (urutan prioritas di `config/sumber.csv`: BPS dan petugas di atas SP2KP).

## 4d. Proyeksi, status Valid/Eksperimen, dan Dasbor Analitik

**Dashboard Internal BPS** adalah beranda Administrator dan Analis (juga halaman `dasbor.html` di menu Analis, TPID, dan Admin). Tampilannya
ringan tanpa pita biru, memakai satu jenis huruf (Plus Jakarta Sans, disimpan di `site/vendor/font`): judul singkat, delapan indikator bergaris
ukur (sumber aktif, pemeriksaan, kecocokan sumber, umur data, kelengkapan, lolos uji, sinyal aktif, status audit), lalu baris pilihan:

- **Perkiraan untuk** 7, 14, atau 30 hari, **atau pilih tanggal** mana pun sampai 30 hari sesudah data terakhir. Angkanya diambil dari
  perkiraan harian (`jalur` per varian di `analitik.json`), bukan dihitung ulang di browser.
- **Menjelang hari raya**: tombol H-30, H-14, H-7, H-3, dan Hari H untuk hari raya terdekat (`hari_raya_mendatang`). Tanggal yang masih di
  luar jangkauan 30 hari tidak bisa ditekan, dan keterangannya menyebut mulai kapan bisa dipilih (mis. H-30 Natal 2026 mulai 26 Oktober).

Di bawahnya ada ringkasan arah perkiraan untuk tanggal terpilih (berapa komoditas naik, stabil, turun; klik untuk menyaring tabel), tabel
proyeksi 21 varian yang **dipendekkan dan bergulir pelan ke bawah dengan sendirinya** (berhenti saat kursor, sentuhan, atau fokus papan
ketik ada di tabel; tombol Jeda untuk mematikan; tidak bergerak bila perangkat diatur untuk mengurangi gerak), grafik tren, perbandingan dan
selisih antarwilayah, ciri pergerakan harga, ketepatan perkiraan, faktor pendorong, asal data, dan rekomendasi. "Analisis lanjutan" dan
"Mutu data dan peringatan dini" berupa tab supaya halaman tidak terlalu panjang; tab menampilkan angka ringkas (mis. 5/10 pencari data,
F1 89%). Indikator yang belum bisa dihitung tetap jujur: keyakinan berupa persen syarat uji yang lolos, dan faktor pendorong bukan SHAP.
Tabel bisa diurutkan dan diekspor ke CSV, termasuk kolom tanggal pilihan. Angkanya dibaca dari
`analitik.json`, `proyeksi_acara.json`, dan `proyeksi_periodik.json` yang dibuat tiap pipeline jalan.

- **Proyeksi harian.** 7, 14, dan 30 hari ke depan dengan rentang 80%. Rentang dibentuk dari selisih prakiraan dan kenyataan pada uji data
  lama (konformal adaptif, lihat bagian 4c), bukan dari rumus tebakan.
- **Uji akhir (holdout).** 90 hari terakhir disisihkan dan tidak dipakai memilih cara prakiraan. Hasilnya dinilai dengan sMAPE, MASE, bias,
  akurasi arah, dan cakupan rentang 80%. MASE memakai skala galat cara naif pada horizon yang sama, dihitung dari data sebelum masa uji.
- **Status.** **Valid** hanya bila semua syarat Protokol Validasi lolos: riwayat minimal 730 hari, kelengkapan minimal 95%, sMAPE di bawah
  batas kelompok (pokok dan pabrikan 5%, protein 10%, volatil 15%), bias paling banyak 3% (kelas rendah) atau 5%, MASE di bawah 1, cakupan 75
  sampai 85%, dan khusus komoditas volatil akurasi arah minimal 60%. Selain itu **Eksperimen**: tetap tampil, berlabel eksperimen, dan bukan
  angka resmi. Syarat yang gagal tertera di panel "Kinerja model pada data uji akhir".
- **Tingkat keyakinan.** Tinggi bila semua syarat lolos, Sedang bila hanya satu syarat gagal, Rendah bila lebih. Ini aturan, bukan angka karangan.
- **Uji Diebold-Mariano.** Mesin belajar atau gabungan yang terbukti lebih buruk dari cara naif pada masa uji akhir dikembalikan ke juara
  cara sederhana.
- **Hari raya.** Menuju Hari H dari H-30, H-14, H-7, dan H-3, sesudahnya H+3, H+7, H+14, untuk Idul Fitri, Idul Adha, dan Natal. Cara:
  harga titik asal dikalikan median perubahan pada hari raya sejenis sebelumnya, diuji dengan menyisihkan satu hari raya bergiliran (butuh
  minimal 3). Proyeksi aktif baru muncul setelah titik asalnya tiba (mis. Natal 2026 mulai 25 November dari H-30), dihitung dari harga pada
  hari itu. Tab "Hari raya" menampilkan garis waktu titik-titik ini. Selama hari raya
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

   **Jatah kuota Tavily otomatis.** Sebelum mencari, mesin membaca sisa kredit bulan ini langsung dari Tavily
   (`https://api.tavily.com/usage`), jadi pemakaian dari mana pun ikut terhitung (AI harian, berita lokal, tombol di
   Pengaturan, dan AI yang berjalan di browser admin). 10% kuota disisihkan sebagai cadangan; sisanya dibagi rata ke hari
   yang tersisa dalam bulan itu menjadi jatah harian, yang dipakai bersama semua proses hari itu (angka awal hari disimpan
   di Firestore `lbp_status/kuota_tavily`). AI harian menyisakan jatah untuk berita lokal bila berita hari itu belum
   dicari. Permintaan yang ditekan admin boleh melewati jatah harian, tetapi tidak menyentuh cadangan. Bila jatah habis,
   pencarian dilewati dengan alasan yang jelas, AI tetap menjawab tanpa pencarian web, dan berita lokal tetap dicari lewat
   Google Berita. Sisa kuota dan jatah hari ini tampil di Pengaturan → AI (*Pencarian web (Tavily)*). Contoh: dengan AI
   harian 10 komoditas (30 kredit) dan berita (6 kredit), kebutuhan sekitar 1.080 kredit per bulan melebihi 1.000, jadi
   menjelang akhir bulan sebagian komoditas dicari tanpa pencarian web, alih-alih semua pencarian berhenti total.
4. **Actions → AI Data Finder → Run workflow** (atau Pengaturan → Jalankan → *Cari sumber data dengan AI*), isi
   komoditas, periode, jenis data, wilayah, dan penyedia. `otomatis` mencoba AI sesuai *Urutan kalau memilih Otomatis*,
   lalu AI gratis lain yang belum disebut. AI yang kuncinya belum diisi, kena batas pemakaian, atau jawabannya rusak
   dilewati, dan alasannya dicatat di hasil ("dilewati: ...").
5. Hasil tersimpan di `data/sumber/kandidat_ai.json` dan tampil di halaman **Sumber Data** sebagai kartu:
   - Kandidat yang sama dari banyak pencarian (alamat sama, tanpa `www` dan garis miring akhir) **digabung** menjadi satu kartu, lengkap
     dengan berapa kali muncul, untuk komoditas apa, dan kapan terakhir ditemukan.
   - **Skor kelayakan 0 sampai 100** dihitung dari hal yang bisa dicek, bukan pendapat AI: situs resmi (25), alamat muncul di hasil
     pencarian web (15), alamat bisa dibuka (15; setengah bila situs menolak robot), wilayah Bengkulu Tengah (20; pembanding/provinsi 12,
     nasional 6), diperbarui harian (15; mingguan 8, bulanan 4), dan bisa diambil otomatis (10; berkas 7, halaman web 4). Skor 70 ke atas
     berarti layak dicek, 45 sampai 69 sedang.
   - Kartu bisa disaring (belum dinilai, layak dicek, diterima, ditolak, sudah dipakai), dicari, dan diurutkan. Rincian per pencarian ada di
     *Riwayat pencarian*.
   - Hasil tanpa Tavily (dan selain Claude) ditandai **tanpa pencarian web**: semua URL wajib dicek manual.
   - Setiap pencarian memberi AI daftar sumber yang sudah tercatat (paling banyak 40 alamat) supaya yang dicari sumber baru. Kandidat yang
     alamatnya sudah tercatat ditandai `sudah_dikenal`, dan log mencatat berapa kandidat yang benar-benar baru.
6. Verifikasi kandidat (izin, lisensi, cakupan, keandalan). Bila layak, tambahkan ke `config/sumber.csv`.
   Kandidat tidak pernah otomatis menjadi sumber data.

## 5b. Berita lokal harian

Mesin mencari berita lokal tentang harga pangan, membaca isinya, mengambil harga yang disebut, **langsung menilai setiap harga**, lalu
menyusun kesimpulan harian. Hasilnya tampil di halaman **Berita Lokal** (menu Pantau untuk analis, TPID, operator, dan admin).

**Jadwal.** Berjalan sendiri sekali sehari. Penjaga (`antrean.yml`) melihat bahwa jam 07.00 WIB sudah lewat dan berita hari
ini belum dicari, lalu memicu pembaruan harian yang memuat langkah ini. Jam mulainya bisa diubah di **Pengaturan → Berita lokal**.
Mau hasilnya sekarang: **Actions → Berita lokal → Run workflow** (atau, tanpa GitHub, Pengaturan → Jalankan → *Cari berita lokal sekarang*; permintaan dari panel tetap berjalan walau hari ini sudah dicari).
Prosesnya tercatat di **Log proses AI** (halaman Sumber Data) dengan keterangan "Berita lokal harian".

**Yang dikerjakan setiap hari:**

1. **Mencari.** Pencarian berita Tavily (hasilnya sudah memuat isi artikel), umpan RSS Google Berita untuk tiap kata kunci,
   dan umpan RSS portal berita yang diisi admin (`berita.umpan_rss` di `config/pengaturan.json`). Kata kunci tambahan
   (`berita.kueri_tambahan`: LPG, susu kental manis, garam, nama pasar Taba Penanjung dan Karang Tinggi, serta pencarian per portal Bengkulu)
   hanya dicari lewat Google Berita supaya kredit Tavily tidak terpakai.
2. **Menyaring.** Duplikat dibuang (tautan yang sama, atau judul yang sama dari portal lain), begitu pula berita lebih lama
   dari `umur_maks_hari` dan yang berasal dari media sosial atau video. Berita yang tidak menyebut wilayah Bengkulu
   beserta topik pangan dibuang.
3. **Membaca.** Halaman artikel diunduh hanya bila `robots.txt` situsnya mengizinkan, dengan jeda antar permintaan, batas ukuran,
   dan nama bot yang jelas (`LintasBentengBot`). Halaman yang melarang, berbayar, atau memakai JavaScript hanya tampil dengan judulnya.
4. **Mengambil harga.** Dengan aturan baku (bukan AI): kalimat yang memuat komoditas, angka rupiah, dan satuan kg atau liter.
   Selisih kenaikan ("naik Rp 5.000"), harga per butir atau ikat, dan angka di luar batas wajar komoditas tidak dihitung
   sebagai harga. Setiap kandidat membawa kalimat buktinya, wilayah yang disebut (Bengkulu Tengah, pembanding, provinsi,
   nasional, atau tidak jelas), nama pasar bila disebut (mis. Pasar Taba Penanjung), dan arah perubahan (naik atau turun) bila
   kalimatnya tegas. Selain 21 varian, dibaca juga gas LPG 3 kg (per tabung), susu kental manis (per kaleng), garam (per bungkus),
   dan telur ayam ras per karpet; keempatnya hanya penunjuk dan tidak dibandingkan dengan data utama.
5. **AI menilai setiap harga.** AI gratis (rotasi yang sama dengan AI Data Finder) membaca judul, wilayah, dan kalimat bukti tiap harga,
   lalu menentukan: harga pasar saat berita ditulis, harga program pemerintah (pasar murah, operasi pasar, SPHP, bazar), harga rata-rata
   lembaga, harga lama ("dari semula", "sebelumnya"), atau bukan harga barang; apakah angkanya memang untuk barang yang dibaca mesin; dan
   wilayahnya. AI **tidak bisa menulis atau mengubah angka**. Nama barang hanya dikoreksi bila nama barang yang baru tertulis di kalimat
   buktinya (mis. "cabai rawit dan cabai setan Rp80.000" yang terbaca mesin sebagai cabai merah). Alasan AI yang memuat angka yang tidak
   ada di kalimat dibuang. Paling banyak `maks_nilai_harga` harga per hari (bawaan 60, berita terbaru dulu); harga di arsip yang belum
   sempat dinilai diperiksa pada hari berikutnya. Bila AI tidak tersedia, aturan cadangan tetap mengenali harga lama dari kata
   "sebelumnya", "semula", atau "pekan lalu" di depan angkanya.
6. **Membandingkan dengan harga resmi.** Setiap kali situs diterbitkan, tiap harga dibandingkan dengan harga resmi **pada tanggal
   beritanya** (nilai terakhir paling lama 7 hari sebelumnya, atau paling dekat sesudahnya). Wilayahnya disamakan bila datanya ada:
   berita Kota Bengkulu dibandingkan dengan deret Kota Bengkulu, berita tingkat provinsi dengan rata-rata provinsi; selain itu dengan
   harga Bengkulu Tengah. Bila berita tidak menyebut jenis barangnya (mis. "cabai merah" saja), dipakai rentang harga semua jenisnya.
   Putusannya: **sesuai** (selisih sampai 5%), **sedikit lebih mahal/murah** (5 sampai 15%), **jauh lebih mahal/murah, perlu dicek**
   (lebih dari 15%), **harga program pemerintah** dan **harga di luar Bengkulu** (tidak dibandingkan), **belum ada harga resmi pembanding**
   (mis. LPG per tabung, telur per karpet), atau **tidak dipakai** (harga lama, barang lain, bukan harga, di luar batas wajar).
7. **Skor keyakinan 0 sampai 100.** Diperiksa AI 30 (belum diperiksa 10), wilayah 30 (Bengkulu Tengah 30, wilayah tetangga 20, provinsi 15,
   tidak jelas 5, nasional atau luar provinsi 0), kebaruan berita 20 (sampai 3 hari 20, sampai 7 hari 14, sampai 14 hari 6), harga jual
   di pasar 10 (rata-rata atau belum jelas 5), dan didukung berita lain dengan harga serupa (selisih sampai 10%, tautan dan kalimat
   berbeda) 10. Tinggi mulai 70, sedang 45 sampai 69. Skor ini menilai seberapa layak angkanya dipercaya, bukan cocok tidaknya dengan
   harga resmi, supaya harga di lapangan yang benar-benar melonjak tetap terlihat.
8. **Menyimpulkan per komoditas.** Harga yang dipakai dikelompokkan per komoditas: median, rentang, wilayah yang paling dekat dengan
   Bengkulu Tengah (harga pasar didahulukan dari harga program), median selisih terhadap harga resmi, putusan, dan keyakinan tertinggi.
   Hasilnya tampil di halaman **Berita Lokal** (bagian *Penilaian harga dari berita*, dengan rincian per harga di bawah tiap berita) dan
   di tab **Harga dari berita** pada Dashboard Internal (`ringkasan_harga` dan `penilaian` di `berita.json`).
9. **Meringkas dan menyimpulkan.** AI meringkas berita yang paling relevan dan menyusun kesimpulan harian. AI hanya boleh memakai fakta
   dari teks berita, dan kalimat yang memuat angka yang tidak ada di berita dibuang otomatis. Bila semua AI sedang tidak bisa dipakai,
   ringkasan dan kesimpulan disusun otomatis dari kalimat berita dan ditandai "ringkasan otomatis".

**Aturan yang tidak boleh dilanggar:**

- Harga dari berita **tidak pernah** masuk deret harga resmi atau perhitungan prakiraan, walaupun penilaiannya "sesuai" dan
  keyakinannya tinggi. Penilaian otomatis adalah penunjuk awal: harga yang "jauh lebih mahal, perlu dicek" dengan keyakinan tinggi
  di Bengkulu Tengah adalah alasan untuk menugaskan petugas mengecek pasar, bukan pengganti data resmi. Bila hasil cek lapangan
  layak dipakai, catat sebagai data biasa lewat jalur harga yang sudah ada.
- Isi lengkap artikel **tidak disimpan** (hak cipta penerbit). Yang disimpan: tautan, judul, ringkasan, kutipan pendek, kalimat bukti,
  dan sidik SHA-256 isi artikel pada saat dibaca (`data/berita/berita.json`).
- Berita sering menyebut harga di wilayah lain atau rata-rata nasional. Kolom "Berlaku untuk" di halaman menunjukkan wilayahnya.

**Pengaturan** (Pengaturan → Berita lokal): hidup/mati, jam mulai, umur berita paling lama, jumlah berita yang diringkas AI per hari,
jumlah harga yang dinilai AI per hari, dan pakai AI atau tidak. Kata kunci pencarian dan umpan RSS tambahan diubah di `config/pengaturan.json` bagian `berita`.
Pemakaian kuota Tavily: satu pencarian per kata kunci per hari (bawaan 6 kata kunci, sekitar 180 kredit per bulan). Ditambah AI Data
Finder harian (sekitar 180), totalnya sekitar 360 dari 1.000 kredit gratis per bulan. Tanpa kunci Tavily, pencarian tetap jalan dari Google Berita, tetapi isi artikelnya lebih sering tidak terbaca.

**Yang belum terbukti.** Seluruh uji otomatis memakai berkas tiruan. Berapa banyak berita yang benar-benar terbaca dari Google Berita
dan portal Bengkulu baru diketahui setelah beberapa hari berjalan; lihat "Catatan proses terakhir" di halaman Berita Lokal.

## 6. Buletin, laporan, dan notifikasi

- Halaman **Laporan**: buletin mingguan, analisis bulanan, bahan rapat TPID triwulanan, evaluasi semesteran, dan laporan tahunan. Pilih periode lalu
  **Cetak / Simpan PDF**. Rekomendasi di dalamnya disusun otomatis dan wajib ditelaah analis.
- **Notifikasi Telegram** (gratis): buat bot lewat @BotFather → salin token → buka bot di Telegram dan tekan **Start**
  (untuk pesan pribadi), atau tambahkan bot ke grup TPID lalu kirim satu pesan di grup itu. Isi token di Pengaturan →
  Notifikasi, lalu buka Pengaturan → Jalankan → **Kirim pesan uji Telegram dan email**. Bila ID obrolan belum diisi atau
  salah, hasil uji menampilkan alasan dari Telegram (mis. "chat not found") dan daftar obrolan yang pernah menghubungi
  bot; tekan **Pakai ID ini dan kirim uji lagi** pada obrolan yang benar. ID pribadi berupa angka; ID grup berawalan
  minus. Nama `@pengguna` orang tidak bisa dipakai sebagai tujuan (hanya kanal publik yang boleh memakai `@nama`).
  Tanpa situs berlogin, isi secret `TELEGRAM_BOT_TOKEN` dan `TELEGRAM_CHAT_ID` lalu jalankan **Actions → Uji notifikasi**.
- **Notifikasi email** (gratis, mis. Gmail): aktifkan verifikasi 2 langkah → buat *App Password* → secret
  `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=465`, `SMTP_USER`, `SMTP_PASSWORD` (App Password), `EMAIL_KE`.
- Yang dikirim: peringatan aktif (tingkat paling rendahnya diatur di Pengaturan → Notifikasi) yang belum pernah dikirim,
  dan buletin mingguan setelah minggu berakhir. Catatan kiriman di `data/notifikasi/terkirim.json`. Mode demo tidak
  mengirim notifikasi.
- **Bentuk pesan**: judul dan tanggal, lalu peringatan dikelompokkan menurut seberapa penting (*Perlu segera dicek*,
  *Perlu dipantau*, *Untuk diketahui*). Tiap harga ditulis dengan angka rupiah, misalnya "Sekarang Rp13.400/kg, biasanya
  Rp12.650/kg". Catatan kelengkapan data (pasar belum mengirim, angka tidak diperbarui) ada di bagian sendiri di bawah.
  Pesan yang hanya berisi catatan data dikirim tanpa bunyi supaya grup tidak terganggu. Tautan di pesan mengarah ke
  situs utama (Firebase Hosting).
- **Kapan dikirim (lebih cepat)**: jadwal bawaan GitHub sering terlambat sampai berjam-jam, jadi pemeriksaan rutin kini
  dijalankan oleh penjaga antrean yang selalu menyala, tepat pada jam di Pengaturan → Notifikasi → **Jam pemeriksaan
  rutin** (bawaan 07.30, 11.45, 15.45 WIB pada hari pencatatan). Harga yang dikirim petugas dari situs tetap diproses saat
  itu juga. Satu putaran pemeriksaan sampai pesan terkirim biasanya 8 sampai 10 menit.

## 6b. Fitur bantu untuk semua pengguna

- **Tanya Takar** (tombol "Tanya" di pojok kanan bawah). Menjawab pertanyaan dengan kalimat biasa dari data situs:
  harga barang, barang yang naik atau turun paling banyak, perkiraan 7, 14, atau 30 hari, peringatan aktif, hari raya
  berikutnya, dan kapan data diperbarui. Jawaban ini tidak memakai AI dan tidak memakai kunci, jadi bisa dipakai semua peran.
  Pertanyaan bebas yang tidak ada di data (mis. "kenapa harga naik?") diteruskan ke AI untuk **semua pengguna yang sudah
  masuk**, lewat fitur AI bawaan Firebase (AI Logic). Kunci Gemini-nya disimpan Firebase dan tidak pernah dikirim ke
  browser, jadi tidak ada kunci yang bisa disalin pengguna. AI hanya diberi data situs sebagai bahan jawaban dan dibatasi
  30 pertanyaan per hari per perangkat. Selama AI Logic belum dinyalakan, AI tetap jalan untuk Administrator memakai kunci
  AI situs, dan peran lain dijawab dari data saja.
- **Pencarian cepat** (tombol Cari di bilah atas, atau tekan Ctrl+K atau /). Ketik nama barang, peringatan, atau halaman;
  barang langsung membuka grafiknya di halaman Harga.
- **Mode Videotron** (tombol "Mode Videotron" di Dasbor TPID, atau lewat pencarian cepat; untuk peran TPID, Analis, dan
  Administrator). Layar penuh bergaya dashboard untuk rapat, TV, atau videotron, tanpa tombol di layar. Tampilan berganti
  otomatis: ringkasan hari ini, harga semua bahan pokok (dibagi beberapa layar sesuai ukuran layar), pergerakan sebulan,
  tren 30 hari, harga yang perlu diwaspadai, perkiraan 7 hari, dan menjelang hari raya. Di bawah layar ada teks berjalan
  berisi semua harga, dan di atas ada jam serta tanggal data. Ukuran huruf menyesuaikan layar (proyektor, TV 4K, layar
  tegak, sampai ponsel). Data baru masuk sendiri tanpa memuat ulang halaman, jadi layar penuh tidak terputus.
  Kendali untuk operator: **Esc** atau ketuk dua kali untuk keluar, panah kiri/kanan untuk pindah, spasi untuk jeda,
  **F** untuk layar penuh lagi.
  **Untuk videotron yang menyala terus**: masuk dengan akun TPID di komputer videotron, buka alamat situs ditambah
  `index.html#videotron`, lalu jalankan peramban dalam mode kios (mis. Chrome dengan `--kiosk`). Bila halaman dimuat
  ulang, mode videotron terbuka lagi sendiri.
- **Grafik**: tombol + dan − di pojok grafik untuk memperbesar, lalu seret ke kiri atau kanan; ketuk dua kali untuk kembali
  ke semua tanggal. Halaman Harga punya grafik **Bandingkan harga** untuk sampai 4 barang sekaligus.
- **Pasang aplikasi**: bila peramban mengizinkan, tombol "Pasang aplikasi" muncul di kaki halaman supaya situs bisa dibuka
  dari layar utama ponsel seperti aplikasi.
- Animasi otomatis mati bila pengaturan perangkat meminta gerak dikurangi.

### Menyalakan AI untuk semua pengguna (sekali saja)

1. Buka [Firebase Console](https://console.firebase.google.com) → pilih proyek situs ini → menu **AI Logic** (alamat
   langsungnya `console.firebase.google.com/project/ID-PROYEK/genai`) → **Get started**.
2. Pilih **Gemini Developer API**. Paket gratis (Spark) cukup; Firebase membuat kunci Gemini sendiri dan menyimpannya di
   server. Jangan menempelkan kunci Gemini situs ke mana pun di langkah ini.
3. Tunggu beberapa menit, lalu coba Tanya Takar dengan pertanyaan bebas memakai akun yang bukan Administrator. Jawaban AI
   ditandai "Jawaban AI dari data situs".

**Pengaman yang disarankan: App Check.** Konfigurasi web Firebase memang terbuka untuk umum, jadi tanpa App Check orang
lain bisa memakai jatah AI proyek dari skrip mereka sendiri. Dengan App Check, Firebase hanya melayani permintaan dari situs
ini. Bila proyek masih paket gratis (Spark), pemakaian liar paling buruk menghabiskan kuota gratis sehingga AI berhenti
sampai kuota pulih. Bila proyek sudah paket berbayar (Blaze), pemakaian liar bisa menimbulkan tagihan, jadi App Check wajib
dipasang:

1. Buat kunci **reCAPTCHA v3** di [Google reCAPTCHA Admin](https://www.google.com/recaptcha/admin): tipe reCAPTCHA v3,
   domain diisi alamat situs (mis. `lintas-benteng-proyeksi.web.app`). Simpan **kunci situs** dan **kunci rahasia**.
2. Firebase Console → **App Check** → tab **Apps** → aplikasi web situs → **reCAPTCHA** → tempel **kunci rahasia** → Simpan.
3. Buka **Pengaturan** di situs → tab **Firebase** → isian Konfigurasi web Firebase (`FIREBASE_WEB_CONFIG`). Tambahkan baris
   `recaptchaSiteKey: "kunci-situs-dari-langkah-1"` di dalam `firebaseConfig`, lalu simpan. Kunci situs memang boleh
   terlihat publik. Tunggu situs terbit ulang.
4. Setelah beberapa jam, buka App Check → tab **APIs** → **Firebase AI Logic**. Bila hampir semua permintaan sudah
   "Verified", tekan **Enforce**. Sejak itu permintaan AI dari luar situs ditolak.

Batas pemakaian per pengguna juga bisa diatur di Firebase Console → AI Logic → **Settings** (permintaan per menit per
pengguna). Di halaman Pengaturan situs, AI Logic sengaja tidak dipakai karena aturan keamanan halaman itu lebih ketat;
di sana Tanya Takar memakai kunci AI situs milik Administrator.

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

### Pendaftaran otomatis untuk masyarakat (bila memakai Firebase)

Saat situs disebar ke publik, menyetujui warga satu per satu akan lambat. Di halaman **Pengguna** ada saklar **Setujui
otomatis pendaftar baru sebagai Masyarakat** (hanya peran Administrator yang bisa mengubahnya). Bila dinyalakan, siapa pun
yang masuk dengan akun Google (yang emailnya sudah terverifikasi) langsung aktif sebagai **Masyarakat**: bisa melihat
harga, laporan, dan kamus, tetapi tidak bisa membuka halaman lain. Peran lain (petugas, TPID, analis, admin) tetap hanya
diberikan Administrator. Pendaftar yang masih menunggu ikut aktif sebagai Masyarakat saat masuk berikutnya. Aturan
Firestore yang menjaga semua ini, jadi tidak bisa diakali dari peramban. Saklar ini tercatat di jejak tindakan admin.

### Pengguna aktif, lokasi, dan log aktivitas (bila memakai Firebase)

Di Beranda Administrator, tab **Ringkasan Administrator**, ada panel **Pengguna aktif dan lokasi** yang diperbarui langsung:

- **Angka ringkas**: berapa orang aktif sekarang (dipakai dalam 10 menit terakhir), diam (aplikasi terbuka tetapi tidak
  dipakai, sampai 30 menit), tidak aktif (keluar atau lama tidak membuka), dan berapa yang membagikan lokasi.
- **Peta**: titik tiap orang yang membagikan lokasi. Hijau berdenyut = aktif, oranye = diam, abu = tidak aktif (lokasi
  terakhir). Huruf di titik adalah huruf awal peran. Ketuk titik untuk nama, halaman yang sedang dibuka, dan waktu lokasi.
- **Daftar**: nama, peran, status, halaman yang sedang dibuka, lokasi, jenis perangkat, dan kapan terakhir aktif.
  Ketuk koordinat untuk melompat ke titiknya di peta.
- **Log aktivitas**: siapa masuk, membuka halaman apa, keluar, dan mulai atau berhenti berbagi lokasi, beserta waktu dan
  lokasinya. Bisa disaring per peran dan diunduh sebagai CSV.

**Lokasi selalu atas izin pengguna.** Saat pertama memakai aplikasi, setiap pengguna ditanya "Bagikan lokasi Anda dengan
Administrator?" dan bisa menjawab *Jangan*. Pilihan bisa diubah kapan saja lewat menu akun (pojok kanan atas). Browser
juga meminta izin sendiri. Lokasi **petugas lapangan** dikirim tepat (untuk memantau kunjungan pasar); lokasi **peran lain**
dibulatkan sekitar 1 km supaya rumah orang tidak bisa ditunjuk. Lokasi hanya diambil saat aplikasi sedang dibuka, paling
sering tiap 10 menit, bukan terus-menerus di latar belakang. Ini sejalan dengan UU Pelindungan Data Pribadi (UU 27/2022):
ada persetujuan, tujuan jelas, dan data tidak disimpan selamanya.

Yang bisa melihat panel ini hanya pengelola akun (peran Administrator, atau orang yang diberi halaman Pengguna). Catatan
tidak bisa diubah atau dihapus dari situs. Menghapus akun di halaman Pengguna ikut menghapus lokasi terakhirnya.

**Hapus otomatis catatan lama (sekali saja, disarankan):** setiap catatan log membawa tanggal hapus 90 hari ke depan.
Supaya benar-benar terhapus, buka Firebase Console → **Firestore Database** → **TTL** (Time-to-live) → **Create policy**,
isi *Collection group* `lbp_aktivitas` dan *Timestamp field* `hapus_pada`, lalu simpan. Fitur ini gratis.

Bila aturan Firestore digabung sendiri (`FIREBASE_TERBITKAN_ATURAN` = `tidak`), salin juga blok
`match /lbp_kehadiran/...`, `match /lbp_aktivitas/...`, dan fungsi `lokasiSah` dari `firestore.rules`.

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
| Notifikasi tidak terkirim | Kunci belum diisi, mode demo, atau Telegram menolak (mis. "chat not found": bot belum di-Start atau ID obrolan salah) | Pengaturan → Jalankan → **Kirim pesan uji Telegram dan email**; alasan dan daftar obrolan yang benar tampil di sana |
| Peringatan "Data tidak diperbarui" | Sumber resmi melaporkan angka yang sama terus padahal harga di tempat lain bergeser | Minta petugas mencatat langsung di pasar itu; lihat Cek Data → *Harga yang tidak diperbarui sumbernya* |
| AI mencari "tanpa pencarian web" | Jatah kuota Tavily hari ini habis (kuota bulanan dijaga) | Lihat sisa kuota di Pengaturan → AI; kurangi *AI harian* atau tunggu hari berikutnya |
| Issue tidak dibuat | Mode demo, keparahan < tinggi, atau `github_issues=false` | Periksa `pengaturan.json` dan pesan sinkronisasi di halaman Sinyal |
| Workflow deploy gagal "Pages not enabled" | Pages belum diaktifkan | Settings → Pages → Source: GitHub Actions |
| Cuaca tidak bertambah | API Open-Meteo tidak terjangkau | Langkah konektor bersifat `continue-on-error`; cek log Actions |
| Halaman Berita Lokal kosong | Pencarian pertama belum jalan, atau dimatikan di Pengaturan → Berita lokal | Jalankan **Berita lokal** lewat Actions; cek Log proses AI |
| Banyak berita "hanya judul" | Situs melarang robot, berbayar, atau memakai JavaScript; tautan Google Berita tidak mengarah ke artikel | Isi kunci Tavily (isi artikel ikut terambil), atau tambahkan umpan RSS portal di `berita.umpan_rss` |

# Adopsi fitur model bertahap

Fondasi tetap pipeline GitHub. Arsip unggahan tidak menggantikan direktori pipeline, modul lama, ataupun skema keluaran situs. Kebijakan yang dapat ditinjau berada di `config/kebijakan_model.json`.

## 1. Sumber training eksplisit

Training produksi memakai satu sumber utuh per varian/wilayah, bukan campuran sumber pada tanggal yang berbeda:

1. Cari SP2KP yang lolos quality gate di wilayah target.
2. Jika tidak layak, cari PIHPS di wilayah tersebut.
3. Jika belum ada, ulangi pada wilayah cadangan yang dikonfigurasi, dengan label wilayah cadangan.

Bawaan kelayakan: minimal 60 tanggal observasi dan umur data terakhir maksimal tujuh hari kalender pada tanggal penilaian. Data sesudah tanggal penilaian tidak boleh ikut pemilihan. Data berstatus beku, ditolak, atau menunggu validasi tidak masuk training.

BPS-HRG, PSR-ENUM, AI, dan sumber lain tetap dibaca untuk pemeriksaan, rekonsiliasi, laporan, dan tampilan. Nilainya tidak ditambahkan untuk mengisi hari yang hilang pada sumber resmi training. Jika tidak ada sumber resmi layak, data lapangan masih ditampilkan tetapi proyeksi model resmi ditahan. Mode demo tetap dapat memakai data sintetis dengan penanda demo dan tidak memperoleh izin proyeksi resmi.

Angka prioritas umum pada sumber.csv tidak diubah. Filter training ini eksplisit sehingga data lapangan tidak dapat masuk hanya karena memiliki prioritas tinggi atau karena SP2KP kosong pada suatu hari. Keputusan sumber dan alasan cadangan dicatat per varian.

## 2. Fitur bertahap dan kausal

Tiga kandidat Ridge memakai kelompok fitur yang semakin lengkap:

- `musiman_kalender`: harmonik tahunan, momentum harga, return tahun sebelumnya, serta fase per jenis Idul Fitri, Idul Adha, Natal, awal Ramadan, dan Tahun Baru Masehi. Pendekatan H-35 sampai H-1 dipisahkan dari profil Gaussian sekitar acara; tanggal peristiwa mengikuti kalender masing-masing tahun.
- `musiman_cuaca`: kalender ditambah hujan/suhu 7 dan 30 hari, kelengkapan observasi, dan anomali terhadap rata-rata bulan yang hanya dihitung dari riwayat yang sudah tersedia.
- `musiman_regional`: kalender/cuaca ditambah return dan deviasi spread wilayah pembanding. Kode 1708 adalah Kepahiang, 1771 Kota Bengkulu, dan 17 Provinsi Bengkulu.

Cuaca dan harga regional memakai informasi sampai H-1. Tidak ada pengisian awal dengan observasi yang baru datang di masa depan. Fitur regional boleh meneruskan observasi paling lama tiga hari; celah lebih panjang ditandai tidak tersedia. Nilai proksi regional tidak menjadi target harga lokal dan tidak menambah jumlah observasi asli lokal.

Harga target training tetap harus teramati. Pengisian celah yang sudah ada hanya membantu fitur dan harga awal; target sintetis hasil pengisian tidak dihitung sebagai pasangan training Ridge kontekstual.

Prakiraan BMKG masa depan belum dimasukkan. Pemakaiannya memerlukan arsip dengan waktu penerbitan, waktu berlaku, dan wilayah, agar informasi pada origin historis dapat direkonstruksi. CSV historis dapat memuat revisi penerbit; pengujian saat ini mengasumsikan tanggal observasi sebagai batas ketersediaan dan tidak mengklaim mempunyai arsip vintage lengkap SP2KP/PIHPS.

Quality gate dan kelayakan sumber dinilai dari snapshot pada tanggal evaluasi. Keputusan kualitas serta pilihan sumber belum direkonstruksi dari arsip keputusan pada setiap origin historis. Backtest model memakai fitur dan target berurutan secara kausal pada snapshot tersebut; hasilnya belum merupakan simulasi vintage seluruh proses pengumpulan dan validasi data.

RF/Boosting/Ridge yang sudah ada tetap menjadi penantang dengan fitur lamanya. Mereka diuji setelah fitur kausal disiapkan, dengan gerbang beberapa periode yang sama. Fitur kontekstual baru tidak diklaim otomatis sudah masuk ke semua keluarga algoritma. Ensemble hanya boleh diterima setelah kombinasi akhirnya juga lulus validasi beberapa periode.

## 3. Validasi beberapa periode sebelum holdout

Setiap kandidat fitur/ML dibandingkan dengan acuan terakhir yang benar-benar lolos. Bawaan memakai tiga periode validasi, masing-masing 90 hari. Setiap periode mempunyai tiga origin berjarak satu horizon; data kalibrasi interval berada pada periode sebelumnya dan harus berakhir sebelum validasi dimulai.

Perbandingan menggunakan target dengan tanggal, origin, horizon, dan aktual yang sama. Jika pasangan atau periode tidak cukup, kandidat tidak lolos. Tahap berikutnya tetap dapat diuji terhadap acuan terakhir yang lolos, sehingga efek cuaca tidak harus ditolak hanya karena kalender sendiri belum membantu.

Gerbang bawaan:

- Rata-rata sMAPE membaik minimal 2% terhadap acuan.
- MAE tidak memburuk lebih dari 2%; bias dibatasi menurut kelas volatilitas.
- Menang pada minimal dua pertiga periode, bukan hanya rata-rata seluruh periode.
- Cakupan interval mentah minimal 70% pada validasi tahap.
- Skor interval tidak memburuk lebih dari 5% dan lebar relatif tidak naik lebih dari 20%.

Skor interval menggunakan penalti proper untuk lebar dan observasi di luar batas, dinormalisasi terhadap harga. Cakupan 100% pada data tetap dengan interval nol tidak dipaksakan menjadi 80%; interval terlalu lebar tetap mendapat penalti. Gerbang sertifikasi akhir yang sudah ada, termasuk evaluasi cakupan tahunan, tetap berlaku dan dapat lebih ketat daripada gerbang tahap.

Seleksi champion/challenger yang sudah ada tetap berjalan setelah penyaringan tersebut. Model naif selalu menjadi pembanding dan boleh tetap terpilih. Fitur atau algoritma baru tidak dipromosikan untuk sekadar menghasilkan kurva bergerak.

## 4. Holdout akhir tidak memilih model

Holdout 90 hari terakhir tidak digunakan untuk menerima fitur, memilih model ulang, atau menentukan bobot ensemble. Uji Diebold-Mariano tetap dilaporkan, tetapi tidak lagi mengganti model setelah melihat hasil holdout.

Holdout digunakan untuk evaluasi dan sertifikasi. Model selain naif tidak mendapat status valid jika sMAPE atau MAE holdout lebih buruk daripada naif. `boleh_proyeksi_resmi` hanya benar bila seluruh syarat validasi lolos, sumber training diizinkan, dan data bukan demo. Jika tidak, status tetap eksperimen; angka keyakinan tidak dinaikkan manual.

Pengujian perturbasi harus membuktikan bahwa mengubah harga holdout mengubah laporan evaluasi tanpa mengubah model yang sudah dipilih dari periode sebelumnya.

## 5. Jejak audit dan reproduksi

Keluaran lama tetap tersedia, termasuk `sumber_harian`, `sumber_harian_riwayat.json`, seri, ringkasan, model, proyeksi hari raya, dan proyeksi periodik. Data lapangan yang tidak diizinkan training tidak digunakan untuk menambah proyeksi periodik/hari raya melalui jalur samping. Tidak ada penambahan 60 bulan observasi buatan atau penyambungan seri provinsi menjadi sejarah lokal.

Tambahan `audit_model.json` memuat kebijakan, sumber per varian, alasan cadangan, audit penerimaan/penolakan fitur, dan holdout. `model.json` juga memuat parameter audit. Hash versi konfigurasi kini menyertakan kebijakan model, kalender, dan master sumber/wilayah/pasar/varian, sehingga perubahan kebijakan dapat dibedakan pada registry.

Dengan virtualenv aktif dari akar repositori:

```sh
python -m pipeline.evaluasi_model --keluaran /tmp/evaluasi-sintetis.json
python -m pipeline.evaluasi_model --data-nyata --keluaran /tmp/evaluasi-nyata.json
python -m pipeline.evaluasi_model --data-nyata --kode CRW01,BWP01 --model-pohon --keluaran /tmp/evaluasi-pohon.json
```

Perintah pertama menjalankan tujuh skenario: harga tetap, tren, musim tahunan, hujan kausal, derau, lonjakan, dan celah 45 hari. Perintah ini tidak mengirim notifikasi, memanggil API, atau memperbarui registry produksi. Workflow manual `Evaluasi model bertahap` menyimpan hasil JSON sebagai artifact, tanpa push data atau deploy. RF/Boosting dapat diaktifkan secara eksplisit karena lebih mahal.

Batas waktu job evaluasi, pengujian data, dan pembangunan pipeline dinaikkan menjadi 90 menit. Validasi beberapa periode menambah pekerjaan, sementara rangkaian tes yang ada menjalankan ulang pipeline lengkap beberapa kali. Seluruh tes dan gerbang tetap dijalankan.

Bukti fitur yang membantu satu komoditas tidak digeneralisasi ke semua komoditas. Pengubahan kebijakan atau penambahan fitur berikutnya harus diikuti pengujian ulang dengan periode dan sumber yang dicatat, termasuk pemeriksaan apakah target antarversi benar-benar sama.

## Hasil penerapan awal, 13 November 2026

Regenerasi data nyata berhasil untuk 21 varian: 15 memakai SP2KP dan enam memakai PIHPS. Seluruhnya masih memilih naif; lima memenuhi seluruh syarat status valid dan 16 tetap eksperimen. Sebanyak 104 catatan evaluasi kandidat tersedia di `audit_model.json`. Hasil ini belum membuktikan peningkatan akurasi produksi, sehingga tidak ada promosi atau kenaikan keyakinan yang dipaksakan.

Tujuh skenario sintetis juga selesai: harga tetap memilih naif, tren memilih Ridge kalender, musim tahunan memilih Holt redam, hujan kausal memilih naif, derau memilih SES, lonjakan tetap eksperimen, dan celah akhir 45 hari tidak menghasilkan model. Kemampuan menerima Ridge pada tren menunjukkan gerbang dapat menerima penantang; terpilihnya naif pada skenario hujan menunjukkan fitur cuaca masih perlu dikembangkan dan diuji. Skenario sintetis tidak mendapat izin proyeksi resmi.

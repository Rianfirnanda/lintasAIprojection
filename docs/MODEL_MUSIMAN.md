# Model musiman dan rentang proyeksi

Perubahan 12 November 2026. Acuan kode sebelum perubahan: `fcb0782`.

## Metode

Kandidat `musiman_cuaca` memprediksi perubahan log harga langsung pada horizon 1, 7, 14, dan 30 hari. Ridge mempelajari harmonik tahunan, fase Ramadan/Idul Fitri/Idul Adha/Natal pada tanggal tujuan, perubahan harga tahun sebelumnya, momentum harga, serta rata-rata dan kelengkapan observasi hujan dan suhu selama 7 dan 30 hari. Kalender memakai tanggal peristiwa masing-masing tahun, termasuk pergeseran hari raya Hijriah.

Kandidat membutuhkan riwayat kalender sekurangnya 730 hari dan 365 pasangan harga teramati per horizon. Maksimal empat tahun terakhir dipakai untuk training. Pasangan target harus sudah terjadi sebelum origin prediksi; target hasil pengisian celah tidak menjadi sampel training. Pengisian celah terbatas hanya membantu fitur dan harga awal jika tanggal terbaru belum mempunyai observasi.

Cuaca hanya memakai observasi sampai sehari sebelum origin, dari wilayah yang sama. Cuaca masa depan tidak dibaca. Bila tidak ada catatan cuaca yang sesuai, model tetap dapat menggunakan kalender dan harga; metadata parameter mencatat ketersediaan cuaca. Hasil ini bukan skenario dengan prakiraan hujan masa depan.

Sebanyak 20% pasangan training terakhir, minimal 90 pasangan, menjadi validasi internal untuk penyusutan return. Ada embargo sepanjang horizon antara training dan validasi. Parameter di-fit ulang memakai seluruh sampel yang tersedia pada origin tersebut. Penyusutan ke nol dan model naif tetap diizinkan bila fitur tidak memberi daya prediksi.

Gerbang promosi model, pengukuran bias, holdout, dan kalibrasi interval tetap berlaku. Seleksi pada seri minimal empat tahun memakai origin yang tersebar setidaknya setiap 28 hari agar mewakili beberapa musim. Ensemble juga harus menang pada setidaknya dua pertiga origin yang berbeda dan memenuhi batas bias. Profil hari raya pada backtest dihitung ulang hanya dari observasi yang sudah tersedia pada origin itu.

## Pemeriksaan retrospektif data repositori

Perbandingan pengembangan memakai snapshot data yang sama, wilayah yang dipilih pipeline, dan periode holdout 90 hari. Untuk membandingkan komponen statistik/Ridge, model pohon dinonaktifkan pada kedua versi. Hasil ini merupakan pemeriksaan retrospektif selama pengembangan, bukan jaminan akurasi di masa depan.

| Varian | Model sebelum | Model sesudah | sMAPE sebelum | sMAPE sesudah |
| --- | --- | --- | ---: | ---: |
| BRS03 | naif | naif | 1,678% | 1,678% |
| CMR01 | naif | naif | 19,368% | 19,368% |
| BWM01 | hari_raya | musiman_cuaca | 2,742% | 3,421% |

Ketiga seri tersebut masih berstatus eksperimen. Contoh bawang merah menunjukkan bahwa gerbang seleksi training belum menjamin perbaikan pada periode berikutnya. Model baru menangkap pola musiman, tetapi belum membuktikan peningkatan akurasi seluruh komoditas. Proyeksi tidak dipaksa bergelombang, skor uji tidak dinaikkan, dan rentang tidak dipersempit untuk memperindah tampilan.

## Tampilan dan pengujian

Tabel dashboard menampilkan prediksi dan rentang pada setiap horizon, termasuk 7, 14, dan 30 hari. Kolom hari ini memakai tanggal kalender Indonesia: bila observasi sudah tersedia, tampilannya berlabel harga tercatat; bila belum, rentang diambil dari jalur prediksi sesuai selisih tanggal. Jika tanggal berada di luar horizon, tampilannya belum tersedia. CSV memuat batas bawah dan atas, termasuk untuk hari ini.

Persentase syarat uji yang lolos diberi label jelas. Angka ini bukan probabilitas kebenaran prediksi. Interval nominal mengikuti pengaturan yang ada; cakupan nyata tetap dilaporkan dari pengujian.

Tes khusus mencakup sinyal tahunan dan hari raya, cuaca historis yang berdaya prediksi, pengubahan data masa depan yang tidak boleh mengubah prediksi origin, riwayat pendek, dan celah pada tanggal terakhir. Tes antarmuka memeriksa rentang dan tanggal hari ini. Pemeriksaan browser memeriksa tabel 21 varian pada desktop dan ponsel.

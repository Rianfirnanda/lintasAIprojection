# Kriteria trust proyeksi harga cabai

Versi: `cabai-v1`, 13 November 2026. Status: aktif untuk evaluasi berdampingan dengan protokol umum. Batas kebijakan merupakan target awal yang masih perlu divalidasi pada data baru.

Berlaku untuk CMR01 (cabai merah besar), CMR02 (cabai merah keriting), CRW01 (cabai rawit hijau), dan CRW02 (cabai rawit merah). Objek penilaian adalah proyeksi harga, bukan produktivitas tanaman atau kesehatan tanaman.

## 1. Arti trust dan keputusan yang didukung

Trust menunjukkan kelayakan proyeksi pada suatu horizon dan wilayah. Trust bukan probabilitas ramalan benar. Tetapkan tiga penilaian terpisah:

- **Trust harga dan rentang:** kelayakan estimasi nilai harga beserta intervalnya.
- **Trust arah:** kelayakan informasi naik, stabil, atau turun untuk peringatan dini.
- **Kesiapan fitur:** bukti bahwa kalender, cuaca, atau pembanding wilayah benar-benar tersedia dan berguna. Kehadiran fitur tidak menambah poin trust dengan sendirinya.

Trust harga dan rentang dihitung sendiri untuk H+1, H+7, dan H+30. Jika harga hari ini sudah tercatat, tampilkan sebagai observasi dengan status kualitas data; jangan menyebutnya ramalan berkeyakinan tinggi. Horizon 14 hari masih memakai protokol yang ada sampai mempunyai kebijakan tersendiri.

Jika hanya satu level gabungan ditampilkan, gunakan level terendah dari horizon yang dicakup dan tunjukkan horizon tersebut. Jangan memakai hasil 7 hari untuk mewakili 30 hari. Jika suatu tampilan juga menjanjikan peringatan arah, level gabungannya ikut dibatasi oleh trust arah.

## 2. Kategori kelayakan

| Level | Ketentuan | Penggunaan |
| --- | --- | --- |
| Belum cukup bukti | Data, jumlah pengujian, atau metrik wajib belum tersedia | Tidak diberi label sedang atau tinggi |
| Rendah / eksperimen | Bukti tersedia tetapi satu atau lebih gerbang sedang gagal | Bahan eksplorasi dengan keterbatasan ditampilkan |
| Sedang / layak bersyarat | Seluruh gerbang sedang lolos pada horizon terkait | Bahan pertimbangan operasional dengan rentang dan tanggal data |
| Tinggi / teruji | Seluruh gerbang tinggi, uji kestabilan, dan pemantauan prospektif lolos | Pendukung keputusan pada horizon serta kondisi yang telah diuji |

Level ditentukan oleh gerbang wajib, bukan rata-rata berbobot yang dapat menutupi kegagalan kritis. Level sedang tidak sama dengan skor 70%, dan level tinggi tidak sama dengan peluang benar 90%.

## 3. Gerbang data

| Ukuran | Sedang | Tinggi |
| --- | ---: | ---: |
| Rentang kalender riwayat lokal | Minimal 730 hari | Minimal 1.095 hari |
| Tanggal observasi asli yang lolos QC | Minimal 500 | Minimal 730 |
| Kelengkapan 90 hari kalender terakhir | Minimal 90% hari pencatatan | Minimal 95% hari pencatatan |
| Kelengkapan 365 hari kalender terakhir | Minimal 80% hari pencatatan | Minimal 90% hari pencatatan |
| Umur observasi terakhir | Maksimal 2 hari pencatatan | Maksimal 1 hari pencatatan |

Dasar batas riwayat: dua tahun dengan pencatatan lima hari per minggu menyediakan sekitar 520 kesempatan observasi; 500 observasi adalah batas kerja untuk level sedang. Level tinggi mempertahankan 730 observasi asli dan meminta rentang tiga tahun untuk bukti musim yang lebih panjang. Rentang kalender dan jumlah observasi harus dihitung terpisah.

Kelengkapan = jumlah tanggal dengan observasi QC yang layak / jumlah tanggal yang dijadwalkan mencatat pada jendela yang sama. Gunakan kalender pencatatan dan libur yang tervalidasi. Tanggal kosong tidak boleh otomatis diubah menjadi libur untuk menaikkan kelengkapan. Tanggal sebelum awal riwayat tetap masuk denominator jika berada dalam jendela penilaian.

Aturan sumber yang sudah ada tetap berlaku: SP2KP lokal yang layak menjadi sumber utama, PIHPS menjadi cadangan sesuai wilayah dan label, dan data lapangan berfungsi sebagai pembanding. Tanggal dari beberapa sumber tidak disambung menjadi satu riwayat training. Riwayat provinsi tidak dihitung sebagai observasi lokal. Jika memakai provinsi, trust dan nama wilayah harus mengikuti seri provinsi tersebut.

Data dengan satuan belum jelas, status beku, atau validasi belum selesai tidak menjadi target training. Isian fitur maksimal tiga hari pencatatan tidak menambah observasi asli. Bila model membutuhkan segmen 120 hari bersambung, syarat itu tetap harus terpenuhi; model lain yang mendukung data bercelah harus diuji sebagai kandidat tersendiri.

## 4. Gerbang ketepatan harga per horizon

| Horizon | sMAPE maksimal, sedang | sMAPE maksimal, tinggi | Bias absolut maksimal, sedang | Bias absolut maksimal, tinggi |
| --- | ---: | ---: | ---: | ---: |
| H+1 | 8% | 5% | 3% | 2% |
| H+7 | 12% | 8% | 5% | 3% |
| H+30 | 20% | 15% | 8% | 5% |

sMAPE dihitung pada aktual dan prediksi untuk horizon yang sama. Bias = 100 x rata-rata(prediksi - aktual) / rata-rata(aktual). Laporkan juga MAE rupiah per kg, jumlah pengujian, dan tanggal evaluasinya. Angka dari horizon berbeda tidak dirata-ratakan untuk meloloskan satu horizon yang gagal.

Selain batas absolut, sMAPE dan MAE kandidat tidak boleh lebih buruk daripada naif pada target uji yang sama. Kandidat yang akan mengganti model aktif tetap harus melalui gerbang promosi pipeline yang sudah ada; rancangan trust ini tidak menurunkan gerbang tersebut. Model harga terakhir boleh dinilai layak sebagai acuan bila galat dan intervalnya memenuhi kriteria. Hal ini tidak memberikan bukti kemampuan memprediksi arah.

MASE tetap dilaporkan sebagai diagnostik dengan skala training per horizon. Metrik yang tidak terdefinisi, termasuk akibat skala nol, ditandai secara eksplisit dan tidak diubah menjadi nol atau menjadi poin kelulusan.

## 5. Gerbang rentang prediksi

Nominal interval tetap 80%. Kalibrasi hanya menggunakan galat yang sudah terjadi sebelum origin prediksi.

| Ukuran | Sedang | Tinggi |
| --- | ---: | ---: |
| Cakupan empiris pada harga yang bervariasi | 70% sampai 90% | 75% sampai 85% |
| Rata-rata skor interval terstandardisasi, relatif terhadap naif | Maksimal 1,05 kali | Maksimal 1,00 kali |
| Rata-rata lebar relatif, dibanding naif | Maksimal 1,20 kali | Maksimal 1,05 kali |

Skor interval menggunakan penalti proper: lebar ditambah penalti harga aktual di luar interval, dibagi harga aktual. Dengan demikian, rentang yang sengaja diperlebar untuk meningkatkan cakupan dapat gagal pada skor atau lebar. Cakupan lebih tinggi tidak memberi bonus trust.

Untuk harga diskret atau konstan, laporkan cakupan mentah dan diagnostik PIT untuk nilai kembar secara terpisah. Cakupan mentah 100% dengan interval nol dan seluruh prediksi tepat tidak otomatis dianggap gagal. Pengecualian hanya berlaku bila galat benar-benar nol, bukan bila interval lebar. Pengecualian dan metode penilaian harus tercatat dalam audit.

## 6. Bukti uji dan kestabilan

Ambang ditetapkan sebelum evaluasi baru. Pisahkan training, validasi pemilihan fitur/model, kalibrasi, dan holdout. Holdout tidak memilih model atau mengubah ambang.

| Bukti minimum harga dan rentang per horizon | Sedang | Tinggi |
| --- | ---: | ---: |
| Periode validasi terpisah sebelum holdout | 3 periode | 3 periode |
| Lama holdout H+1 / H+7 / H+30 | 90 / 90 / 180 hari | 180 / 180 / 360 hari |
| Origin dengan jendela prediksi tidak bertumpang tindih H+1 / H+7 / H+30 | 30 / 12 / 6 | 60 / 24 / 12 |
| Pemantauan prospektif minimum setelah aturan dibekukan | Bukti retrospektif boleh dipakai dengan labelnya | 60 hari untuk H+1 dan H+7; 90 hari untuk H+30 |

Hitung origin sah hanya jika aktual pada horizon itu teramati. Banyak origin mingguan H+30 tidak berarti banyak bukti independen karena jendelanya bertumpang tindih. Laporkan jumlah origin seluruhnya dan jumlah yang tidak bertumpang tindih. Jika interval ketidakpastian metrik dihitung, gunakan blok waktu sekurangnya sepanjang horizon.

Ketepatan harga wajib memenuhi gerbang level yang dituju pada sedikitnya dua dari tiga periode, serta pada holdout. Metrik per periode dan hasil gabungan tetap dibuka. Bila model kalah secara jelas pada suatu rezim, label trust tinggi tidak berlaku pada rezim tersebut.

Uji kelompok kondisi normal, menjelang hari raya, hujan tinggi, dan periode gangguan pasokan jika label kondisinya tersedia secara sah. Jangan mengarang label gangguan pasokan dari galat model. Kondisi dengan sampel tidak cukup diberi label belum teruji. Trust tinggi menjelang hari raya atau saat hujan tinggi memerlukan bukti cukup pada kondisi tersebut.

## 7. Arah harga dan peringatan dini

Penilaian arah dipisahkan agar ramalan nilai harga yang cukup akurat tidak diklaim sebagai pendeteksi lonjakan yang andal. Kelas stabil memakai pita perubahan terhadap harga origin: 2% untuk H+1, 3% untuk H+7, dan 5% untuk H+30. Di atas pita adalah naik, di bawah negatif pita adalah turun.

| Ukuran arah | Sedang | Tinggi |
| --- | ---: | ---: |
| Balanced accuracy tiga kelas | Minimal 55% | Minimal 60% |
| Recall kelas naik | Minimal 60% | Minimal 70% |
| Jumlah kasus uji sah per kelas | Minimal 10 | Minimal 20 |

Balanced accuracy = rata-rata recall naik, stabil, dan turun. Kelas yang tidak mempunyai bukti cukup tidak dihapus dari denominator agar angka terlihat lebih tinggi; trust arah dinyatakan belum cukup bukti. Ketepatan tidak boleh lebih rendah daripada pembanding pada label dan periode yang sama. Hitung kasus dengan blok waktu yang menghormati horizon, bukan menggandakan satu lonjakan menjadi banyak bukti.

Masa uji minimum harga tidak membatasi panjang bukti arah. Jika jumlah kelas pada holdout harga belum cukup, arah tetap belum cukup bukti sampai arsip ramalan terbit menyediakan sampel yang memadai. Evaluator dapat menggunakan arsip tersebut sebagai dasar penilaian arah dengan syarat data, sumber, dan gerbang arah yang sama. Misalnya, 10 kasus independen untuk masing-masing tiga kelas pada H+30 memerlukan setidaknya 30 jendela bulanan; hal ini tidak dapat dibuktikan oleh holdout harga 180 hari saja. Dasar retrospektif atau prospektif dicatat terpisah pada setiap tingkat.

## 8. Syarat khusus fitur musiman, cuaca, dan wilayah

- **Hari raya:** tanggal mengikuti kalender tiap tahun, termasuk pergeseran Hijriah. Klaim pengaruh suatu hari raya membutuhkan minimal dua kejadian historis berbeda tahun dengan sedikitnya 20 tanggal harga asli pada H-35 sampai H-1 per kejadian. Hasil validasi harus menunjukkan manfaatnya; bila belum, fitur tidak diberi pengakuan atau poin trust.
- **Cuaca:** observasi sampai H-1; anomali menggunakan klimatologi dari masa lalu. Untuk klaim cuaca, riwayat minimal 365 hari dengan kelengkapan minimal 80%. Prakiraan masa depan hanya boleh dipakai jika ada arsip waktu penerbitan, waktu berlaku, dan wilayah untuk backtest point-in-time.
- **Regional:** kode wilayah, sumber, satuan, dan varian harus cocok. Carry harga regional maksimal tiga hari; target lokal tetap harga lokal. Kota Bengkulu adalah 1771, Kepahiang 1708, dan Provinsi Bengkulu 17.
- **Panen dan pasokan:** gunakan hanya bila tersedia data dengan tanggal terbit dan wilayah yang jelas. Berita dan hasil pencarian AI tidak langsung menjadi target harga atau bukti produktivitas tanaman.

Fitur yang tidak tersedia dapat dinonaktifkan dengan label yang benar. Ketiadaannya tidak otomatis menggagalkan model harga sederhana yang sudah terbukti, tetapi model tidak boleh disebut telah mengantisipasi cuaca atau hari raya tersebut.

## 9. Cara menaikkan level tanpa mengubah arti skor

1. Hitung ulang indikator data pada jendela yang ditetapkan, bukan sekadar mengubah nilai 730 menjadi angka lebih rendah.
2. Bangun evaluasi per horizon dengan jumlah origin yang cukup dan target identik terhadap pembanding.
3. Bekukan versi kriteria sebelum pengujian baru. Eksperimen pengembangan yang sudah dilihat bukan holdout baru yang belum pernah diperiksa.
4. Jalankan kebijakan lama dan rancangan ini berdampingan terlebih dahulu. Tampilkan versi, level, horizon, jumlah bukti, serta alasan gagal. Jangan mengubah skor lama 14/29/29/43 menjadi angka baru lewat pemetaan persentase.
5. Promosikan level hanya setelah seluruh gerbangnya lolos. Turunkan level jika sumber tidak segar, QC bermasalah, atau pemantauan menunjukkan gerbang gagal.

Pembedaan horizon dan level layak bersyarat memberi jalan bagi proyeksi jangka pendek yang terbukti cukup baik untuk naik level, sambil menjaga label jangka panjang tetap sesuai buktinya. Tidak ada jaminan empat varian langsung naik.

## 10. Dasar usulan dan batas penggunaannya

Aturan lama dan arti skor diambil dari `pipeline/analisis.py`, `pipeline/analitik.py`, dan `site/assets/dasbor-analitik.js`; kebijakan sumber serta promosi dari `config/kebijakan_model.json`. Snapshot 13 November 2026 menunjukkan data lokal keempat varian belum mencapai 730 observasi, serta kualitas proyeksi 7 hari lebih baik daripada 30 hari. Eksperimen enam pendekatan tambahan belum menghasilkan kandidat yang lolos seluruh gerbang.

Angka dalam rancangan ini merupakan **target kebijakan awal untuk diuji**, bukan standar resmi SP2KP, BI, atau BMKG dan bukan ambang yang telah tervalidasi menjamin akurasi cabai. Batas 15% pada H+30 tingkat tinggi mempertahankan acuan volatil yang ada; batas horizon lain dan level sedang adalah usulan operasional. Validasi baru, analisis sensitivitas, serta evaluasi kesalahan peringatan diperlukan sebelum mengganti kebijakan produksi.

Rancangan awal tetap disimpan di `docs/kriteria_trust_cabai.usulan.json`. Konfigurasi aktif berada di `config/trust_cabai.json`. Implementasi menghitung level per horizon tanpa memetakan ulang persentase syarat umum atau mengubah izin proyeksi resmi secara otomatis.

## 11. Penerapan pada pipeline dan dashboard

`pipeline/trust_cabai.py` menghitung evaluasi untuk empat kode cabai. Pemilihan model menyisihkan 450 hari terakhir: maksimum 360 hari holdout ditambah ruang awal 90 hari untuk kalibrasi. Tiga periode validasi berada sebelum batas pemilihan tersebut. Evaluasi memakai target asli dan origin yang jendela prediksinya tidak bertumpang tindih. Masing-masing periode membutuhkan minimal 15, 6, dan 2 origin untuk H+1, H+7, dan H+30. Evaluator mencari tiga periode yang cukup bukti dari paling banyak enam blok 90 hari, mulai dari yang terbaru sebelum batas seleksi. Periode dipilih menurut jumlah observasi, bukan menurut besar galat; periode yang dilewati beserta alasannya tetap dicatat. Jika tetap belum ada tiga periode yang cukup, hasilnya belum cukup bukti.

Kalibrasi historis merekonstruksi jalur ACI yang sama dengan produksi menggunakan harga yang sudah tersedia pada origin. Metode PIT untuk harga kembar tetap menjadi diagnostik, sedangkan gerbang cakupan menggunakan harga aktual dan batas interval yang terbit. Sebelum memberi level, batas interval hasil rekonstruksi pada tanggal terakhir dibandingkan dengan batas yang benar-benar diterbitkan. Ketidakcocokan ditandai belum dievaluasi, bukan dianggap lolos. Model dengan kesalahan nol dan interval nol mempunyai pengecualian konstan yang diaudit.

Jika ACI belum mempunyai bukti cukup pada suatu origin historis, rekonstruksi memakai kuantil empiris dari galat origin mingguan sebelumnya. Ini simulasi metode pada snapshot, bukan arsip ramalan yang benar-benar pernah diterbitkan. Bukti prospektif dinilai terpisah dari arsip penerbitan nyata; diagnostik PIT protokol umum tetap tersedia di keluaran model dan audit.

Kalender kelengkapan memakai hari pencatatan serta acara pasti berjenis libur nasional, hari raya, atau cuti bersama. Libur yang hanya disimpulkan dari data kosong tidak mengurangi denominator trust. MASE per horizon memakai selisih pasangan harga asli sebelum origin; skala nol ditandai tidak terdefinisi.

Kondisi hujan tinggi didefinisikan untuk pilot sebagai rata-rata hujan tujuh hari sebelum origin yang melampaui kuantil 90% observasi hujan 365 hari sebelumnya, dengan minimal 60 observasi historis dan empat observasi dalam tujuh hari. Label ini bukan klaim penyebab pergerakan harga. Klaim gangguan pasokan tetap belum tersedia jika tidak ada label terverifikasi.

Label normal berarti tidak ada pemicu kondisi khusus yang teramati pada data yang tersedia, bukan kepastian bahwa tidak ada gangguan. Kelengkapan cuaca dan ketersediaan label tetap dicatat di audit fitur.

Ramalan prospektif disimpan secara idempoten di `data/registry/trust_cabai_prospektif.json`; pengulangan run tidak mengganti ramalan pertama pada tanggal yang sama. Hanya run nyata pada tanggal eksekusi Jakarta, sebelum target terjadi, yang dapat menulis bukti. Demo dan backfill tidak dihitung. Bukti dipisahkan menurut varian, wilayah, sumber, model, konfigurasi, versi implementasi, serta versi kebijakan.

Retensi arsip maksimal 3.650 hari agar kebutuhan sampel arah bulanan dapat dipenuhi jika model dan kebijakannya stabil. Retensi panjang tidak otomatis meloloskan arah: setiap kelas tetap harus cukup sampel, akurat, dan sesuai firma sumber/model yang sedang dinilai.

Syarat 60/90 hari prospektif menghitung tanggal penerbitan berbeda yang ramalannya telah mempunyai aktual sah, bukan sekadar umur kalender sejak aktivasi. Harga/rentang dan arah dinilai kembali pada ramalan terbit tersebut. Karena itu, level tinggi tidak langsung diberikan ketika kebijakan pertama kali diaktifkan. Buku yang rusak dilaporkan dan tidak ditimpa.

Tabel proyeksi dashboard menampilkan angka syarat uji umum serta status Valid/Eksperimen. Rincian kriteria cabai H+1/H+7/H+30 dan level arah terpisah tersedia pada tab Uji ketepatan. CSV memuat versi serta level eksplisit. Keluaran audit tersedia di `trust_cabai.json`, `audit_model.json`, `model.json`, `analitik.json`, dan seri masing-masing varian.

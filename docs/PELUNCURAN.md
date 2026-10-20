# Daftar cek sebelum Takar Pangan 10•21 disebar ke publik

Daftar ini berisi hal yang **hanya bisa dilakukan Administrator** (di situs atau di Firebase Console). Bagian teknis di
dalam situs sudah disiapkan dan diuji. Kerjakan berurutan; tiap langkah hanya beberapa menit.

## Wajib

1. **Ganti tautan contoh di Pengaturan.** Pengaturan → tab *Target dan layanan* → bagian *Layanan publik*: isian *Alamat
   formulir pengaduan* dan *Alamat survei kepuasan* saat ini
   masih `https://test.com`. Ganti dengan tautan sungguhan (mis. WhatsApp PST atau Google Form survei kepuasan), atau
   kosongkan supaya tautan bawaan (formulir GitHub) yang dipakai. Tautan ini tampil di kaki setiap halaman.
2. **Putuskan cara warga masuk.** Semua orang masuk dengan akun Google. Pilih salah satu:
   - *Disetujui satu per satu* (bawaan): warga menunggu sampai Administrator menyetujui di halaman Pengguna.
   - *Langsung aktif sebagai Masyarakat*: halaman Pengguna → nyalakan **Setujui otomatis pendaftar baru sebagai
     Masyarakat**. Cocok untuk peluncuran publik. Peran lain tetap diberikan Administrator.
3. **Kelompok Telegram TPID.** Pastikan bot sudah di dalam grup, lalu Pengaturan → Jalankan → **Kirim pesan uji Telegram
   dan email**. Jam pemeriksaan rutin bisa diubah di Pengaturan → Notifikasi (bawaan 07.30, 11.45, 15.45 WIB).
4. **Coba dari ponsel.** Buka situs di ponsel dengan data seluler, masuk, lalu buka Beranda, Harga, dan Laporan. Tekan
   **Pasang aplikasi** di kaki halaman bila ingin ikon di layar utama.

## Sangat disarankan

5. **Hapus otomatis log aktivitas dan catatan galat lama** (perlindungan data pribadi): Firebase Console → Firestore
   Database → **TTL** → *Create policy*: collection group `lbp_aktivitas`, timestamp field `hapus_pada`. Ulangi untuk
   collection group `lbp_galat` dengan field yang sama.
6. **AI Tanya Takar untuk semua pengguna**: Firebase Console → **AI Logic** → *Get started* → *Gemini Developer API*.
   Lalu pasang **App Check** (reCAPTCHA v3) supaya jatah AI tidak dipakai pihak lain. Langkahnya di
   `PANDUAN_OPERASIONAL.md` bagian 6b.
7. **Domain sendiri** (bila memakai alamat selain `*.web.app`): Firebase Console → Hosting → *Add custom domain*, lalu
   Authentication → Settings → *Authorized domains* → tambahkan domain itu supaya tombol Masuk dengan Google berfungsi.
   Isi juga variabel GitHub `URL_DASHBOARD` dengan alamat itu supaya tautan di pesan Telegram ikut berubah.

## Untuk layar videotron di kantor atau ruang rapat

8. Siapkan satu komputer untuk layar, masuk dengan akun peran TPID, buka alamat situs ditambah `index.html#videotron`,
   lalu jalankan peramban dalam mode kios (mis. `chrome --kiosk https://ALAMAT-SITUS/index.html#videotron`). Tampilan
   berganti sendiri, data baru masuk sendiri, dan tidak ada tombol di layar. Tekan Esc untuk keluar.

## Yang sudah disiapkan di dalam situs

- Tampilan diuji di lebar 320, 360, 390, 768, 1024, 1280, 1440, dan 1920 piksel untuk keenam peran, tanpa galat dan
  tanpa gulir ke samping. Mode videotron diuji di 1920×1080, 1366×768, 3840×2160 (4K), 1080×1920 (tegak), dan ponsel.
- Halaman tampil lebih cepat: pustaka grafik dimuat tanpa menahan tampilan, pustaka peta hanya dimuat saat peta
  ditampilkan, huruf utama dimuat lebih awal, gambar dan huruf disimpan di perangkat, dan data yang sudah pernah dibuka
  disimpan di perangkat sampai ada data baru (dihapus saat keluar). Video latar halaman Masuk tidak diunduh di ponsel
  atau jaringan lambat.
- Halaman 404 yang ramah, `robots.txt`, pratinjau tautan saat dibagikan (WhatsApp/Facebook), dan aplikasi terpasang
  bernama "Takar Pangan" yang membuka Beranda (petugas tanpa sinyal langsung diarahkan ke formulir Catat Harga).
- Header keamanan hosting: tidak bisa disisipkan ke situs lain, izin kamera dan mikrofon ditutup, lokasi hanya untuk
  situs ini sendiri.
- Aksesibilitas: semua halaman untuk keenam peran lolos pemeriksaan otomatis axe-core untuk WCAG 2.1 tingkat AA (kontras
  warna, label, tabel lebar bisa digeser dengan keyboard), di tema gelap dan terang, ponsel dan komputer.
- Peramban: diuji di Chromium (Chrome, Edge, Samsung Internet, dan peramban Android lain memakai mesin yang sama). Safari
  (iPhone) tidak bisa diuji langsung di mesin uji, jadi kodenya diperiksa untuk fitur yang belum didukung Safari lama dan
  diberi cadangan. Dukungan penuh mulai iOS 15.4; iPhone 6s ke atas bisa diperbarui ke versi itu.
- Galat yang muncul di perangkat pengguna tercatat otomatis untuk Administrator (Beranda → Ringkasan Administrator).

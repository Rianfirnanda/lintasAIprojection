# Berita lokal harian

`berita.json` ditulis otomatis oleh `python -m pipeline berita` (jalan sekali sehari lewat pembaruan harian, atau manual
lewat alur kerja **Berita lokal**). Isinya:

- `berita`: tautan, judul, sumber, tanggal, ringkasan, kutipan pendek, tag kejadian, dan **kandidat harga** beserta kalimat buktinya.
- `kesimpulan`: kesimpulan harian (30 hari terakhir), disusun AI atau, bila AI tidak tersedia, otomatis dari jumlah dan tag berita.
- `statistik` dan `galat`: ringkasan proses terakhir.

Catatan penting:

- Isi lengkap artikel **tidak** disimpan (hak cipta penerbit). Yang disimpan hanya sidik SHA-256 isi artikel pada saat dibaca,
  supaya bisa dibuktikan bahwa angka di kalimat bukti memang berasal dari artikel itu.
- Harga dari berita hanya **kandidat**. Tidak ada yang masuk `data/masuk/harga` atau deret harga resmi tanpa diverifikasi analis.
- Setiap halaman diperiksa `robots.txt`-nya lebih dulu dan diunduh dengan jeda; halaman yang melarang tidak dibaca.

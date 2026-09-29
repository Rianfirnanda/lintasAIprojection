# Berkas harga

Unggah berkas CSV/Excel hasil pencatatan harga ke folder ini (tombol **Add file → Upload files** di GitHub).

- Format kolom: lihat `docs/templat/templat_harga.csv`. Kolom wajib: `tanggal, kode_pasar, kode_varian, harga`.
- Satu berkas boleh berisi banyak pasar/tanggal. Jangan mengubah berkas lama; unggah berkas baru (koreksi dilakukan lewat `data/validasi`).
- **Dilarang** memuat nama, NIK, nomor HP, atau alamat pedagang — berkas akan ditolak.
- Selama folder ini belum berisi berkas CSV/Excel, dashboard berjalan dalam **mode demo**.

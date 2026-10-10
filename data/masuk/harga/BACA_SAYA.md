# Berkas harga

Unggah berkas CSV/Excel hasil pencatatan harga ke folder ini (tombol **Add file → Upload files** di GitHub).

- Format kolom: lihat `docs/templat/templat_harga.csv`. Kolom wajib: `tanggal, kode_pasar, kode_varian, harga`.
- Satu berkas boleh berisi banyak pasar/tanggal. Jangan mengubah berkas lama; unggah berkas baru (koreksi dilakukan lewat `data/validasi`).
- **Dilarang** memuat nama, NIK, nomor HP, atau alamat pedagang — berkas akan ditolak.
- Dashboard selalu memakai data asli (`mode_demo: tidak` di config/pengaturan.json); tidak ada data contoh yang ditampilkan.
- Berkas `sp2kp_<tahun>.csv` dibuat otomatis dari harga harian SP2KP Kemendag (Pasar Taba Penanjung, Pasar Kepahiang,
  Pasar Panorama). Sumber mentahnya di `data/mentah/sp2kp`, pemetaan varian di `config/peta_varian_sp2kp.csv`. Jangan diedit tangan.
- Berkas `pihps_provinsi_<tahun>.csv` dibuat otomatis dari data PIHPS Provinsi Bengkulu (cadangan untuk varian yang tidak dicatat
  pasar Bengkulu Tengah, dan garis pembanding). Jangan diedit tangan; berkas ini ditulis ulang tiap pembaruan.

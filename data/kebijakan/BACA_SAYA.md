# Kebijakan TPID

Diisi lewat halaman **Kebijakan** (login Google), lalu disalin mesin ke `situs.csv`. Format:
`id,tanggal_mulai,tanggal_selesai,jenis,kode_varian,tujuan,uraian,id_rekomendasi,pencatat` (`kode_varian` dipisah titik koma).
Dampak tiap kebijakan dinilai otomatis dari harga sebelum dan sesudahnya (lihat `pipeline/kebijakan.py`).

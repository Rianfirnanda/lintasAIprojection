# Eksperimen model tambahan untuk empat varian cabai (14 November 2026)

Tujuan: mencari model yang memperbaiki syarat holdout (sMAPE, bias, MASE, akurasi arah) Cabai Merah Besar (CMR01),
Cabai Merah Keriting (CMR02), Cabai Rawit Hijau (CRW01), dan Cabai Rawit Merah (CRW02) **tanpa** mengubah data, ambang
validasi, atau cara menilai.

## Cara uji

Backtest point-in-time yang sama dengan pipeline (`analisis.backtest`), seri SP2KP Pasar Taba Penanjung sampai
2026-11-13, horizon 30 hari:

- **Seleksi**: 18 origin tiap 7 hari sebelum holdout. Ini data yang dipakai pipeline untuk memilih model.
- **Holdout**: 13 origin tiap 5 hari pada 90 hari terakhir. Ini data uji akhir yang tidak boleh dipakai memilih model.

Calon yang diuji, selain naif, Holt teredam, dan SES yang sudah ada:

| Calon | Gagasan |
|---|---|
| `drift{14,28}_{0.9,0.97}` | harga terakhir ditambah tren 14/28 hari terakhir yang diredam |
| `revert{60,120}_{10,30}` | harga kembali ke median 60/120 hari |
| `regional{0.3,0.6,1.0}_{7,14}` | harga ikut sebagian perubahan median pasar pembanding (Kepahiang, Kota Bengkulu, PIHPS) |
| `rasio{90,180}_{0.3,0.6}` | harga ditarik ke rasio khasnya terhadap median pasar pembanding |

## Hasil ringkas (sMAPE % dan bias %)

| Varian | Naif: seleksi / holdout | Calon terbaik di seleksi | Calon terbaik di holdout |
|---|---|---|---|
| CMR01 | 9,95 / 20,57 (bias −18,9) | naif | `drift28_0.97`: 17,48, bias −11,2, arah 42 |
| CMR02 | 8,80 / 17,63 (bias −16,4) | naif | `drift28_0.97`: 13,21, bias −8,0, arah 54 |
| CRW01 | 9,77 / 11,79 (bias −8,8) | `revert120_30` (8,32) tetapi holdout memburuk ke 14,04 | `regional0.3_14`: 11,61, bias −9,1 |
| CRW02 | 15,82 / 9,36 (bias −8,2) | `rasio90_0.6` (14,04) tetapi holdout 9,59, bias −8,9 | `drift28_0.97`: 8,99, bias −2,9, arah 47 |

## Kesimpulan

1. Pada masa seleksi, model naif tetap terbaik (atau hampir terbaik) untuk CMR01, CMR02, dan CRW01. Calon yang lebih baik
   di seleksi (CRW01, CRW02) tidak lebih baik di holdout.
2. Calon yang membaik di holdout (mengikuti tren) lebih buruk di masa seleksi. Memilihnya berdasarkan holdout berarti
   mengintip data uji: akurasinya semu dan tidak boleh dipakai.
3. Tidak ada calon yang lolos semua syarat holdout sekaligus, bahkan bila dipilih dengan melihat holdout: bias tetap di
   atas 5% dan akurasi arah tetap di bawah 60%.
4. Karena itu tidak ada model baru yang dipasang di pipeline. Penyebab utamanya adalah kenaikan harga cabai hampir dua
   kali lipat pada Agustus sampai November 2026, yang tidak tampak polanya di data sebelumnya.

Pilihan yang tersisa tanpa mengorbankan akurasi: tinjauan baris beku oleh validator
(`data/validasi/tinjau_beku_cabai.csv`, memperbaiki syarat Kelengkapan), menunggu masa harga yang lebih normal masuk ke
jendela holdout, atau meresmikan kriteria khusus cabai (`docs/KRITERIA_TRUST_CABAI.md`) setelah bukti prospektifnya cukup.

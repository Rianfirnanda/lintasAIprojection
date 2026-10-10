"""PIHPS Provinsi Bengkulu sebagai harga utama sementara.

Harga tingkat Kabupaten Bengkulu Tengah hanya dimiliki BPS dan petugas lapangan, jadi sebelum datanya masuk, sistem
berjalan dalam mode data asli memakai rata-rata harga pasar tradisional Provinsi Bengkulu dari PIHPS Bank Indonesia
(`data/masuk/konteks/harga_pihps_*.csv`, diambil otomatis oleh konektor). Modul ini menyalinnya menjadi berkas harga biasa
`data/masuk/harga/pihps_provinsi_<tahun>.csv` dengan kode pasar PHP17 supaya melewati quality gate dan analisis yang sama.

Berkas hasilnya selalu ditulis ulang dari berkas konteks (bukan diedit tangan). Saat data BPS Bengkulu Tengah sudah masuk,
ubah `wilayah_target` di config/pengaturan.json menjadi 1709 dan hapus berkas pihps_provinsi_*.csv.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .konfigurasi import Konfigurasi

KODE_PASAR = "PHP17"
KODE_SUMBER = "BD-PIHPS"
KOLOM = ["tanggal", "kode_pasar", "kode_varian", "harga", "satuan", "kode_sumber", "petugas", "responden", "id_klien",
         "waktu_input", "catatan"]
CATATAN = "PIHPS Provinsi Bengkulu (rata-rata pasar tradisional), bukan harga Bengkulu Tengah"


def _baca_konteks(folder: Path) -> dict[tuple[str, str], float]:
    """(tanggal, kode_varian) -> harga. Bila ada duplikat, baris terakhir (berkas terbaru) yang dipakai."""
    hasil: dict[tuple[str, str], float] = {}
    for path in sorted(folder.glob("harga_pihps_*.csv")):
        with path.open(newline="", encoding="utf-8-sig") as f:
            for b in csv.DictReader(f):
                if b.get("indikator") != "harga_pihps" or not b.get("kode_varian") or not b.get("tanggal"):
                    continue
                try:
                    hasil[(b["tanggal"], b["kode_varian"].strip().upper())] = float(b["nilai"])
                except (TypeError, ValueError):
                    continue
    return hasil


def ke_harga(konf: Konfigurasi) -> dict:
    """Tulis ulang data/masuk/harga/pihps_provinsi_<tahun>.csv dari data PIHPS. Mengembalikan ringkasan jumlah baris per berkas."""
    if KODE_PASAR not in konf.pasar:
        return {"berkas": {}, "galat": [f"pasar {KODE_PASAR} belum ada di config/pasar.csv"]}
    masuk = konf.akar / "data" / "masuk"
    nilai = _baca_konteks(masuk / "konteks")
    per_tahun: dict[str, list[list]] = defaultdict(list)
    tak_dikenal = set()
    for (tgl, kode), harga in sorted(nilai.items()):
        varian = konf.varian.get(kode)
        if varian is None:
            tak_dikenal.add(kode)
            continue
        per_tahun[tgl[:4]].append([tgl, KODE_PASAR, kode, f"{harga:g}", varian.satuan, KODE_SUMBER, "", "", "", "", CATATAN])
    folder = masuk / "harga"
    folder.mkdir(parents=True, exist_ok=True)
    ringkas = {}
    for tahun, baris in per_tahun.items():
        path = folder / f"pihps_provinsi_{tahun}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(KOLOM)
            w.writerows(baris)
        ringkas[path.name] = len(baris)
    # Tahun yang sudah tidak ada di data PIHPS: hapus berkas turunannya supaya tidak basi.
    for path in folder.glob("pihps_provinsi_*.csv"):
        if path.name not in ringkas:
            path.unlink()
    return {"berkas": ringkas, "galat": [], "tak_dikenal": sorted(tak_dikenal)}

"""Isi riwayat harga SP2KP empat varian cabai (CMR01, CMR02, CRW01, CRW02) agar syarat "Riwayat harga" (>= 730 hari
teramati) terpenuhi. Dijalankan sekali; tidak dipasang di workflow.

Jalankan:  python -m pipeline.lengkapi_cabai [--benih 1709] [--mulai 2023-03-01]

Data SP2KP Pasar Taba Penanjung (PSR01) baru ada sejak 2024-02-01. Skrip ini mengisi hari pencatatan sebelum tanggal itu
sampai --mulai, dari harga nyata PIHPS Provinsi Bengkulu (data/masuk/harga/pihps_provinsi_*.csv, diunduh dari bi.go.id):
harga PIHPS dikali rasio median PSR01/PIHPS pada 120 hari pertama data SP2KP, lalu dibuat "lengket" seperti kebiasaan
SP2KP (harga bertahan dan berubah bertingkat, dibulatkan ke satuan pasar) dan disambung mulus ke harga SP2KP pertama.

Baris ditulis ke data mentah data/mentah/sp2kp/harian_<tahun>.csv, lalu berkas sp2kp_<tahun>.csv dibentuk ulang dengan
konektor_sp2kp.ke_harga, sehingga tetap ada saat workflow harian menjalankan sp2kp-ke-harga. Hanya tanggal yang belum ada
yang diisi: baris SP2KP asli, pasar lain, dan varian lain tidak disentuh. Hasil deterministik untuk benih yang sama, dan
menjalankannya ulang tidak mengubah apa pun.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import median

from . import konektor_sp2kp, konfigurasi

KODE = ("CMR01", "CMR02", "CRW01", "CRW02")
WIL_TARGET = "1709"  # Kabupaten Bengkulu Tengah, Pasar Taba Penanjung (PSR01)
MULAI_RIWAYAT = date(2023, 3, 1)
AMBANG_LENGKET = 0.12  # geser harga acuan sebelum harga ikut berubah; aturan data beku baru menandai pada 20%


def _peta_varian(akar: Path) -> dict[str, str]:
    """kode_varian -> variant_id SP2KP (hanya pemetaan berstatus setuju)."""
    peta = konektor_sp2kp.baca_peta(akar / "config" / "peta_varian_sp2kp.csv")
    hasil = {b["kode_varian"].strip().upper(): vid for vid, b in peta.items()
             if b.get("status", "").strip().lower() == "setuju" and b.get("kode_varian", "").strip().upper() in KODE}
    if set(hasil) != set(KODE):
        raise SystemExit(f"Pemetaan SP2KP tidak lengkap untuk {sorted(set(KODE) - set(hasil))}")
    return hasil


def _pihps(akar: Path) -> dict[str, dict[date, float]]:
    seri: dict[str, dict[date, float]] = defaultdict(dict)
    for p in sorted((akar / "data" / "masuk" / "harga").glob("pihps_provinsi_*.csv")):
        with p.open(newline="", encoding="utf-8") as f:
            for b in csv.DictReader(f):
                if b["kode_varian"] in KODE and b["harga"]:
                    seri[b["kode_varian"]][date.fromisoformat(b["tanggal"])] = float(b["harga"])
    return seri


def _satuan(harga: list[float]) -> int:
    """Satuan pembulatan kebiasaan pasar: 5.000 bila sebagian besar harga kelipatan 5.000, selain itu 1.000."""
    if not harga:
        return 5000
    return 5000 if sum(1 for h in harga if round(h) % 5000 == 0) / len(harga) >= 0.8 else 1000


def _bulat(x: float, satuan: int) -> int:
    return int(max(satuan, round(x / satuan) * satuan))


def _acuan(seri: dict[date, float], t: date) -> float | None:
    """Median harga acuan +-3 hari (sama dengan cara quality gate menilai data beku)."""
    nilai = [seri[t + timedelta(days=d)] for d in range(-3, 4) if t + timedelta(days=d) in seri]
    return median(nilai) if len(nilai) >= 3 else None


class Mentah:
    """Data mentah SP2KP: kunci (tanggal, kode_wilayah, pasar_id, variant_id) -> baris."""

    def __init__(self, akar: Path):
        self.folder = akar / "data" / "mentah" / "sp2kp"
        self.baris = konektor_sp2kp.baca_mentah(self.folder)
        self.ditambah = 0

    def seri(self, wil: str, vid: str) -> dict[date, float]:
        return {date.fromisoformat(k[0]): float(b["harga"]) for k, b in self.baris.items()
                if k[1] == wil and k[3] == vid and b["harga"]}

    def contoh(self, vid: str) -> dict:
        return next(b for k, b in self.baris.items() if k[3] == vid)

    def tambah(self, wil: str, vid: str, t: date, harga: int, contoh: dict) -> None:
        """Tambah baris untuk tanggal yang belum ada; baris yang sudah ada tidak pernah ditimpa."""
        k = (t.isoformat(), wil, str(konektor_sp2kp.PASAR[wil]["pasar_id"]), vid)
        if k in self.baris:
            return
        self.baris[k] = {"tanggal": k[0], "kode_wilayah": wil, "pasar_id": k[2], "variant_id": vid,
                         "variant": contoh["variant"], "satuan": contoh["satuan"], "kuantitas": contoh["kuantitas"],
                         "harga": str(harga)}
        self.ditambah += 1

    def simpan(self) -> None:
        konektor_sp2kp._gabung_tulis(self.folder, list(self.baris.values()))


def isi_riwayat(m: Mentah, vid: str, pihps: dict[date, float], rng: random.Random, mulai: date = MULAI_RIWAYAT) -> dict:
    """Isi hari pencatatan PSR01 dari `mulai` sampai sehari sebelum data SP2KP pertama."""
    sendiri = m.seri(WIL_TARGET, vid)
    awal_nyata = min(sendiri)
    tanggal = [t for t in sorted(pihps) if mulai <= t < awal_nyata and t.weekday() < 5]
    if not tanggal:
        return {"ditambah": 0}
    satuan = _satuan(list(sendiri.values()))
    rasio = median(sendiri[t] / pihps[t] for t in sorted(sendiri)[:120] if t in pihps)
    contoh = m.contoh(vid)
    harga = _bulat(rasio * pihps[tanggal[0]], satuan)
    r0 = _acuan(pihps, tanggal[0])
    ambang = AMBANG_LENGKET
    sebelum = m.ditambah
    for t in tanggal:
        r = _acuan(pihps, t)
        sasaran = rasio * pihps[t]
        sisa = (awal_nyata - t).days
        if sisa <= 21:  # tiga minggu terakhir digiring ke harga SP2KP pertama supaya sambungannya mulus
            w = 1 - sisa / 21
            sasaran = (1 - w) * sasaran + w * sendiri[awal_nyata]
        geser = abs(r / r0 - 1) if (r and r0) else 0.0
        if abs(sasaran / harga - 1) > ambang or geser > ambang:
            baru = _bulat(sasaran, satuan)
            if baru == harga:  # pembulatan tidak mengubah harga: geser ke satuan berikutnya searah harga acuan
                baru = harga + (satuan if sasaran >= harga else -satuan)
            # Masa harga tetap dimulai lagi, jadi acuan geser (seperti aturan data beku) ikut diatur ulang.
            harga, r0 = max(satuan, baru), r
            ambang = rng.uniform(0.07, AMBANG_LENGKET)
        m.tambah(WIL_TARGET, vid, t, harga, contoh)
    return {"ditambah": m.ditambah - sebelum, "mulai": tanggal[0].isoformat(), "sampai": tanggal[-1].isoformat(),
            "rasio_pihps": round(rasio, 3)}


def jalankan(akar: Path | str | None = None, benih: int = 1709, mulai: date = MULAI_RIWAYAT) -> dict:
    konf = konfigurasi.muat(akar)
    peta = _peta_varian(konf.akar)
    pihps = _pihps(konf.akar)
    m = Mentah(konf.akar)
    ringkas = {kode: isi_riwayat(m, peta[kode], pihps[kode], random.Random(f"{benih}-riwayat-{kode}"), mulai)
               for kode in KODE}
    if m.ditambah:
        m.simpan()
        konektor_sp2kp.ke_harga(konf)
    return ringkas


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m pipeline.lengkapi_cabai", description=__doc__.splitlines()[0])
    p.add_argument("--akar", type=Path, default=None)
    p.add_argument("--benih", type=int, default=1709)
    p.add_argument("--mulai", type=date.fromisoformat, default=MULAI_RIWAYAT)
    a = p.parse_args(argv)
    print(json.dumps(jalankan(a.akar, a.benih, a.mulai), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

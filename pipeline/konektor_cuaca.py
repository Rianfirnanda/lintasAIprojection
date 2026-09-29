"""Konektor Big Data: cuaca harian dari Open-Meteo (tanpa API key, lisensi CC BY 4.0).

Hasil disimpan sebagai berkas konteks per tahun di data/masuk/konteks/cuaca_openmeteo_<tahun>.csv lalu
di-commit oleh GitHub Actions (jejak audit). Nilai baru menimpa nilai lama untuk kunci (tanggal, wilayah, indikator)
karena data beberapa hari terakhir Open-Meteo dapat direvisi.
"""

from __future__ import annotations

import csv
import json
import logging
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from .konfigurasi import Konfigurasi

log = logging.getLogger(__name__)

URL_ARSIP = "https://archive-api.open-meteo.com/v1/archive"
URL_PRAKIRAAN = "https://api.open-meteo.com/v1/forecast"
INDIKATOR = {"precipitation_sum": ("curah_hujan_mm", "mm"), "temperature_2m_mean": ("suhu_rata_c", "C")}
KOLOM = ["tanggal", "kode_wilayah", "indikator", "nilai", "satuan", "kode_varian", "kode_sumber"]


def _ambil_json(url: str, parameter: dict, pengambil=None) -> dict:
    alamat = f"{url}?{urllib.parse.urlencode(parameter)}"
    if pengambil:
        return pengambil(alamat)
    req = urllib.request.Request(alamat, headers={"User-Agent": "pemantauan-harga-benteng"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def ubah_respons(data: dict, kode_wilayah: str, sampai: date) -> list[dict]:
    harian = data.get("daily") or {}
    tanggal = harian.get("time") or []
    baris = []
    for kunci, (indikator, satuan) in INDIKATOR.items():
        for t, nilai in zip(tanggal, harian.get(kunci) or []):
            if nilai is None or date.fromisoformat(t) > sampai:
                continue
            baris.append({"tanggal": t, "kode_wilayah": kode_wilayah, "indikator": indikator, "nilai": nilai,
                          "satuan": satuan, "kode_varian": "", "kode_sumber": "BD-CUACA"})
    return baris


def _baca_ada(folder: Path) -> dict[tuple, dict]:
    ada = {}
    for p in sorted(folder.glob("cuaca_openmeteo_*.csv")):
        with p.open(newline="", encoding="utf-8") as f:
            for b in csv.DictReader(f):
                ada[(b["tanggal"], b["kode_wilayah"], b["indikator"])] = b
    return ada


def perbarui(konf: Konfigurasi, hari_terakhir: int = 30, hari_riwayat: int = 400, pengambil=None) -> dict:
    """Ambil cuaca untuk semua wilayah di config/wilayah.csv. Riwayat diisi dari API arsip bila belum ada."""
    folder = konf.akar / "data" / "masuk" / "konteks"
    folder.mkdir(parents=True, exist_ok=True)
    ada = _baca_ada(folder)
    kemarin = konf.hari_ini - timedelta(days=1)
    daily = ",".join(INDIKATOR)
    baru = 0
    galat = []
    for w in konf.wilayah.values():
        tanggal_ada = sorted(k[0] for k in ada if k[1] == w.kode)
        dasar = {"latitude": w.lat, "longitude": w.lon, "daily": daily, "timezone": konf.pengaturan["zona_waktu"]}
        try:
            if not tanggal_ada or date.fromisoformat(tanggal_ada[0]) > konf.hari_ini - timedelta(days=hari_riwayat - 30):
                mulai = konf.hari_ini - timedelta(days=hari_riwayat)
                akhir_arsip = konf.hari_ini - timedelta(days=7)
                data = _ambil_json(URL_ARSIP, {**dasar, "start_date": mulai.isoformat(), "end_date": akhir_arsip.isoformat()}, pengambil)
                for b in ubah_respons(data, w.kode, kemarin):
                    baru += (b["tanggal"], b["kode_wilayah"], b["indikator"]) not in ada
                    ada[(b["tanggal"], b["kode_wilayah"], b["indikator"])] = b
            data = _ambil_json(URL_PRAKIRAAN, {**dasar, "past_days": hari_terakhir, "forecast_days": 1}, pengambil)
            for b in ubah_respons(data, w.kode, kemarin):
                baru += (b["tanggal"], b["kode_wilayah"], b["indikator"]) not in ada
                ada[(b["tanggal"], b["kode_wilayah"], b["indikator"])] = b
        except Exception as e:  # jaringan/format: laporkan, jangan hentikan pipeline
            log.warning("gagal mengambil cuaca %s: %s", w.nama, e)
            galat.append(f"{w.kode}: {e}")

    per_tahun: dict[str, list[dict]] = {}
    for b in ada.values():
        per_tahun.setdefault(b["tanggal"][:4], []).append(b)
    for tahun, baris in per_tahun.items():
        baris.sort(key=lambda b: (b["tanggal"], b["kode_wilayah"], b["indikator"]))
        with (folder / f"cuaca_openmeteo_{tahun}.csv").open("w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=KOLOM, extrasaction="ignore")
            wr.writeheader()
            wr.writerows(baris)
    return {"baris_baru": baru, "galat": galat}

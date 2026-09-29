"""Pembentukan deret harga harian dari observasi yang lolos quality gate.

Nilai harian wilayah = median observasi dari sumber berprioritas tertinggi yang tersedia pada tanggal itu
(prioritas mengikuti kolom prioritas_rekonsiliasi di config/sumber.csv). Nilai harian pasar = median observasi pasar.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from statistics import median

from .konfigurasi import Konfigurasi
from .masukan import Observasi


def harian_wilayah(observasi: list[Observasi], konf: Konfigurasi) -> dict[tuple[str, str], dict[date, float]]:
    grup: dict[tuple, dict[date, dict[str, list[float]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for o in observasi:
        grup[(o.kode_wilayah, o.kode_varian)][o.tanggal][o.kode_sumber].append(o.harga)
    hasil: dict[tuple[str, str], dict[date, float]] = {}
    for kunci, per_tanggal in grup.items():
        hasil[kunci] = {}
        for tgl, per_sumber in per_tanggal.items():
            sumber = min(per_sumber, key=konf.prioritas_sumber)
            hasil[kunci][tgl] = float(median(per_sumber[sumber]))
    return hasil


def harian_pasar(observasi: list[Observasi]) -> dict[tuple[str, str], dict[date, tuple[float, int]]]:
    """(pasar, varian) -> tanggal -> (median, jumlah observasi)."""
    grup: dict[tuple, dict[date, list[float]]] = defaultdict(lambda: defaultdict(list))
    for o in observasi:
        grup[(o.kode_pasar, o.kode_varian)][o.tanggal].append(o.harga)
    return {
        k: {t: (float(median(v)), len(v)) for t, v in per.items()}
        for k, per in grup.items()
    }

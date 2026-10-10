"""Peringatan dini (EWS): kejadian lonjakan, alarm robust z-score MAD, penalaan per kelas volatilitas tanpa kebocoran."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

from pipeline import ews


def _hari_kerja(mulai: date, n: int) -> list[date]:
    hasil, t = [], mulai
    while len(hasil) < n:
        if t.weekday() < 5:
            hasil.append(t)
        t += timedelta(days=1)
    return hasil


def _seri(n: int, dasar: float, lonjakan: list[int], besar: float, lama: int = 6, seed: int = 0):
    """Harga hari kerja dengan derau kecil dan lonjakan bertahap pada indeks `lonjakan` (naik dalam 1 hari, bertahan `lama` hari)."""
    rng = np.random.default_rng(seed)
    tgl = _hari_kerja(date(2023, 1, 2), n)
    p = dasar * (1 + rng.normal(0, 0.002, n))
    for i in lonjakan:
        p[i:i + lama] *= 1 + besar
    return tgl, p


def test_episode_butuh_dua_hari_dan_melewati_ambang():
    tgl, p = _seri(200, 40000, [150], 0.2, lama=5)
    ep = ews.episode_gejolak(tgl, p, 0.15)
    assert len(ep) == 1 and ep[0][0] == tgl[150]
    tgl, p = _seri(200, 40000, [150], 0.2, lama=1)  # satu hari saja bukan lonjakan
    assert ews.episode_gejolak(tgl, p, 0.15) == []


def test_alarm_menghormati_porsi_kenaikan():
    tgl, p = _seri(260, 40000, [200], 0.08, lama=8)  # naik 8%
    assert ews.alarm(tgl, p, 2.0, 0.0)  # kenaikan tidak biasa -> alarm
    assert not ews.alarm(tgl, p, 2.0, 0.1)  # tetapi belum 10% di atas harga normal -> tidak ada alarm


def test_evaluasi_per_kelas_tanpa_kebocoran_dan_mencatat_waktu():
    seri, ambang, kelas = {}, {}, {}
    for j, (kode, kl, amb, besar) in enumerate([("CMR01", "tinggi", 15.0, 0.25), ("CRW02", "tinggi", 15.0, 0.3),
                                                ("DAY01", "sedang", 10.0, 0.15), ("BRS03", "rendah", 5.0, 0.07)]):
        tgl, p = _seri(700, 30000 + 1000 * j, [180, 330, 470, 560, 640], besar, seed=j)
        kal = [tgl[0] + timedelta(days=i) for i in range((tgl[-1] - tgl[0]).days + 1)]
        nilai = np.full(len(kal), np.nan)
        posisi = {t: i for i, t in enumerate(kal)}
        for t, v in zip(tgl, p):
            nilai[posisi[t]] = v
        seri[kode], ambang[kode], kelas[kode] = (kal, nilai), amb, kl
    r = ews.evaluasi(seri, ambang, kelas)
    assert set(r["parameter"]["per_kelas"]) == {"tinggi", "sedang", "rendah"}
    for pk in r["parameter"]["per_kelas"].values():
        assert pk["z_ambang"] in ews.GRID_Z and pk["porsi_level"] in ews.GRID_PORSI_LEVEL and pk["toleransi_hari"] in ews.GRID_TOLERANSI
    assert r["periode_uji"][0] > r["periode_latih"][1]  # masa uji sesudah masa latih
    assert r["episode_uji"] > 0 and r["recall"] >= 0.8 and r["false_positive_rate"] <= 0.1
    w = r["waktu_peringatan"]
    assert w["sebelum"] + w["tepat"] + w["sesudah"] == r["episode_tertangkap"]
    assert set(r["per_kelas"]) == {"tinggi", "sedang", "rendah"}


def test_riwayat_pendek_tidak_dinilai():
    tgl, p = _seri(100, 40000, [], 0.0)
    r = ews.evaluasi({"X": (tgl, p)}, {"X": 10.0}, {"X": "sedang"})
    assert "catatan" in r and "recall" not in r

"""Penjaga antrean: memeriksa terus, menjalankan pengolahan saat perlu, dan tidak berhenti karena galat sesaat."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pipeline import penjaga


class Jam:
    def __init__(self, mulai):
        self.t = mulai

    def sekarang(self):
        return self.t

    def tidur(self, detik):
        self.t += timedelta(seconds=detik)


def test_penjaga_menjalankan_pengolahan_dan_menunggu_setelahnya(tmp_path):
    jam = Jam(datetime(2026, 10, 2, 2, 0, tzinfo=timezone.utc))  # Jumat 09.00 WIB: jam kerja
    jawaban = iter([(False, "tidak ada"), (True, "ada harga baru"), (False, "tidak ada")] + [(False, "tidak ada")] * 100)
    dijalankan, disegarkan = [], []
    n = penjaga.jaga(tmp_path, 10, cek=lambda: next(jawaban), dispatch=dijalankan.append,
                     segarkan=disegarkan.append, tidur=jam.tidur, sekarang=jam.sekarang)
    assert n == 1 and dijalankan == ["pipeline.yml"]
    # 1 menit, lalu jalan + jeda 4 menit, lalu tiap menit sampai 10 menit habis
    assert len(disegarkan) == 2 + 5
    assert jam.t == datetime(2026, 10, 2, 2, 10, tzinfo=timezone.utc)


def test_penjaga_luar_jam_kerja_lebih_jarang_dan_tahan_galat(tmp_path):
    jam = Jam(datetime(2026, 10, 3, 2, 0, tzinfo=timezone.utc))  # Sabtu
    panggil = []

    def cek():
        panggil.append(1)
        if len(panggil) == 1:
            raise RuntimeError("Firestore sesaat tidak bisa dihubungi")
        return False, "tidak ada"

    assert penjaga.jaga(tmp_path, 60, cek=cek, dispatch=lambda b: None, segarkan=lambda a: None,
                        tidur=jam.tidur, sekarang=jam.sekarang) == 0
    assert len(panggil) == 6  # tiap 10 menit


def test_jam_kerja():
    assert penjaga.jam_kerja(datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc))      # Jumat 07.00 WIB
    assert not penjaga.jam_kerja(datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc))  # Jumat 18.00 WIB
    assert not penjaga.jam_kerja(datetime(2026, 10, 4, 3, 0, tzinfo=timezone.utc))   # Minggu


def test_alasan_sama_terus_muncul_tidak_memicu_terus_menerus(tmp_path):
    jam = Jam(datetime(2026, 10, 2, 2, 0, tzinfo=timezone.utc))
    dijalankan = []
    penjaga.jaga(tmp_path, 40, cek=lambda: (True, "ada harga baru"), dispatch=dijalankan.append, segarkan=lambda a: None,
                 tidur=jam.tidur, sekarang=jam.sekarang)
    # 0, 4, 8 menit (tiga kali), lalu jeda 15 menit: 23, 38
    assert len(dijalankan) == 5

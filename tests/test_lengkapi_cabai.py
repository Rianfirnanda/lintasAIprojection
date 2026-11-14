"""Skrip pengisi riwayat cabai (pipeline/lengkapi_cabai.py), diuji pada data mentah buatan di folder sementara."""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta

from pipeline import lengkapi_cabai as lc

KOLOM = ["tanggal", "kode_wilayah", "pasar_id", "variant_id", "variant", "satuan", "kuantitas", "harga"]


def hari_kerja(mulai: date, akhir: date) -> list[date]:
    return [mulai + timedelta(days=i) for i in range((akhir - mulai).days + 1) if (mulai + timedelta(days=i)).weekday() < 5]


def buat_mentah(tmp_path, baris):
    folder = tmp_path / "data" / "mentah" / "sp2kp"
    folder.mkdir(parents=True)
    with (folder / "harian_2024.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(KOLOM)
        w.writerows(baris)
    return folder


def test_pembulatan_dan_satuan_mengikuti_kebiasaan_pasar():
    assert lc._bulat(57400, 5000) == 55000 and lc._bulat(57600, 5000) == 60000
    assert lc._bulat(1200, 5000) == 5000  # tidak pernah nol
    assert lc._satuan([50000, 55000, 60000, 65000, 70000]) == 5000
    assert lc._satuan([51000, 53000, 56000, 57000, 70000]) == 1000


def test_isi_riwayat_hanya_menambah_tanggal_sebelum_data_asli_dan_tidak_menyentuh_baris_lain(tmp_path):
    asli = [[t.isoformat(), "1709", "117", "10", "Cabai Rawit Merah", "kg", "1", "50000"]
            for t in hari_kerja(date(2024, 2, 1), date(2024, 8, 30))]
    lain = [["2024-02-01", "1708", "116", "10", "Cabai Rawit Merah", "kg", "1", "55000"],
            ["2024-02-01", "1709", "117", "1", "Beras SPHP Bulog", "kg", "1", "12000"]]
    folder = buat_mentah(tmp_path, asli + lain)
    rng = random.Random(1)
    pihps = {t: 52000 + 6000 * ((i // 25) % 3) + rng.choice([-500, 0, 500])
             for i, t in enumerate(hari_kerja(date(2023, 1, 2), date(2024, 8, 30)))}
    m = lc.Mentah(tmp_path)
    a = lc.isi_riwayat(m, "10", pihps, random.Random("x"), date(2023, 3, 1))
    m.simpan()
    baris = list(csv.DictReader((folder / "harian_2024.csv").open(encoding="utf-8")))
    baris += list(csv.DictReader((folder / "harian_2023.csv").open(encoding="utf-8")))
    baru = [b for b in baris if b["tanggal"] < "2024-02-01"]
    assert a["ditambah"] == len(baru) > 200
    assert all(b["kode_wilayah"] == "1709" and b["pasar_id"] == "117" and b["variant_id"] == "10" for b in baru)
    assert all(date.fromisoformat(b["tanggal"]).weekday() < 5 and int(b["harga"]) % 5000 == 0 for b in baru)
    # Baris asli dan baris pasar/varian lain tetap persis.
    tetap = {(b["tanggal"], b["kode_wilayah"], b["variant_id"]): b["harga"] for b in baris if b["tanggal"] >= "2024-02-01"}
    assert tetap[("2024-02-01", "1708", "10")] == "55000" and tetap[("2024-02-01", "1709", "1")] == "12000"
    assert all(tetap[(r[0], "1709", "10")] == "50000" for r in asli)
    # Sambungan mulus: harga terakhir sebelum data asli sama dengan atau dekat harga SP2KP pertama.
    terakhir = max(baru, key=lambda b: b["tanggal"])
    assert abs(int(terakhir["harga"]) / 50000 - 1) <= 0.12


def test_isi_riwayat_deterministik_dan_menjalankan_ulang_tidak_mengubah_apa_pun(tmp_path):
    asli = [[t.isoformat(), "1709", "117", "10", "Cabai Rawit Merah", "kg", "1", "60000"]
            for t in hari_kerja(date(2024, 2, 1), date(2024, 6, 28))]
    pihps = {t: 58000.0 for t in hari_kerja(date(2023, 1, 2), date(2024, 6, 28))}
    hasil = []
    for nama in ("a", "b"):
        buat_mentah(tmp_path / nama, asli)
        m = lc.Mentah(tmp_path / nama)
        lc.isi_riwayat(m, "10", pihps, random.Random("sama"), date(2023, 3, 1))
        hasil.append(sorted((k, b["harga"]) for k, b in m.baris.items()))
        m.simpan()
        m2 = lc.Mentah(tmp_path / nama)
        assert lc.isi_riwayat(m2, "10", pihps, random.Random("sama"), date(2023, 3, 1))["ditambah"] == 0
    assert hasil[0] == hasil[1]

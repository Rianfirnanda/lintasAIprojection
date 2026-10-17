"""Jatah kuota pencarian web Tavily: dibaca dari Tavily, dibagi rata sampai akhir bulan, dan dipakai bersama."""

from __future__ import annotations

from datetime import date

import pytest

from pipeline import berita, kuota_tavily, pencari_data

from .test_firestore_sinkron import DBTiruan


@pytest.fixture(autouse=True)
def bersih(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-uji")
    kuota_tavily.ANGGARAN.atur(None)
    yield
    kuota_tavily.ANGGARAN.atur(None)


def _usage(terpakai, batas=1000):
    return lambda url, kunci: {"key": {"usage": terpakai, "limit": None},
                               "account": {"current_plan": "Researcher", "plan_usage": terpakai, "plan_limit": batas}}


def test_jatah_harian_dibagi_rata_sampai_akhir_bulan_dengan_cadangan():
    # 17 Oktober: 15 hari tersisa. Sisa awal hari 700, cadangan 10% = 100, jadi jatah (700 - 100) / 15 = 40 per hari.
    j = kuota_tavily.hitung_jatah({"batas": 1000, "terpakai": 312}, 300, date(2026, 10, 17))
    assert (j["hari_tersisa"], j["jatah_harian"], j["terpakai_hari_ini"], j["sisa_jatah"], j["sisa_bulan"]) == (15, 40, 12, 28, 688)
    assert kuota_tavily.hitung_jatah({"batas": 1000, "terpakai": 950}, 950, date(2026, 10, 31))["jatah_harian"] == 0


def test_beberapa_proses_sehari_berbagi_jatah_dan_kuota_baru_bulan_berikutnya():
    db = DBTiruan()
    hari = date(2026, 10, 17)
    j = kuota_tavily.siapkan(sisihkan=6, db=db, ambil=_usage(300), hari=hari)
    assert j["jatah_harian"] == 40 and kuota_tavily.ANGGARAN.sisa == 34  # 6 kredit disisakan untuk berita lokal
    # proses kedua hari yang sama: pemakaian dihitung dari angka awal hari yang tersimpan
    j = kuota_tavily.siapkan(db=db, ambil=_usage(330), hari=hari)
    assert j["terpakai_hari_ini"] == 30 and kuota_tavily.ANGGARAN.sisa == 10
    assert db.data["lbp_status"]["kuota_tavily"]["awal_hari"] == 300
    # hari berikutnya mulai dari angka baru
    j = kuota_tavily.siapkan(db=db, ambil=_usage(345), hari=date(2026, 10, 18))
    assert j["terpakai_hari_ini"] == 0 and j["jatah_harian"] == 39
    # permintaan dari admin boleh melewati jatah harian, tetapi tidak menyentuh cadangan bulanan
    kuota_tavily.siapkan(manual=True, db=db, ambil=_usage(880), hari=date(2026, 10, 18))
    assert kuota_tavily.ANGGARAN.sisa == 20
    kuota_tavily.siapkan(manual=True, db=db, ambil=_usage(950), hari=date(2026, 10, 18))
    assert kuota_tavily.ANGGARAN.sisa == 0


def test_tanpa_kunci_atau_sisa_tidak_terbaca_pencarian_tidak_dibatasi(monkeypatch):
    def rusak(url, kunci):
        raise OSError("jaringan")
    assert kuota_tavily.siapkan(db=DBTiruan(), ambil=rusak) is None and kuota_tavily.ANGGARAN.sisa is None
    monkeypatch.delenv("TAVILY_API_KEY")
    assert kuota_tavily.siapkan(db=DBTiruan(), ambil=_usage(0)) is None and kuota_tavily.ANGGARAN.pakai(99)


def test_pencarian_berhenti_saat_jatah_habis():
    dipanggil = []

    def kirim(url, header, isi):
        dipanggil.append(isi["query"])
        return {"results": [{"url": f"https://contoh.go.id/{len(dipanggil)}", "title": "x", "content": "y"}]}

    kuota_tavily.ANGGARAN.atur(2)
    hasil, galat = pencari_data.cari_web(pencari_data.kueri_web("cabai", "Oktober 2026", "harga", "Bengkulu Tengah"), kirim)
    assert len(dipanggil) == 2 and len(hasil) == 2 and "jatah" in galat[-1]
    kuota_tavily.ANGGARAN.atur(1)
    _, galat = berita.cari_tavily(["a", "b", "c"], 14, kirim)
    assert dipanggil[-1] == "a" and "Google Berita" in galat[-1] and "2 kueri" in galat[-1]

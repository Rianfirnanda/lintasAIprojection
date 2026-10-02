"""AI Data Finder: jadwal harian bergilir, log proses, dan hasil dari browser admin."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from pipeline import __main__ as m
from pipeline import firestore_sinkron as fs
from pipeline import pencari_data

from .test_firestore_sinkron import DBTiruan


def _catatan(komoditas):
    return {"waktu": "2026-10-02T09:00:00+07:00", "permintaan": {"komoditas": komoditas}, "penyedia": "gemini",
            "punya_pencarian_web": True, "pencarian_web": "Tavily, 5 hasil", "penyedia_dilewati": [], "model": "g",
            "request_id": None, "hasil": {"kandidat": [], "tidak_ditemukan": [], "catatan": ""}, "url_hasil_pencarian": [],
            "log": [{"waktu": "09.00.01", "teks": "Pencarian web Tavily: 5 halaman ditemukan.", "jenis": "info"}]}


def test_ai_harian_bergilir_dan_tercatat(akar_sementara, monkeypatch):
    db = DBTiruan()
    monkeypatch.setattr(fs, "aktif", lambda: True)
    monkeypatch.setattr(fs, "klien", lambda: db)
    monkeypatch.setattr(fs, "pasang_rahasia_dari_firestore", lambda akar: [])
    dicari = []

    def cari(konf, komoditas, periode, *a, **k):
        dicari.append((komoditas, periode))
        if komoditas == "Bawang Merah":
            e = RuntimeError("tidak ada penyedia AI yang dapat dipakai")
            e.langkah = [{"waktu": "", "teks": "gemini dilewati", "jenis": "peringatan"}]
            raise e
        return _catatan(komoditas)

    monkeypatch.setattr(pencari_data, "cari", cari)

    class Jam(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 2, 2, 0, tzinfo=timezone.utc)  # 09.00 WIB

    import datetime as modul_dt
    monkeypatch.setattr(modul_dt, "datetime", Jam)
    pesan = m._ai_harian(akar_sementara)
    assert len(dicari) == 2 and all(p == "Oktober 2026" for _, p in dicari)
    status = db.data["lbp_status"]["ai_harian"]
    assert status["tanggal"] == "2026-10-02" and status["indeks"] == 2 and status["komoditas"] == [k for k, _ in dicari]
    log = list(db.data["lbp_log_ai"].values())
    assert {x["sumber"] for x in log} == {"harian"} and len(log) == 2
    # Hari yang sama tidak diulang
    assert m._ai_harian(akar_sementara) == [] and len(dicari) == 2
    assert any("kandidat" in p for p in pesan)


def test_hasil_ai_dari_situs_dicek_dan_disimpan(akar_sementara, monkeypatch):
    monkeypatch.setattr(pencari_data, "cek_url", lambda url: (True, "HTTP 200"))
    hasil = {"kandidat": [{"nama_sumber": "PIHPS", "url": "https://www.bi.go.id/hargapangan"},
                          {"nama_sumber": "Karangan", "url": "https://palsu.example/x"}]}
    n = m._kandidat_dari_situs(akar_sementara, [{
        "permintaan": {"komoditas": "cabai", "periode": "Oktober 2026"}, "penyedia": "gemini", "model": "g",
        "punya_pencarian_web": True, "pencarian_web": "Tavily, 2 hasil", "url_pencarian": ["https://www.bi.go.id/hargapangan"],
        "hasil": json.dumps(hasil), "oleh_email": "adm@contoh.go.id", "diperbarui": datetime(2026, 10, 2, tzinfo=timezone.utc)}])
    assert n == 1
    data = json.loads((akar_sementara / "data/sumber/kandidat_ai.json").read_text())
    k = data["pencarian"][0]["hasil"]["kandidat"]
    assert [x["url_ada_di_hasil_pencarian"] for x in k] == [True, False]
    assert all(x["url_dapat_diakses"] is True for x in k) and data["pencarian"][0]["dari"] == "situs"

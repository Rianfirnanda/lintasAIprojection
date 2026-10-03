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
    monkeypatch.setattr(pencari_data, "periksa_url", lambda url: {
        "url_dapat_diakses": True, "keterangan_url": "HTTP 200", "url_diakses": "2026-10-02T09:00:00+07:00",
        "url_sha256": "ab" * 32, "url_ukuran_byte": 1234, "url_sidik_terpotong": False})
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
    # bukti akses untuk verifikasi manusia: waktu akses, sidik jari isi halaman, dan ID untuk tombol terima/tolak
    assert k[0]["url_sha256"] == "ab" * 32 and k[0]["url_diakses"].startswith("2026-10-02") and k[0]["url_ukuran_byte"] == 1234
    assert len({x["id"] for x in k}) == 2 and all(len(x["id"]) == 12 for x in k)


def test_keputusan_analis_menandai_kandidat_dan_masuk_daftar_sumber(tmp_path):
    from pipeline import proses

    data = {"pencarian": [{"waktu": "2026-10-02T09:00:00+07:00", "hasil": {"kandidat": [
        {"nama_sumber": "Disperindag", "url": "https://disperindag.bengkuluprov.go.id/komoditas", "metode_akses": "web",
         "frekuensi_pembaruan": "harian", "lisensi_atau_ketentuan": "terbuka"},
        {"nama_sumber": "Karangan", "url": "https://palsu.example/x"},
        {"nama_sumber": "Belum dinilai", "url": "https://lain.go.id"}]}}]}
    pencari_data.beri_id(data)
    a, b, _ = (k["id"] for k in data["pencarian"][0]["hasil"]["kandidat"])
    folder = tmp_path / "data/sumber/keputusan"
    folder.mkdir(parents=True)
    # baris kedua untuk kandidat yang sama: keputusan terbaru yang berlaku
    (folder / "situs.csv").write_text(
        "id_kandidat,keputusan,alasan,penilai,tanggal,url,nama_sumber,pencarian\n"
        f"{a},tolak,salah wilayah,Analis 1,2026-10-02,,,\n"
        f"{a},terima,data resmi provinsi,Analis 1,2026-10-03,,,\n"
        f"{b},tolak,alamat karangan AI,Analis 2,2026-10-03,,,\n", encoding="utf-8")

    keputusan = proses.baca_keputusan_sumber(tmp_path)
    diterima = proses.terapkan_keputusan_sumber(data, keputusan)
    k = data["pencarian"][0]["hasil"]["kandidat"]
    assert [x.get("status_verifikasi") for x in k] == ["diterima", "ditolak", None]
    assert k[1]["keputusan"] == {"keputusan": "tolak", "alasan": "alamat karangan AI", "penilai": "Analis 2", "tanggal": "2026-10-03"}
    assert len(diterima) == 1
    s = diterima[0]
    assert s["kode"] == f"AI-{a[:6].upper()}" and s["status"] == "diterima" and s["kelompok"] == "AI_FINDER"
    assert s["url"].startswith("https://disperindag") and s["frekuensi"] == "harian" and "Analis 1" in s["catatan"]

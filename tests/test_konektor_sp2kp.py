"""Konektor SP2KP Kemendag (bentuk jawaban diambil dari jawaban asli export-area-daily-json, Oktober 2026)."""

from __future__ import annotations

import csv

from pipeline import konektor_sp2kp, konfigurasi, masukan

from .conftest import HARI_INI


def _jawaban(pasar_id: str) -> dict:
    tambah = 0 if pasar_id == "117" else 500
    return {"status": "success", "data": [
        {"daftarHarga": [{"date": "2026-09-24", "harga": 14375 + tambah}, {"date": "2026-09-25", "harga": 14400 + tambah},
                         {"date": "2026-09-28", "harga": None}, {"date": "2026-09-29", "harga": 0}],
         "kuantitas": 1, "order": 101, "satuan": "kg", "variant": "Beras Medium", "variant_id": 52},
        {"daftarHarga": [{"date": "2026-09-24", "harga": 60000}],
         "kuantitas": 1, "order": 301, "satuan": "kg", "variant": "Cabai Merah Keriting", "variant_id": 61},
    ]}


def _pengirim(panggil):
    def kirim(url, data):
        panggil.append(data)
        return _jawaban(data["pasar_id"])
    return kirim


def test_ubah_respons_lewati_harga_kosong():
    b = konektor_sp2kp.ubah_respons(_jawaban("117"), "1709", 117)
    assert [(x["tanggal"], x["variant_id"], x["harga"]) for x in b] == [
        ("2026-09-24", "52", "14375"), ("2026-09-25", "52", "14400"), ("2026-09-24", "61", "60000")]
    assert all(x["kode_wilayah"] == "1709" and x["pasar_id"] == "117" for x in b)


def test_perbarui_simpan_mentah_dan_tambah_peta_baru(konf):
    panggil = []
    hasil = konektor_sp2kp.perbarui(konf, hari_riwayat=40, pengirim=_pengirim(panggil), tidur=lambda s: None)
    assert hasil["galat"] == [] and hasil["varian_baru"] == ["52", "61"]
    # tiga pasar, rentang 40 hari dibagi per 30 hari = 2 permintaan per pasar
    assert len(panggil) == 6 and {p["pasar_id"] for p in panggil} == {"117", "116", "118"}
    assert all(p["level"] == "3" and p["kode_provinsi"] == "17" for p in panggil)
    mentah = list(csv.DictReader((konf.akar / "data/mentah/sp2kp/harian_2026.csv").open(encoding="utf-8")))
    assert len(mentah) == 9  # 3 baris x 3 pasar; permintaan berulang tidak menggandakan baris
    peta = konektor_sp2kp.baca_peta(konf.akar / "config/peta_varian_sp2kp.csv")
    assert peta["52"]["status"] == "baru" and peta["52"]["variant_sp2kp"] == "Beras Medium"


def test_ke_harga_hanya_pemetaan_disetujui_dan_lolos_pembacaan(konf):
    konektor_sp2kp.perbarui(konf, hari_riwayat=10, pengirim=_pengirim([]), tidur=lambda s: None)
    path = konf.akar / "config/peta_varian_sp2kp.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=konektor_sp2kp.KOLOM_PETA, lineterminator="\n")
        w.writeheader()
        w.writerow({"variant_id": "52", "variant_sp2kp": "Beras Medium", "satuan_sp2kp": "kg", "kode_varian": "BRS03", "faktor": "1",
                    "status": "setuju", "catatan": ""})
        w.writerow({"variant_id": "61", "variant_sp2kp": "Cabai Merah Keriting", "satuan_sp2kp": "kg", "kode_varian": "CMR02",
                    "faktor": "1", "status": "tinjau", "catatan": ""})
    hasil = konektor_sp2kp.ke_harga(konf)
    assert hasil["galat"] == [] and hasil["berkas"] == {"sp2kp_2026.csv": 6}
    assert hasil["per_wilayah_varian"] == {"1708:BRS03": 2, "1709:BRS03": 2, "1771:BRS03": 2}
    konf2 = konfigurasi.muat(konf.akar, hari_ini=HARI_INI)
    baca = masukan.baca_semua(konf.akar / "data" / "masuk", konf2, akar_relatif=konf.akar)
    assert baca.penolakan == []
    obs = {(o.kode_pasar, o.tanggal.isoformat()): o.harga for o in baca.observasi}
    assert obs[("PSR01", "2026-09-24")] == 14375 and obs[("PSR92", "2026-09-25")] == 14900
    assert {o.kode_sumber for o in baca.observasi} == {"BD-SP2KP"}
    assert {o.kode_wilayah for o in baca.observasi} == {"1709", "1708", "1771"}


def test_kode_varian_salah_dilaporkan(konf):
    path = konf.akar / "config/peta_varian_sp2kp.csv"
    path.write_text("variant_id,variant_sp2kp,satuan_sp2kp,kode_varian,faktor,status,catatan\n52,Beras Medium,kg,XXX01,1,setuju,\n",
                    encoding="utf-8")
    assert konektor_sp2kp.ke_harga(konf)["galat"]


def test_peta_sungguhan_hanya_merujuk_varian_yang_ada():
    konf = konfigurasi.muat(konektor_sp2kp.Path(__file__).resolve().parent.parent, hari_ini=HARI_INI)
    peta = konektor_sp2kp.baca_peta(konf.akar / "config/peta_varian_sp2kp.csv")
    for v in peta.values():
        assert v["status"] in ("setuju", "tinjau", "tolak", "baru")
        if v["status"] == "setuju":
            assert v["kode_varian"] in konf.varian, v

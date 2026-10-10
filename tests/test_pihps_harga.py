"""PIHPS Provinsi Bengkulu sebagai harga utama sementara: salinan ke berkas harga, mode data asli, dan penanda di dashboard."""

from __future__ import annotations

import csv
import json
import shutil
from datetime import date, timedelta

from pipeline import konfigurasi, masukan, pihps_harga, proses

from .conftest import AKAR, HARI_INI

KOLOM = ["tanggal", "kode_wilayah", "indikator", "nilai", "satuan", "kode_varian", "kode_sumber"]


def _tulis_konteks(akar, tahun, baris):
    p = akar / "data" / "masuk" / "konteks"
    p.mkdir(parents=True, exist_ok=True)
    with (p / f"harga_pihps_{tahun}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(KOLOM)
        w.writerows(baris)


def _baris(awal: date, hari: int, kode: str, dasar: float):
    out = []
    for i in range(hari):
        t = awal + timedelta(days=i)
        if t.weekday() < 5:
            out.append([t.isoformat(), "17", "harga_pihps", dasar + (i % 5) * 100, "Rp", kode, "BD-PIHPS"])
    return out


def test_pasar_pihps_ada_di_konfigurasi_sungguhan():
    konf = konfigurasi.muat(AKAR, hari_ini=HARI_INI)
    assert pihps_harga.KODE_PASAR in konf.pasar and konf.pasar[pihps_harga.KODE_PASAR].kode_wilayah == "17"
    # Sasaran Bengkulu Tengah; Provinsi Bengkulu (PIHPS) hanya cadangan untuk varian yang tidak dicatat pasar Bengkulu Tengah.
    assert konf.wilayah_target == "1709" and konf.wilayah["1709"].peran == "target"
    assert konf.wilayah_cadangan == "17" and konf.wilayah["17"].peran != "target"


def test_salin_ke_harga_per_tahun_diterima_quality_gate(akar_sementara):
    konf = konfigurasi.muat(akar_sementara, hari_ini=HARI_INI)
    _tulis_konteks(akar_sementara, 2025, _baris(date(2025, 12, 1), 31, "BRS03", 13500))
    _tulis_konteks(akar_sementara, 2026, _baris(date(2026, 1, 1), 60, "BRS03", 13800) + [["2026-01-05", "17", "harga_pihps", 1, "Rp", "XXX99", "BD-PIHPS"]])
    hasil = pihps_harga.ke_harga(konf)
    assert set(hasil["berkas"]) == {"pihps_provinsi_2025.csv", "pihps_provinsi_2026.csv"} and hasil["tak_dikenal"] == ["XXX99"]
    harga = akar_sementara / "data/masuk/harga"
    isi = list(csv.DictReader((harga / "pihps_provinsi_2026.csv").open(encoding="utf-8")))
    assert isi[0]["kode_pasar"] == "PHP17" and isi[0]["satuan"] == "kg" and "bukan harga Bengkulu Tengah" in isi[0]["catatan"]
    assert all(r["kode_varian"] == "BRS03" for r in isi)
    # berkas hasil salinan lolos baca masukan biasa tanpa penolakan, dan otomatis mematikan mode demo
    assert masukan.ada_data_harga(akar_sementara / "data" / "masuk")
    baca = masukan.baca_semua(akar_sementara / "data" / "masuk", konf, akar_relatif=akar_sementara)
    assert [x for x in baca.penolakan if "/harga/" in x.berkas] == [] and len(baca.observasi) == sum(hasil["berkas"].values())
    assert all(o.kode_wilayah == "17" and o.kode_sumber == "BD-PIHPS" for o in baca.observasi)


def test_salin_ulang_menghapus_berkas_tahun_yang_hilang_dan_tidak_menggandakan(akar_sementara):
    konf = konfigurasi.muat(akar_sementara, hari_ini=HARI_INI)
    _tulis_konteks(akar_sementara, 2025, _baris(date(2025, 12, 1), 14, "BRS03", 13500))
    pihps_harga.ke_harga(konf)
    n1 = len(list((akar_sementara / "data/masuk/harga").glob("pihps_provinsi_*.csv")))
    pihps_harga.ke_harga(konf)  # dua kali: hasil sama, bukan dobel
    assert len(list((akar_sementara / "data/masuk/harga").glob("pihps_provinsi_*.csv"))) == n1 == 1
    (akar_sementara / "data/masuk/konteks/harga_pihps_2025.csv").unlink()
    assert pihps_harga.ke_harga(konf)["berkas"] == {}
    assert not list((akar_sementara / "data/masuk/harga").glob("pihps_provinsi_*.csv"))


def _tulis_harga_target(akar, kode, awal, hari, dasar):
    """Harga harian Pasar Taba Penanjung (Bengkulu Tengah) dari SP2KP untuk satu varian."""
    p = akar / "data/masuk/harga"
    p.mkdir(parents=True, exist_ok=True)
    with (p / "sp2kp_uji.csv").open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        if f.tell() == 0:
            w.writerow(pihps_harga.KOLOM)
        for i in range(hari):
            t = awal + timedelta(days=i)
            if t.weekday() < 5:
                w.writerow([t.isoformat(), "PSR01", kode, dasar + (i % 4) * 250, "kg", "BD-SP2KP", "", "", "", "", "SP2KP uji"])


def test_dashboard_bengkulu_tengah_dengan_cadangan_provinsi_per_varian(tmp_path):
    """Varian yang punya harga Bengkulu Tengah memakai harga itu; varian yang tidak punya memakai rata-rata Provinsi Bengkulu
    (PIHPS) dengan penanda jelas. Kedua deret tidak disambung."""
    shutil.copytree(AKAR / "config", tmp_path / "config")
    p = tmp_path / "config/pengaturan.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["analisis"]["model_pohon"] = False
    p.write_text(json.dumps(d), encoding="utf-8")
    (tmp_path / "data/masuk/harga").mkdir(parents=True)
    _tulis_konteks(tmp_path, 2026, _baris(date(2026, 4, 1), 180, "BRS03", 13500) + _baris(date(2026, 4, 1), 180, "CRW02", 40000))
    _tulis_harga_target(tmp_path, "CRW02", date(2026, 4, 1), 180, 45000)
    konf = konfigurasi.muat(tmp_path, hari_ini=HARI_INI)
    pihps_harga.ke_harga(konf)
    keluaran = tmp_path / "site/data"
    proses.jalankan(konf, keluaran, sinkron_github=False)
    meta = json.loads((keluaran / "meta.json").read_text(encoding="utf-8"))
    assert meta["mode_demo"] is False and meta["wilayah_target"]["nama"] == "Kabupaten Bengkulu Tengah"
    assert meta["data_sementara"] is None
    assert meta["sumber_seri"]["utama"] == ["CRW02"] and meta["sumber_seri"]["pengganti"] == ["BRS03"]
    crw = json.loads((keluaran / "seri/CRW02.json").read_text(encoding="utf-8"))
    brs = json.loads((keluaran / "seri/BRS03.json").read_text(encoding="utf-8"))
    assert crw["sumber_seri"]["kode_wilayah"] == "1709" and crw["sumber_seri"]["pengganti"] is False
    assert crw["sumber_seri"]["sumber"] == "SP2KP Kemendag" and crw["sumber_seri"]["pasar"] == ["Pasar Taba Penanjung"]
    assert max(x for x in crw["aktual"] if x) >= 45000  # deret Bengkulu Tengah, bukan provinsi
    assert "17" in crw["pembanding"] and "PIHPS" in crw["pembanding"]["17"]["nama"]
    assert brs["sumber_seri"]["kode_wilayah"] == "17" and brs["sumber_seri"]["pengganti"] is True
    assert "belum mencatat" in brs["sumber_seri"]["catatan"]
    analitik = json.loads((keluaran / "analitik.json").read_text(encoding="utf-8"))
    kartu = {v["kode"]: v["kartu_model"] for v in analitik["varian"]}
    assert kartu["BRS03"]["data"]["wilayah"] == "Provinsi Bengkulu"
    assert any("belum mencatat" in b for b in kartu["BRS03"]["keterangan" if "keterangan" in kartu["BRS03"] else "keterbatasan"])
    assert kartu["CRW02"]["data"]["wilayah"] == "Kabupaten Bengkulu Tengah"
    sinyal = json.loads((keluaran / "sinyal.json").read_text(encoding="utf-8"))
    for s_ in sinyal.get("sinyal", []):
        if s_["kode_varian"] == "BRS03":
            assert s_["kode_wilayah"] == "17" and "Bengkulu Tengah" not in s_["judul"]


def test_tidak_ada_penanda_bila_target_adalah_bengkulu_tengah(akar_sementara):
    konf = konfigurasi.muat(akar_sementara, hari_ini=HARI_INI)
    proses.jalankan(konf, akar_sementara / "site/data", mode_demo="ya", sinkron_github=False)  # mode demo
    meta = json.loads((akar_sementara / "site/data/meta.json").read_text(encoding="utf-8"))
    assert meta["data_sementara"] is None and meta["mode_demo"] is True

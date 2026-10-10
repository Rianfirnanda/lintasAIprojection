"""Protokol validasi, proyeksi hari raya, proyeksi periodik, dan bahan Dasbor Analitik."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pytest

from pipeline import analisis, analitik, proyeksi_acara, proyeksi_periodik
from pipeline.konfigurasi import Acara

MULAI = date(2022, 10, 10)  # Senin


def seri_hari_kerja(fungsi, n_hari):
    """Seri harian yang hanya terisi pada hari kerja (seperti PIHPS)."""
    p = {}
    for i in range(n_hari):
        t = MULAI + timedelta(days=i)
        if t.weekday() < 5:
            p[t] = float(fungsi(i))
    return analisis.bentuk_seri(p)


def pengaturan_uji():
    """Pengaturan sungguhan di config/ (horizon 30 hari, interval 80%)."""
    from tests.conftest import AKAR

    return json.loads((AKAR / "config/pengaturan.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- metrik

def test_mase_memakai_skala_per_titik_dan_nol_hanya_bila_tebakan_tepat():
    f, a = np.array([110.0, 120.0]), np.array([100.0, 100.0])
    m = analisis.metrik(f, a, insample_diff=np.array([10.0, 20.0]))
    assert m["mase"] == pytest.approx((10 / 10 + 20 / 20) / 2)
    # harga tidak pernah berubah di data latih (skala 0): MASE hanya terdefinisi bila tebakan tepat
    assert analisis.metrik(np.array([100.0]), np.array([100.0]), insample_diff=np.array([0.0]))["mase"] == 0.0
    assert "mase" not in analisis.metrik(np.array([101.0]), np.array([100.0]), insample_diff=np.array([0.0]))


def test_backtest_menyisihkan_holdout_dan_skala_mase_dari_data_latih():
    s = seri_hari_kerja(lambda i: 1000 + 5 * math.sin(i / 9), 700)
    terisi = analisis.isi_celah(s.nilai, 7)
    geser = 90
    bt = analisis.backtest(s, terisi, "naif", {}, 14, 6, 7, 120, geser_akhir=geser)
    batas = s.tanggal[-1] - timedelta(days=geser)
    assert max(bt.tanggal) <= batas
    assert bt.metrik["mase"] > 0


# ---------------------------------------------------------------- uji Diebold-Mariano

def test_diebold_mariano_mengenali_model_yang_lebih_baik():
    rng = np.random.default_rng(3)
    bagus, buruk = rng.normal(0, 1, 120), rng.normal(0, 3, 120)
    hasil = analisis.uji_diebold_mariano(bagus, buruk, horizon=7)
    assert hasil["statistik"] < 0 and hasil["p"] < 0.01
    serupa = analisis.uji_diebold_mariano(bagus, bagus.copy(), horizon=7)
    assert serupa["statistik"] is None and serupa["p"] is None  # selisih nol di mana-mana: uji tidak berlaku
    assert analisis.uji_diebold_mariano(bagus[:5], buruk[:5], 7)["p"] is None  # sampel terlalu sedikit


# ---------------------------------------------------------------- diagnostik dan kelengkapan

def test_kelengkapan_hanya_menghitung_hari_pencatatan():
    s = seri_hari_kerja(lambda i: 100, 400)
    assert analisis.kelengkapan_seri(s, [0, 1, 2, 3, 4]) == 100.0
    nilai = s.nilai.copy()
    idx = [i for i, t in enumerate(s.tanggal) if t.weekday() == 0][-10:]
    nilai[idx] = np.nan  # 10 hari Senin hilang
    s2 = analisis.SeriHarian(tanggal=s.tanggal, nilai=nilai)
    hasil = analisis.kelengkapan_seri(s2, [0, 1, 2, 3, 4], jendela=365)
    assert 95 < hasil < 100


def test_diagnostik_membedakan_derau_stasioner_dan_jalan_acak():
    rng = np.random.default_rng(4)
    derau = 100 * np.exp(rng.normal(0, 0.02, 500))
    jalan = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 500)))
    sd = analisis.diagnostik_deret(analisis.SeriHarian(tanggal=[MULAI + timedelta(days=i) for i in range(500)], nilai=derau), derau)
    sj = analisis.diagnostik_deret(analisis.SeriHarian(tanggal=[MULAI + timedelta(days=i) for i in range(500)], nilai=jalan), jalan)
    assert sd["adf_p"] < 0.05 and sd["stasioner"] is True
    assert sj["stasioner"] is False
    pendek = np.array([100.0] * 30)
    assert analisis.diagnostik_deret(analisis.SeriHarian(tanggal=[MULAI + timedelta(days=i) for i in range(30)], nilai=pendek), pendek)["adf_p"] is None


# ---------------------------------------------------------------- status valid / eksperimen

def holdout_baik(**ubah):
    h = {"smape": 3.0, "bias_persen": 1.0, "cakupan_persen": 80.0, "mase": 0.7, "akurasi_arah": 70.0}
    h.update(ubah)
    return h


def test_status_valid_bila_semua_syarat_lolos():
    v = analisis.pengaturan_validasi({})
    hasil = analisis.nilai_validasi("pokok", v, 900, 98.0, holdout_baik())
    assert hasil["status"] == "valid" and not hasil["gagal"]
    assert hasil["kelas_volatilitas"] == "rendah" and hasil["ambang_smape"] == 5.0


@pytest.mark.parametrize("ubah,gagal", [
    ({"smape": 6.0}, "sMAPE holdout"),
    ({"bias_persen": -3.5}, "Bias holdout"),  # kelas rendah: batas 3%
    ({"cakupan_persen": 100.0}, "Cakupan interval 80%"),
    ({"cakupan_persen": 60.0}, "Cakupan interval 80%"),
    ({"mase": 1.2}, "MASE holdout"),
])
def test_status_eksperimen_per_syarat(ubah, gagal):
    v = analisis.pengaturan_validasi({})
    hasil = analisis.nilai_validasi("pokok", v, 900, 98.0, holdout_baik(**ubah))
    assert hasil["status"] == "eksperimen" and gagal in hasil["gagal"]


def test_syarat_riwayat_kelengkapan_dan_akurasi_arah_volatil():
    v = analisis.pengaturan_validasi({})
    assert "Riwayat harga" in analisis.nilai_validasi("pokok", v, 400, 98.0, holdout_baik())["gagal"]
    assert "Kelengkapan data" in analisis.nilai_validasi("pokok", v, 900, 90.0, holdout_baik())["gagal"]
    volatil = analisis.nilai_validasi("volatil", v, 900, 98.0, holdout_baik(smape=12.0, bias_persen=4.0, akurasi_arah=40.0))
    assert volatil["status"] == "eksperimen" and volatil["gagal"] == ["Akurasi arah"]  # sMAPE 12 <= 15 dan bias 4 <= 5 lolos
    assert analisis.nilai_validasi("volatil", v, 900, 98.0, holdout_baik(smape=12.0, bias_persen=4.0, akurasi_arah=65.0))["status"] == "valid"
    # bias 4% melewati batas kelas rendah (3%) tetapi lolos kelas sedang (5%)
    assert "Bias holdout" in analisis.nilai_validasi("pokok", v, 900, 98.0, holdout_baik(bias_persen=4.0))["gagal"]
    assert analisis.nilai_validasi("protein", v, 900, 98.0, holdout_baik(smape=8.0, bias_persen=4.0))["status"] == "valid"


def test_status_tanpa_holdout_selalu_eksperimen():
    v = analisis.pengaturan_validasi({})
    hasil = analisis.nilai_validasi("pokok", v, 900, 98.0, None)
    assert hasil["status"] == "eksperimen" and "Holdout 90 hari" in hasil["gagal"]


def test_analisis_varian_menghasilkan_holdout_validasi_dan_proyeksi_30_hari():
    rng = np.random.default_rng(5)
    s = seri_hari_kerja(lambda i: 20000 * math.exp(0.0002 * i + rng.normal(0, 0.004)), 1100)
    hv = analisis.analisis_varian(s, "pokok", [], pengaturan_uji())
    assert hv.holdout is not None and hv.holdout["hari"] == 90 and hv.holdout["jumlah_origin"] >= 3
    assert set(hv.holdout["per_horizon"]) == {"7", "14", "30"}
    assert hv.holdout["titik_h7"] and {"tanggal", "aktual", "prediksi"} <= set(hv.holdout["titik_h7"][0])
    assert hv.validasi["status"] in {"valid", "eksperimen"} and hv.validasi["syarat"]
    assert len(hv.proyeksi) == 30 and all(p["bawah"] <= p["prediksi"] <= p["atas"] for p in hv.proyeksi)
    assert hv.kelengkapan_persen > 95 and hv.jumlah_obs > 700
    assert hv.diagnostik["adf_p"] is not None


def test_analisis_varian_riwayat_pendek_tanpa_holdout_dan_eksperimen():
    s = seri_hari_kerja(lambda i: 20000 + i, 200)
    hv = analisis.analisis_varian(s, "pokok", [], pengaturan_uji())
    assert hv.holdout is None and hv.validasi["status"] == "eksperimen"


# ---------------------------------------------------------------- proyeksi hari raya

def konf_palsu(acara, hari_ini=date(2026, 10, 10)):
    varian = {"V1": SimpleNamespace(kelompok="volatil", nama="Varian satu")}
    return SimpleNamespace(hari_raya=lambda: [a for a in acara if a.jenis == "hari_raya"], pengaturan=pengaturan_uji(), varian=varian,
                           hari_ini=hari_ini)


def test_jenis_acara_menyatukan_tahun():
    assert proyeksi_acara.jenis_acara("Idul Fitri 1446 H") == "Idul Fitri"
    assert proyeksi_acara.jenis_acara("Idul Adha 1447 H") == "Idul Adha"
    assert proyeksi_acara.jenis_acara("Hari Raya Natal") == "Natal"
    assert proyeksi_acara.kode_offset(-7) == "H-7" and proyeksi_acara.kode_offset(14) == "H+14"


def test_rasio_hari_raya_dipelajari_dari_hari_raya_sejenis():
    # harga naik 10% dalam 7 hari menjelang tiap Natal; datar di waktu lain
    natal = [date(2022, 12, 25), date(2023, 12, 25), date(2024, 12, 25), date(2025, 12, 25)]

    def harga(i):
        t = MULAI + timedelta(days=i)
        for n in natal:
            k = (t - n).days
            if -7 <= k <= 0:
                return 10000 * (1 + 0.10 * (k + 7) / 7)
        return 10000

    s = seri_hari_kerja(harga, 1300)
    acara = [Acara(n, "Hari Raya Natal", "hari_raya", "pasti") for n in natal] + [Acara(date(2026, 12, 25), "Hari Raya Natal", "hari_raya", "pasti")]
    h = proyeksi_acara._Harga(s)
    kejadian = [e for n in natal if (e := proyeksi_acara._kumpul(h, n, -7, date(2026, 10, 9)))]
    assert len(kejadian) == 4
    ev = proyeksi_acara.evaluasi_offset(kejadian, 0.8)
    assert ev["n_acara"] == 4 and ev["perbaikan_vs_naif_persen"] > 90 and ev["smape"] < 1.5
    v = analisis.pengaturan_validasi({})
    st = proyeksi_acara.status_evaluasi(ev, "volatil", v)
    # hanya 4 hari raya sejenis: cakupan interval belum bisa dinilai, jadi tetap Eksperimen
    assert st["status"] == "eksperimen" and not st["gagal"] and "Cakupan interval 80%" in st["belum_dinilai"][0]
    # kurang dari 3 hari raya: tidak diuji
    assert proyeksi_acara.evaluasi_offset(kejadian[:2], 0.8) is None
    assert proyeksi_acara.status_evaluasi(None, "volatil", v)["status"] == "eksperimen"


def test_proyeksi_acara_baru_dibuat_setelah_titik_asal_tiba():
    natal = [date(2022, 12, 25), date(2023, 12, 25), date(2024, 12, 25), date(2025, 12, 25)]
    s0 = seri_hari_kerja(lambda i: 10000, 1400)
    acara = [Acara(n, "Hari Raya Natal", "hari_raya", "pasti") for n in natal + [date(2026, 12, 25)]]
    hv = {"V1": SimpleNamespace(seri=s0)}
    konf = konf_palsu(acara)
    # data baru sampai Oktober 2026: Natal 2026 belum dimulai (titik asal H-7 = 18 Des)
    out = proyeksi_acara.bentuk(konf, hv, date(2026, 10, 9))
    natal26 = next(a for a in out["acara"] if a["tanggal"] == "2026-12-25")
    assert natal26["fase"] == "belum_dimulai" and natal26["varian"] == [] and natal26["proyeksi_mulai"] == "2026-12-18"
    assert len(out["evaluasi"]) == 1  # satu varian x satu jenis hari raya (Natal)
    # data sudah sampai 20 Des 2026: titik asal H-7 tiba, H-3 belum
    s1 = seri_hari_kerja(lambda i: 10000, 1530)
    out2 = proyeksi_acara.bentuk(konf, {"V1": SimpleNamespace(seri=s1)}, date(2026, 12, 20))
    natal26 = next(a for a in out2["acara"] if a["tanggal"] == "2026-12-25")
    assert natal26["fase"] == "pra"
    baris = natal26["varian"][0]["baris"]
    assert [b["kode"] for b in baris] == ["H-7"] and baris[0]["prediksi"] == 10000 and baris[0]["bawah"] <= 10000 <= baris[0]["atas"]


# ---------------------------------------------------------------- proyeksi periodik

def test_tambah_bulan_dan_rata_bulanan():
    assert proyeksi_periodik.tambah_bulan(2026, 11, 3) == (2027, 2)
    assert proyeksi_periodik.tambah_bulan(2026, 1, -1) == (2025, 12)
    s = seri_hari_kerja(lambda i: 100, 400)
    bulan, y = proyeksi_periodik.rata_bulanan(s, date(2023, 11, 15))
    assert bulan[-1] == (2023, 10) and (2023, 11) not in bulan  # bulan berjalan tidak ikut
    assert all(v == 100.0 for v in y)


def test_periodik_menunggu_data_bila_riwayat_kurang_dari_syarat():
    s = seri_hari_kerja(lambda i: 100 + i * 0.01, 1500)  # sekitar 49 bulan
    konf = konf_palsu([])
    konf.varian = {"V1": SimpleNamespace(kelompok="pokok")}
    out = proyeksi_periodik.bentuk(konf, {"V1": SimpleNamespace(seri=s)}, date(2026, 11, 20))
    p = out["periode"]
    assert p["triwulanan"]["tersedia"] and p["semesteran"]["tersedia"]
    assert p["tahunan"]["tersedia"] is False and "60 bulan" in p["tahunan"]["alasan"] and p["tahunan"]["varian"] == []
    tw = p["triwulanan"]["varian"][0]
    assert tw["rendah"][0] <= tw["dasar"][0] <= tw["tinggi"][0]
    assert len(p["triwulanan"]["bulan_target"]) == 3 and len(p["semesteran"]["bulan_target"]) == 6
    assert tw["status"] in {"valid", "eksperimen"} and tw["rata_periode"]["rendah"] <= tw["rata_periode"]["tinggi"]


def test_periodik_tahunan_tersedia_setelah_lima_tahun():
    rng = np.random.default_rng(6)
    s = seri_hari_kerja(lambda i: 20000 * math.exp(0.0001 * i + 0.03 * math.sin(2 * math.pi * i / 365) + rng.normal(0, 0.003)), 1900)
    konf = konf_palsu([])
    konf.varian = {"V1": SimpleNamespace(kelompok="pokok")}
    out = proyeksi_periodik.bentuk(konf, {"V1": SimpleNamespace(seri=s)}, date(2027, 12, 1))
    t = out["periode"]["tahunan"]
    assert t["tersedia"] and len(t["bulan_target"]) == 12 and len(t["varian"][0]["dasar"]) == 12


# ---------------------------------------------------------------- bahan dasbor

def test_kepercayaan_dan_rekomendasi_netral():
    assert analitik.kepercayaan({"status": "valid"}) == "tinggi"
    assert analitik.kepercayaan({"status": "eksperimen", "gagal": ["Bias holdout"], "belum_dinilai": []}) == "sedang"
    assert analitik.kepercayaan({"status": "eksperimen", "gagal": ["a", "b"], "belum_dinilai": []}) == "rendah"
    assert analitik.kepercayaan({}) == "rendah"
    pr = {"30": {"perubahan_persen": 6.0, "bawah": 10000, "atas": 12000}}
    teks = analitik.rekomendasi_netral("Cabai", 11000, SimpleNamespace(), pr, "eksperimen")
    assert "Eksperimen" in teks and "naik 6.0%" in teks
    assert "stabil" in analitik.rekomendasi_netral("Beras", 15000, SimpleNamespace(), {"30": {"perubahan_persen": 0.2, "bawah": 1, "atas": 2}}, "valid")
    assert "belum dapat disusun" in analitik.rekomendasi_netral("X", None, SimpleNamespace(), {}, "valid")


def test_status_audit_dan_rekomendasi_netral_umum():
    kpi = {"kesegaran": "segar", "ditolak": 0, "varian_eksperimen": 0, "perlu_validasi": 0, "varian_berdata": 21}
    assert analitik.status_audit(kpi)["status"] == "HIJAU"
    assert analitik.status_audit({**kpi, "varian_eksperimen": 3, "perlu_validasi": 2})["status"] == "KUNING"
    assert analitik.status_audit({**kpi, "kesegaran": "terlambat"})["status"] == "MERAH"
    varian = [{"nama": "Cabai", "perubahan_30h_persen": -12.0}, {"nama": "Beras", "perubahan_30h_persen": 0.0}]
    r = analitik.rekomendasi_umum(varian, {**kpi, "varian_eksperimen": 2}, None)
    assert [x["warna"] for x in r] == ["hijau", "biru", "oranye"]
    assert "Cabai -12,0%" in r[0]["isi"] and "2 dari 21" in r[1]["isi"]
    assert "stabil" in analitik.rekomendasi_umum([{"nama": "Beras", "perubahan_30h_persen": 0.1}], kpi, None)[0]["isi"]


def test_hash_json_stabil_terhadap_urutan_kunci():
    assert analitik.hash_json({"a": 1, "b": [1, 2]}) == analitik.hash_json({"b": [1, 2], "a": 1})
    assert analitik.hash_json({"a": 1}) != analitik.hash_json({"a": 2})


def test_keluaran_pipeline_memuat_analitik_acara_dan_periodik(tmp_path):
    from pipeline import konfigurasi, proses
    from tests.conftest import HARI_INI, salin_config

    salin_config(tmp_path / "config")
    (tmp_path / "data/masuk/harga").mkdir(parents=True)
    # harga PIHPS Kota Bengkulu (konteks) harus muncul sebagai pembanding wilayah
    (tmp_path / "data/masuk/konteks").mkdir(parents=True)
    (tmp_path / "data/masuk/konteks/pihps_kota_2026.csv").write_text(
        "tanggal,kode_wilayah,indikator,nilai,satuan,kode_varian,kode_sumber\n"
        "2026-09-28,1771,harga_pihps,65000,Rp,CRW02,BD-PIHPS\n2026-09-29,1771,harga_pihps,66000,Rp,CRW02,BD-PIHPS\n", encoding="utf-8")
    konf = konfigurasi.muat(tmp_path, hari_ini=HARI_INI)
    proses.jalankan(konf, tmp_path / "site/data", sinkron_github=False)
    d = tmp_path / "site/data"
    seri = json.loads((d / "seri/CRW02.json").read_text(encoding="utf-8"))
    assert seri["pembanding"]["PIHPS-1771"]["nama"] == "Kota Bengkulu (PIHPS BI)" and 66000 in seri["pembanding"]["PIHPS-1771"]["nilai"]
    a = json.loads((d / "analitik.json").read_text(encoding="utf-8"))
    assert len(a["varian"]) == 21 and a["horizon"] == [7, 14, 30] and a["kpi"]["varian_berdata"] == 21
    v = a["varian"][0]
    assert set(v["proyeksi"]) == {"7", "14", "30"} and v["status"] in {"valid", "eksperimen"} and v["rekomendasi"]
    assert a["kpi"]["skor_konsensus"] is None or a["kpi"]["skor_konsensus"] >= 0
    assert len(a["garis_data"]["versi_data"]) == 64 and len(a["garis_data"]["versi_konfigurasi"]) == 64
    assert a["garis_data"]["berkas_mentah"] and "sha256" in a["garis_data"]["berkas_mentah"][0]
    assert a["kpi"]["varian_valid"] + a["kpi"]["varian_eksperimen"] == 21
    assert "1771" in a["pembanding_wilayah"]["tersedia"]
    # bahan untuk Dashboard Internal BPS
    assert a["wilayah_proyek"]["sasaran"] == "Bengkulu Tengah" and "Kepahiang" in a["wilayah_proyek"]["pembanding"]
    assert a["audit"]["status"] in {"HIJAU", "KUNING", "MERAH"} and len(a["rekomendasi_umum"]) == 3
    assert a["sumber_nama"] and sum(a["model_dipakai"].values()) == 21
    assert all(0 <= x["syarat_lolos"] <= x["syarat_total"] for x in a["varian"])
    ac = json.loads((d / "proyeksi_acara.json").read_text(encoding="utf-8"))
    assert ac["tanggal_data"] and ac["evaluasi"] and "metode" in ac["aturan"]
    pe = json.loads((d / "proyeksi_periodik.json").read_text(encoding="utf-8"))
    assert set(pe["periode"]) == {"triwulanan", "semesteran", "tahunan"}
    m = json.loads((d / "model.json").read_text(encoding="utf-8"))
    assert "validasi" in m["per_varian"][0] and "varian_valid" in m["ringkasan"]

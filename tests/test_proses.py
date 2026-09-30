"""Uji end-to-end: pipeline lengkap dalam mode demo dan mode data nyata."""

import json
from datetime import date, timedelta

import pytest

from pipeline import proses
from tests.conftest import tulis_csv

BERKAS = ["meta.json", "master.json", "ringkasan.json", "sinyal.json", "kualitas.json", "model.json", "pasar.json", "sumber.json",
          "kinerja.json", "laporan.json"]


@pytest.fixture(scope="module")
def keluaran_demo(tmp_path_factory):
    import shutil
    from pipeline import konfigurasi
    from tests.conftest import AKAR, HARI_INI

    akar = tmp_path_factory.mktemp("repo")
    shutil.copytree(AKAR / "config", akar / "config")
    (akar / "data/masuk/harga").mkdir(parents=True)
    konf = konfigurasi.muat(akar, hari_ini=HARI_INI)
    keluaran = akar / "site/data"
    ringkas = proses.jalankan(konf, keluaran, sinkron_github=False)
    return keluaran, ringkas


def baca(keluaran, nama):
    return json.loads((keluaran / nama).read_text(encoding="utf-8"))


def test_demo_menghasilkan_semua_berkas(keluaran_demo):
    keluaran, ringkas = keluaran_demo
    for nama in BERKAS:
        assert (keluaran / nama).exists(), nama
    assert len(list((keluaran / "seri").glob("*.json"))) == 21
    assert (keluaran / "unduh/harga_harian.csv").exists()
    meta = baca(keluaran, "meta.json")
    assert meta["mode_demo"] is True and meta["tanggal_data_terakhir"] == "2026-09-29"


def test_demo_kpi_dan_evaluasi_masuk_akal(keluaran_demo):
    keluaran, ringkas = keluaran_demo
    kpi = ringkas["kpi"]
    assert (kpi["jumlah_komoditas"], kpi["jumlah_varian"], kpi["varian_berdata"]) == (10, 21, 21)
    assert kpi["kelengkapan_persen"] > 80
    ev = ringkas["evaluasi_anomali"]
    assert ev["precision"] > 0.4 and ev["recall"] > 0.4  # detektor harus menemukan sebagian besar gejolak sintetis
    model = baca(keluaran, "model.json")
    assert model["ringkasan"]["lolos_bias"] >= 18
    assert model["ringkasan"]["lolos_cakupan"] >= 15


def test_demo_sinyal_aktif_gejolak_cabai(keluaran_demo):
    keluaran, _ = keluaran_demo
    s = baca(keluaran, "sinyal.json")["sinyal"]
    aktif = [x for x in s if x["jenis"] == "anomali_harga" and x["aktif"]]
    assert any(x["kode_varian"] == "CRW02" and x["keparahan"] == "tinggi" for x in aktif)
    assert any(x["jenis"] == "data_terlambat" and x["kode_pasar"] == "PSR02" for x in s)
    assert all(x["status"] == "baru" for x in s)


def test_json_tidak_mengandung_nan(keluaran_demo):
    keluaran, _ = keluaran_demo
    for p in keluaran.rglob("*.json"):
        teks = p.read_text()
        assert "NaN" not in teks and "Infinity" not in teks, p.name


def test_seri_konsisten(keluaran_demo):
    keluaran, _ = keluaran_demo
    s = baca(keluaran, "seri/CRW02.json")
    n = len(s["tanggal"])
    assert len(s["aktual"]) == len(s["baseline"]) == len(s["rata7"]) == n
    assert all(len(p["nilai"]) == n for p in s["pembanding"].values())
    assert len(s["proyeksi"]) == 14
    assert all(p["bawah"] <= p["prediksi"] <= p["atas"] for p in s["proyeksi"])


def test_mode_nyata_dengan_berkas_kecil(konf, akar_sementara):
    baris = ["tanggal,kode_pasar,kode_varian,harga,responden,waktu_input"]
    hari = date(2026, 9, 29)
    for i in range(90, -1, -1):
        t = hari - timedelta(days=i)
        if t.weekday() >= 5:
            continue
        for r in ("R1", "R2"):
            baris.append(f"{t},PSR01,BRS03,{13500 + (i % 5) * 100},{r},{t}T10:00")
            baris.append(f"{t},PSR01,CRW02,{40000 + (i % 7) * 500},{r},{t}T10:00")
    tulis_csv(akar_sementara / "data/masuk/harga/2026_PSR01.csv", "\n".join(baris))
    tulis_csv(akar_sementara / "data/tindak_lanjut/tl.csv", "id_sinyal,status,catatan,petugas,tanggal\nzzz,terverifikasi,,A,2026-09-29")
    keluaran = akar_sementara / "site/data"
    ringkas = proses.jalankan(konf, keluaran, sinkron_github=False)
    meta = baca(keluaran, "meta.json")
    assert meta["mode_demo"] is False
    assert ringkas["kpi"]["varian_berdata"] == 2
    assert sorted(p.stem for p in (keluaran / "seri").glob("*.json")) == ["BRS03", "CRW02"]
    assert baca(keluaran, "model.json")["evaluasi_anomali"]["sumber_label"] == "tindak lanjut analis/TPID"
    kual = baca(keluaran, "kualitas.json")
    assert kual["ringkasan"]["baris_ditolak_skema"] == 0
    assert kual["ketepatan"]["per_pasar"][0]["ketepatan_persen"] == 100.0


def test_demo_kinerja_dan_laporan(keluaran_demo):
    keluaran, ringkas = keluaran_demo
    k = baca(keluaran, "kinerja.json")
    kode = {i["kode"] for i in k["indikator"]}
    assert {"M1", "M2", "A1", "A3", "A6", "L1", "K1", "T1", "T2", "I1", "I2"} <= kode
    assert all(i["status"] in ("memenuhi", "belum_memenuhi", "belum_dapat_dinilai", "diukur_manual") for i in k["indikator"])
    assert k["koreksi_supervisor"]["acuan"] is not None
    lap = baca(keluaran, "laporan.json")
    assert [len(lap[j]) for j in ("mingguan", "bulanan", "triwulanan")] == [8, 6, 4]
    assert lap["bulanan"][0]["kinerja_model"]["ringkasan"]["varian_dinilai"] == 21
    assert "indikator" in lap["triwulanan"][0] and lap["mingguan"][0]["rekomendasi"]
    meta = baca(keluaran, "meta.json")
    assert meta["pesan_notifikasi"] == "notifikasi tidak dikirim dalam mode demo"
    m = baca(keluaran, "model.json")
    assert all(v["status_persetujuan"] in ("disetujui", "menunggu_persetujuan") for v in m["per_varian"])


def test_batas_wilayah_opsional_diterbitkan(konf, akar_sementara):
    keluaran = akar_sementara / "site/data"
    proses.jalankan(konf, keluaran, sinkron_github=False)
    assert baca(keluaran, "meta.json")["batas_wilayah"] is False
    assert not (keluaran / "batas_wilayah.geojson").exists()

    (akar_sementara / "config/batas_wilayah.geojson").write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    proses.jalankan(konf, keluaran, sinkron_github=False)
    assert baca(keluaran, "meta.json")["batas_wilayah"] is True
    assert (keluaran / "batas_wilayah.geojson").exists()

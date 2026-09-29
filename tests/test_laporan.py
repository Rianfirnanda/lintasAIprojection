from datetime import date, timedelta

import pytest

from pipeline import laporan


@pytest.mark.parametrize("jenis,tgl,mulai,akhir,label", [
    ("mingguan", date(2026, 9, 30), date(2026, 9, 28), date(2026, 10, 4), "Minggu ke-40 2026"),
    ("bulanan", date(2026, 2, 10), date(2026, 2, 1), date(2026, 2, 28), "Februari 2026"),
    ("triwulanan", date(2026, 11, 5), date(2026, 10, 1), date(2026, 12, 31), "Triwulan IV 2026"),
    ("triwulanan", date(2026, 1, 5), date(2026, 1, 1), date(2026, 3, 31), "Triwulan I 2026"),
])
def test_periode(jenis, tgl, mulai, akhir, label):
    assert laporan._periode(jenis, tgl) == (mulai, akhir, label)


def test_sebelumnya_dan_tahun_lalu():
    assert laporan._sebelumnya("triwulanan", date(2026, 1, 1))[2] == "Triwulan IV 2025"
    assert laporan._tahun_lalu("bulanan", date(2026, 9, 1))[2] == "September 2025"


def test_bentuk_semua(konf):
    akhir = date(2026, 9, 25)  # Jumat
    harian = {"CRW02": {}, "BRS03": {}}
    for i in range(400):
        t = akhir - timedelta(days=i)
        minggu_ini = t >= date(2026, 9, 21)
        harian["CRW02"][t] = 48000.0 if minggu_ini else 40000.0
        harian["BRS03"][t] = 13500.0
    sinyal = [{"id": "a1", "jenis": "anomali_harga", "keparahan": "tinggi", "status": "baru", "kode_varian": "CRW02",
               "varian": "Cabai Rawit Merah", "judul": "x", "tanggal_mulai": "2026-09-22", "tanggal_terakhir": "2026-09-25",
               "konteks": {"wilayah_pembanding": {"1708": {"wilayah": "Kabupaten Kepahiang", "selisih_persen": 18.0}}}}]
    hasil = laporan.bentuk_semua(konf, harian, {}, sinyal, [], akhir)
    assert [len(hasil[j]) for j in ("mingguan", "bulanan", "triwulanan")] == [8, 6, 4]
    m = hasil["mingguan"][0]
    assert m["label"] == "Minggu ke-39 2026"
    crw = next(v for v in m["varian"] if v["kode"] == "CRW02")
    assert crw["vs_sebelumnya_persen"] == 20.0 and crw["vs_tahun_lalu_persen"] == 20.0
    assert m["indeks_sederhana"] == pytest.approx(round(1.2 ** 0.5 * 100, 2))
    assert m["kenaikan_teratas"] == ["CRW02"] and m["sinyal"][0]["id"] == "a1"
    assert any("Cabai Rawit Merah naik 20,0%" in r and "Kepahiang" in r for r in m["rekomendasi"])
    assert any("belum diverifikasi" in r for r in m["rekomendasi"])
    assert "," in m["ringkasan"][0]  # format angka Indonesia
    assert laporan.bentuk_semua(konf, {}, {}, [], [], None) == {"mingguan": [], "bulanan": [], "triwulanan": []}

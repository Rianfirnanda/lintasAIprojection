"""Kebijakan TPID: rekomendasi dari sinyal, penilaian dampak kebijakan, rapat, dan respons pedagang."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

from pipeline import kebijakan, kinerja

from .conftest import tulis_csv

T0 = date(2026, 9, 1)


def seri(sebelum_awal: float, sebelum: float, sesudah: float) -> dict[date, float]:
    """Harga 14 hari sebelum kebijakan (dua minggu) dan 14 hari sesudahnya."""
    per = {}
    for i in range(14, 7, -1):
        per[T0 - timedelta(days=i)] = sebelum_awal
    for i in range(7, 0, -1):
        per[T0 - timedelta(days=i)] = sebelum
    for i in range(0, 15):
        per[T0 + timedelta(days=i)] = sesudah
    return per


def kbj(**lain):
    return {"id": "k1", "tanggal_mulai": T0.isoformat(), "kode_varian": "CRW02", "tujuan": "menurunkan_harga", **lain}


def test_dampak_berpengaruh_tidak_berpengaruh_dan_netral():
    hari = T0 + timedelta(days=20)
    turun = kebijakan.nilai_dampak(kbj(), {"CRW02": seri(60000, 66000, 60000)}, hari)
    assert turun["status"] == "berpengaruh" and turun["perubahan_persen"] == -9.1
    assert "sesuai tujuan" in turun["keterangan"]
    naik = kebijakan.nilai_dampak(kbj(), {"CRW02": seri(60000, 62000, 68000)}, hari)
    assert naik["status"] == "tidak_berpengaruh"
    # Sebelumnya naik 10% seminggu, sesudahnya hanya naik 1%: kenaikan tertahan.
    tertahan = kebijakan.nilai_dampak(kbj(), {"CRW02": seri(60000, 66000, 66660)}, hari)
    assert tertahan["status"] == "berpengaruh"
    datar = kebijakan.nilai_dampak(kbj(), {"CRW02": seri(60000, 60000, 60500)}, hari)
    assert datar["status"] == "netral"
    # Melindungi petani: harga yang terus jatuh berarti kebijakan belum berpengaruh.
    jatuh = kebijakan.nilai_dampak(kbj(tujuan="menahan_penurunan"), {"CRW02": seri(40000, 36000, 30000)}, hari)
    assert jatuh["status"] == "tidak_berpengaruh"


def test_dampak_menunggu_dan_kurang_data():
    hasil = kebijakan.nilai_dampak(kbj(), {"CRW02": seri(1, 1, 1)}, T0 + timedelta(days=5))
    assert hasil["status"] == "menunggu" and hasil["siap_dinilai"] == "2026-09-15"
    kosong = kebijakan.nilai_dampak(kbj(kode_varian="BRS01"), {"CRW02": seri(1, 1, 1)}, T0 + timedelta(days=30))
    assert kosong["status"] == "belum_dapat_dinilai"


def test_rekomendasi_hanya_sinyal_penting_dan_persetujuan_manusia():
    sinyal = [
        {"id": "a", "jenis": "anomali_harga", "keparahan": "tinggi", "arah": "naik", "aktif": True, "status": "baru",
         "komoditas": "Cabai Rawit", "varian": "Cabai Rawit Merah", "kode_varian": "CRW02", "judul": "naik", "tanggal_terakhir": "2026-09-30"},
        {"id": "b", "jenis": "anomali_harga", "keparahan": "sedang", "arah": "turun", "aktif": True, "status": "baru",
         "komoditas": "Beras", "varian": "Beras I", "kode_varian": "BRS01", "judul": "turun", "tanggal_terakhir": "2026-09-30"},
        {"id": "c", "jenis": "drift", "keparahan": "rendah", "aktif": True, "status": "baru"},
        {"id": "d", "jenis": "anomali_harga", "keparahan": "tinggi", "arah": "naik", "aktif": True, "status": "false_alarm"},
    ]
    rek = kebijakan.rekomendasi(sinyal, {"R-b": {"keputusan": "tolak", "penyetuju": "Kepala"}})
    assert [r["id"] for r in rek] == ["R-a", "R-b"]
    assert rek[0]["risiko_tinggi"] and rek[0]["status"] == "menunggu" and rek[0]["jenis_kebijakan"] == "operasi_pasar"
    assert any("operasi pasar" in l for l in rek[0]["langkah"])
    assert rek[1]["status"] == "ditolak" and rek[1]["jenis_kebijakan"] == "penyerapan_panen"


def test_bentuk_menghitung_rapat_triwulan_dan_dampak(akar_sementara):
    tulis_csv(akar_sementara / "data/kebijakan/situs.csv", f"""
id,tanggal_mulai,tanggal_selesai,jenis,kode_varian,tujuan,uraian,id_rekomendasi,pencatat
k1,{T0},,operasi_pasar,CRW02,menurunkan_harga,Pasar murah,,TPID
""")
    tulis_csv(akar_sementara / "data/rapat/situs.csv", """
id,tanggal,jenis,agenda,keputusan,jumlah_sinyal,peserta,tautan_notulen,pencatat
r1,2026-09-10,rapat_koordinasi,Cabai,Pasar murah,2,BPS,,TPID
r2,2026-06-10,high_level_meeting,Beras,,1,BPS,,TPID
""")
    hasil = kebijakan.bentuk(akar_sementara, [], {"CRW02": seri(60000, 66000, 60000)}, date(2026, 9, 30), {"CRW02": "Cabai Rawit Merah"})
    assert hasil["kebijakan"][0]["dampak"]["status"] == "berpengaruh"
    assert hasil["kebijakan"][0]["nama_varian"] == ["Cabai Rawit Merah"]
    assert hasil["ringkasan"]["rapat_triwulan_ini"] == 1 and hasil["ringkasan"]["rapat_per_triwulan"] == {"2026-T3": 1, "2026-T2": 1}
    assert hasil["ringkasan"]["dampak"]["berpengaruh"] == 1


def test_respons_pedagang_dari_harga_dan_kunjungan_gagal():
    hari = date(2026, 9, 30)
    obs = lambda t, pasar, resp, sumber="PSR-ENUM": SimpleNamespace(tanggal=t, kode_pasar=pasar, responden=resp, petugas="P",  # noqa: E731
                                                                    kode_sumber=sumber)
    observasi = [obs(hari, "PSR01", "R1"), obs(hari, "PSR01", "R1"), obs(hari, "PSR01", "R2"), obs(hari, "PSR02", "R1"),
                 obs(hari, "PSR01", "R3", "BPS-HRG"), obs(hari - timedelta(days=40), "PSR01", "R4")]
    kunjungan = [{"id": "v1", "tanggal": hari.isoformat(), "status": "menolak", "alasan": "takut_pajak"},
                 {"id": "v2", "tanggal": hari.isoformat(), "status": "tidak_ada", "alasan": ""}]
    r = kinerja.respons_pedagang(observasi, kunjungan, hari)
    assert (r["berhasil"], r["menolak"], r["tidak_ada"], r["total"]) == (3, 1, 1, 5)
    assert r["respons_persen"] == 60.0 and r["penolakan_persen"] == 20.0
    assert r["alasan_penolakan"] == {"takut_pajak": 1}
    assert kinerja.respons_pedagang([], [], hari)["respons_persen"] is None

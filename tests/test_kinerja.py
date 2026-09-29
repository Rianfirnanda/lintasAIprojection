from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np

from pipeline import analisis, kinerja, tindak_lanjut
from pipeline.konfigurasi import muat


def test_baca_persetujuan_berlaku_dan_dicabut(tmp_path):
    (tmp_path / "p.csv").write_text(
        "kode_varian,model,keputusan,penyetuju,tanggal,catatan\n"
        "brs03,rata7,setuju,KSK,2026-09-01,\n"
        "CRW02,holt_redam,setuju,KSK,2026-09-01,\n"
        "CRW02,holt_redam,tolak,KSK,2026-09-10,bias tinggi\n"
        "XXX,naif,entah,KSK,2026-09-10,\n", encoding="utf-8")
    p = kinerja.baca_persetujuan(tmp_path)
    assert p["BRS03"]["model"] == "rata7"
    assert p["CRW02"]["model"] is None and len(p["CRW02"]["riwayat"]) == 2
    assert "XXX" not in p


def test_analisis_wajib_persetujuan():
    rng = np.random.default_rng(5)
    nilai = list(1000 * np.exp(0.004 * np.arange(200) + rng.normal(0, 0.002, 200)))
    seri = analisis.bentuk_seri({date(2025, 1, 1) + timedelta(days=i): v for i, v in enumerate(nilai)})
    peng = muat().pengaturan
    bebas = analisis.analisis_varian(seri, "pokok", [], peng)
    assert bebas.model_rekomendasi != "naif" and bebas.status_persetujuan == "menunggu_persetujuan"
    assert bebas.model_terpilih == bebas.model_rekomendasi  # tidak diwajibkan: tetap dipakai, ditandai menunggu
    wajib = analisis.analisis_varian(seri, "pokok", [], peng, wajib_persetujuan=True)
    assert wajib.model_terpilih == "naif" and wajib.catatan
    setuju = analisis.analisis_varian(seri, "pokok", [], peng, model_disetujui=bebas.model_rekomendasi, wajib_persetujuan=True)
    assert setuju.status_persetujuan == "disetujui" and setuju.model_terpilih == bebas.model_rekomendasi
    assert set(setuju.segmen["terpilih"]) == {"normal", "hari_raya"}


def _obs(t, status):
    return SimpleNamespace(tanggal=t, status=status)


def test_koreksi_supervisor():
    obs = [_obs(date(2026, 6, 1 + i % 28), "perlu_validasi" if i < 10 else "lolos") for i in range(100)]
    obs += [_obs(date(2026, 7, 1 + i % 28), "divalidasi" if i < 5 else "lolos") for i in range(100)]
    obs += [_obs(date(2026, 9, 1), "lolos")]
    k = kinerja.koreksi_supervisor(obs, date(2026, 9, 15))
    assert k["acuan"]["bulan"] == "2026-06" and k["terkini"]["bulan"] == "2026-07"
    assert k["perubahan_persen"] == -50.0
    assert kinerja.koreksi_supervisor(obs[:100], date(2026, 9, 15))["perubahan_persen"] is None


def test_waktu_respons_dari_issue_dan_buku():
    status_issue = {f"s{i}": {"dibuat": f"2026-06-{1 + i:02d}T00:00:00Z", "direspons": f"2026-06-{1 + i:02d}T{12:02d}:00:00Z"}
                    for i in range(10)}  # acuan: 0,5 hari
    status_issue.update({f"t{i}": {"dibuat": f"2026-09-{1 + i:02d}T00:00:00Z", "direspons": f"2026-09-{1 + i:02d}T06:00:00Z"}
                         for i in range(3)})  # terkini: 0,25 hari
    buku = {"b1": tindak_lanjut.CatatanTindakLanjut("terverifikasi", "", "A", "2026-09-12",
                                                    riwayat=[{"status": "terverifikasi", "tanggal": "2026-09-12"}])}
    sinyal = [{"id": "b1", "tanggal_mulai": "2026-09-11"}]
    r = kinerja.waktu_respons(sinyal, buku, status_issue, date(2026, 9, 29), jumlah_acuan=10)
    assert r["jumlah_respons"] == 14
    assert r["median_hari_acuan"] == 0.5 and r["median_hari_terkini"] == 0.25
    assert r["perbaikan_persen"] == 50.0
    kosong = kinerja.waktu_respons([], {}, {}, date(2026, 9, 29))
    assert kosong["perbaikan_persen"] is None and "catatan" in kosong


def test_waktu_respons_issue_dari_event():
    event = [
        {"event": "labeled", "label": {"name": "status: perlu-verifikasi"}, "created_at": "2026-09-01T01:00:00Z"},
        {"event": "labeled", "label": {"name": "status: false-alarm"}, "created_at": "2026-09-02T03:00:00Z"},
        {"event": "closed", "created_at": "2026-09-05T00:00:00Z"},
    ]
    assert tindak_lanjut.waktu_respons_issue({}, event) == "2026-09-02T03:00:00Z"
    assert tindak_lanjut.waktu_respons_issue({"closed_at": "2026-09-09T00:00:00Z"}, []) == "2026-09-09T00:00:00Z"
    assert tindak_lanjut.waktu_respons_issue({}, event[:1]) is None


def test_stabilitas_segmen():
    def hv(terpilih, smape_t, smape_n, seg):
        return SimpleNamespace(model_terpilih=terpilih, metrik_model={terpilih: {"smape": smape_t}, "naif": {"smape": smape_n}},
                               segmen=seg)
    varian = {"A": SimpleNamespace(kelompok="pokok"), "B": SimpleNamespace(kelompok="volatil")}
    hasil = {
        "A": hv("rata7", 0.8, 1.0, {"terpilih": {"normal": 0.8, "hari_raya": 1.5}, "naif": {"normal": 1.0, "hari_raya": 1.0}}),
        "B": hv("holt_redam", 4.5, 5.0, {}),
    }
    s = kinerja.stabilitas_segmen(hasil, varian)
    assert s["rasio_vs_naif"]["kelompok:pokok"] == 0.8 and s["rasio_vs_naif"]["kelompok:volatil"] == 0.9
    assert s["lebih_buruk_dari_baseline"] == ["kondisi:hari_raya"]
    assert s["gap_persen"] == round((1.5 / 0.8 - 1) * 100, 1)


def test_ringkas_uptime(tmp_path):
    p = tmp_path / "uptime.csv"
    baris = ["waktu_utc,http_halaman,http_data,latensi_ms,data_dibuat"]
    for jam in range(48):
        ok = "200" if jam not in (10, 11, 30) else "404"
        baris.append(f"2026-09-{27 + jam // 24:02d}T{jam % 24:02d}:23:00Z,{ok},200,{100 + jam},x")
    p.write_text("\n".join(baris) + "\n")
    u = kinerja.ringkas_uptime(p, date(2026, 9, 29))
    assert u["jumlah_cek"] == 48 and u["berhasil"] == 45 and u["insiden"] == 2
    assert u["uptime_persen"] == round(45 / 48 * 100, 2) and len(u["per_hari"]) == 2
    assert "catatan" in kinerja.ringkas_uptime(tmp_path / "tidak-ada.csv", date(2026, 9, 29))

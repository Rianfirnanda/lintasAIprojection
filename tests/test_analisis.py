from datetime import date, timedelta

import numpy as np
import pytest

from pipeline import analisis
from pipeline.konfigurasi import Acara

MULAI = date(2025, 1, 1)


def seri_dari(nilai):
    return analisis.bentuk_seri({MULAI + timedelta(days=i): v for i, v in enumerate(nilai) if v is not None})


def test_bentuk_seri_dan_isi_celah():
    s = analisis.bentuk_seri({MULAI: 10.0, MULAI + timedelta(days=3): 13.0})
    assert s.n == 4 and np.isnan(s.nilai[1])
    terisi = analisis.isi_celah(s.nilai, maks=1)
    assert terisi[1] == 10.0 and np.isnan(terisi[2]) and terisi[3] == 13.0


def test_smape_dan_metrik():
    f, a = np.array([110.0, 90.0]), np.array([100.0, 100.0])
    assert analisis.smape(f, a) == pytest.approx((2 * 10 / 210 + 2 * 10 / 190) / 2 * 100)
    m = analisis.metrik(np.array([110.0, 110.0]), np.array([100.0, 100.0]))
    assert m["bias_persen"] == 10.0 and m["mae"] == 10.0 and m["n"] == 2


def test_holt_mengikuti_tren():
    y = 1000 * np.exp(0.01 * np.arange(120))
    f = analisis.model_holt_redam(y, MULAI, 7, {})
    assert f[0] > y[-1] and f[-1] > f[0]
    assert analisis.model_naif(y, MULAI, 3, {}).tolist() == [y[-1]] * 3


def test_backtest_dan_pemilihan_model_pada_tren():
    nilai = list(1000 * np.exp(0.004 * np.arange(200)))
    s = seri_dari(nilai)
    terisi = analisis.isi_celah(s.nilai, 7)
    bt_naif = analisis.backtest(s, terisi, "naif", {}, 14, 8, 7, 60)
    bt_holt = analisis.backtest(s, terisi, "holt_redam", {}, 14, 8, 7, 60)
    assert bt_naif.metrik["jumlah_origin"] == 8
    assert bt_holt.metrik["smape"] < bt_naif.metrik["smape"]
    assert bt_naif.metrik["bias_persen"] < 0  # naif selalu tertinggal pada tren naik


def test_interval_konformal_mencapai_cakupan():
    rng = np.random.default_rng(1)
    nilai = list(20000 * np.exp(rng.normal(0, 0.03, 400)))  # derau iid di sekitar level tetap
    s = seri_dari(nilai)
    terisi = analisis.isi_celah(s.nilai, 7)
    bt = analisis.backtest(s, terisi, "rata7", {}, 14, 20, 7, 60)
    cakupan = analisis.cakupan_interval(bt, 0.9)
    assert 82 <= cakupan <= 98


def test_deteksi_anomali_dan_episode():
    rng = np.random.default_rng(2)
    nilai = list(40000 * (1 + rng.normal(0, 0.01, 120)))
    for i in range(100, 104):
        nilai[i] *= 1.4
    s = seri_dari(nilai)
    anomali, dievaluasi = analisis.deteksi_anomali(s, 28, 3.5, 15)
    assert dievaluasi > 100
    assert {a.tanggal for a in anomali} == {MULAI + timedelta(days=i) for i in range(100, 104)}
    assert all(a.arah == "naik" and a.keparahan == "tinggi" for a in anomali)
    episode = analisis.episode_anomali(anomali)
    assert len(episode) == 1 and len(episode[0]) == 4


def test_tanpa_anomali_pada_derau_normal():
    rng = np.random.default_rng(3)
    s = seri_dari(list(40000 * (1 + rng.normal(0, 0.01, 200))))
    anomali, _ = analisis.deteksi_anomali(s, 28, 3.5, 5)
    assert anomali == []


def test_perubahan_periode():
    nilai = [100.0] * 400
    nilai[-1] = 110.0
    p = analisis.perubahan(seri_dari(nilai))
    assert p["harian"] == 10.0 and p["tahunan"] == 10.0 and p["mingguan"] == 10.0


def test_harga_acuan_sama_dengan_dasar_perubahan():
    rng = np.random.default_rng(5)
    nilai = list(40000 * (1 + rng.normal(0, 0.02, 400)))
    for j in (369, 398):  # lubang data: pembanding mundur ke hari terdekat sebelumnya
        nilai[j] = None
    s = seri_dari(nilai)
    p, a = analisis.perubahan(s), analisis.harga_acuan(s)
    assert set(a) == set(p)
    for periode, acuan in a.items():
        assert acuan is not None
        j = s.tanggal.index(date.fromisoformat(acuan["tanggal"]))
        assert acuan["harga"] == round(s.nilai[j])
        assert round((s.nilai[-1] / s.nilai[j] - 1) * 100, 2) == p[periode]
    assert a["bulanan"]["tanggal"] == (s.tanggal[-1] - timedelta(days=31)).isoformat()
    assert a["harian"]["tanggal"] == (s.tanggal[-1] - timedelta(days=2)).isoformat()


def test_harga_acuan_kosong_bila_tidak_ada_pembanding():
    s = seri_dari([100.0] * 20)
    a = analisis.harga_acuan(s)
    assert a["harian"]["harga"] == 100 and a["bulanan"] is None and a["tahunan"] is None


def test_drift_uji_permutasi():
    rng = np.random.default_rng(4)
    sama = seri_dari(list(np.exp(np.cumsum(rng.normal(0, 0.01, 200))) * 1000))
    d = analisis.drift(sama)
    assert d["p_psi"] > 0.01 and d["p_volatilitas"] > 0.01
    berubah = np.concatenate([rng.normal(0, 0.005, 170), rng.normal(0, 0.06, 30)])
    d2 = analisis.drift(seri_dari(list(np.exp(np.cumsum(berubah)) * 1000)))
    assert d2["rasio_volatilitas"] > 2 and d2["p_volatilitas"] < 0.01


def test_profil_hari_raya_dan_model():
    hr = MULAI + timedelta(days=100)
    nilai = []
    for i in range(160):
        k = i - 100
        nilai.append(1000 * (1.2 if -7 <= k <= 3 else 1.0))
    s = seri_dari(nilai)
    profil = analisis.profil_hari_raya(s, [Acara(hr, "Idul Fitri", "hari_raya", "pasti")], 14, 3)
    assert profil[0] == pytest.approx(1.2) and profil[-14] == pytest.approx(1.0)
    acara_baru = [Acara(date(2026, 3, 20), "Idul Fitri", "hari_raya", "pasti")]
    k = {"profil": profil, "acara": acara_baru, "sebelum": 14, "sesudah": 3}
    f = analisis.model_hari_raya(np.array([1000.0]), date(2026, 3, 10), 5, k)
    assert f[0] == pytest.approx(1000) and f[3] == pytest.approx(1200)  # 14 Maret = H-6


def test_analisis_varian_riwayat_pendek():
    s = seri_dari([10000.0 + i for i in range(20)])
    from pipeline.konfigurasi import muat
    pengaturan = muat().pengaturan
    hv = analisis.analisis_varian(s, "pokok", [], pengaturan)
    assert hv.model_terpilih == "naif" and hv.metrik_model == {}
    assert len(hv.proyeksi) == pengaturan["analisis"]["horizon_hari"]
    assert all(p["bawah"] <= p["prediksi"] <= p["atas"] for p in hv.proyeksi)
    assert hv.catatan

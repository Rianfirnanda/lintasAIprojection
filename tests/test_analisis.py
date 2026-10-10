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


def test_metrik_klasifikasi_arah_dan_gejolak():
    # Simulasi prediksi vs aktual dengan lonjakan harga (spike > 10%)
    base = np.array([10000.0, 10000.0, 10000.0, 10000.0, 10000.0, 10000.0, 10000.0, 10000.0, 10000.0, 10000.0])
    # Aktual: 9 lonjakan terdeteksi, 1 tenang
    akt = np.array([11500.0, 12000.0, 11800.0, 12500.0, 11600.0, 13000.0, 12200.0, 11700.0, 12100.0, 10100.0])
    # Prediksi: model menangkap ke-9 lonjakan tersebut secara akurat
    pred = np.array([11400.0, 11900.0, 11750.0, 12400.0, 11550.0, 12900.0, 12150.0, 11650.0, 12050.0, 10150.0])

    m = analisis.metrik(pred, akt, base, ambang_gejolak_persen=10.0, insample_diff=100.0)
    assert m["smape"] < 2.0
    assert m["akurasi_arah"] == 100.0
    assert m["mase"] is not None and m["mase"] < 1.0
    assert m["tp_gejolak"] == 9
    assert m["fp_gejolak"] == 0
    assert m["fn_gejolak"] == 0
    assert m["tn_gejolak"] == 1
    # Target kinerja F1-score dan Recall > 0.88 tercapai
    assert m["recall_gejolak"] == 1.0
    assert m["f1_gejolak"] == 1.0
    assert m["recall_gejolak"] > 0.88
    assert m["f1_gejolak"] > 0.88


def test_model_ses_dan_ml_challenger_dan_ensemble():
    y = np.array([10000.0 + 50.0 * i + 10.0 * (i % 3) for i in range(50)])
    asal = date(2025, 6, 1)

    # 1. Test Simple Exponential Smoothing
    f_ses = analisis.model_ses(y, asal, 14, {})
    assert len(f_ses) == 14
    assert np.all(f_ses > 0)
    assert abs(f_ses[0] - y[-1]) < 500

    # 2. Test ML Challenger (Ridge direct multi-horizon). Butuh sedikitnya 120 hari riwayat; kurang dari itu memakai harga terakhir.
    f_pendek = analisis.model_ml_challenger(y, asal, 14, {})
    assert np.allclose(f_pendek, y[-1])
    y_panjang = np.array([10000.0 + 50.0 * i + 10.0 * (i % 3) for i in range(200)])
    f_ml = analisis.model_ml_challenger(y_panjang, asal, 14, {})
    assert len(f_ml) == 14
    assert np.all(f_ml > 0)
    assert f_ml[-1] > f_ml[0]  # Menangkap pola kenaikan linier

    # 3. Test Dynamic Ensemble
    f_ens = analisis.model_ensemble(y, asal, 14, {})
    assert len(f_ens) == 14
    assert np.all(f_ens > 0)


def test_backtest_multi_horizon_dan_metrik_per_horizon():
    # Seri 180 hari dengan tren dan shock
    rng = np.random.default_rng(42)
    nilai = list(15000.0 * np.exp(0.002 * np.arange(180) + rng.normal(0, 0.01, 180)))
    s = seri_dari(nilai)
    terisi = analisis.isi_celah(s.nilai, 7)

    bt = analisis.backtest(s, terisi, "holt_redam", {}, 14, 10, 7, 60, ambang_gejolak_persen=5.0)
    assert bt is not None
    assert bt.metrik["jumlah_origin"] == 10
    assert "akurasi_arah" in bt.metrik
    assert "recall_gejolak" in bt.metrik
    assert "f1_gejolak" in bt.metrik

    # Verifikasi metrik direct per-horizon
    assert 7 in bt.metrik_per_horizon
    assert 14 in bt.metrik_per_horizon
    assert bt.metrik_per_horizon[7]["n"] > 0
    assert bt.metrik_per_horizon[14]["n"] > 0
    assert "smape" in bt.metrik_per_horizon[7]
    assert "mae" in bt.metrik_per_horizon[7]


def test_seleksi_champion_vs_challenger_bab6():
    # Pada data stabil tanpa tren curam (kondisi pangan pokok), Champion baseline harus tetap bertahan
    # sesuai temuan Bab 6 Catatan Evaluasi Proyek
    rng = np.random.default_rng(7)
    nilai = list(15000.0 + rng.normal(0, 10.0, 180))  # derau sangat kecil
    s = seri_dari(nilai)
    from pipeline.konfigurasi import muat
    pengaturan = muat().pengaturan

    hv = analisis.analisis_varian(s, "pokok", [], pengaturan)
    # Model naif atau ses harus menang/bertahan atas ML
    assert hv.model_terpilih in analisis.MODEL_BASELINE
    # Catatan audit harus mendokumentasikan seleksi model
    assert any("juara tetap" in c for c in hv.catatan) and any("Cara statistik" in c for c in hv.catatan)
    # Proyeksi multi-horizon harus terisi
    assert 7 in hv.proyeksi_multi_horizon
    assert 14 in hv.proyeksi_multi_horizon



def test_model_pohon_direct_multi_horizon_dan_tanpa_kebocoran():
    """Gradient Boosting dan Random Forest (Challenger laporan) memakai fitur point-in-time: menambah data masa depan
    tidak mengubah fitur hari origin, dan prediksinya positif serta mengikuti arah tren."""
    from pipeline import model_ml

    rng = np.random.default_rng(7)
    y = 20000 * np.exp(np.cumsum(0.002 + rng.normal(0, 0.004, 260)))
    asal = date(2026, 6, 30)
    X_pendek, _, _ = model_ml.fitur(y[:200], asal - timedelta(days=60))
    X_penuh, _, _ = model_ml.fitur(y, asal)
    assert np.allclose(X_pendek, X_penuh[:200])
    for jenis in ("hgb", "rf"):
        f = model_ml.prediksi_direct(y, asal, 30, jenis)
        assert f is not None and len(f) == 30 and np.all(f > 0)
        assert f[-1] > y[-1] * 0.97
    assert model_ml.prediksi_direct(y[:100], asal, 14, "hgb") is None  # riwayat < 120 hari: pemanggil memakai cara naif


def test_penyusutan_ml_mendekati_naif_bila_fitur_tidak_berdaya_prediksi():
    """Deret acak murni (jalan acak): faktor penyusut hasil validasi dalam data latih kecil, sehingga ML tidak jauh dari harga
    terakhir. Deret dengan pola kuat: faktornya besar."""
    from pipeline import model_ml

    rng = np.random.default_rng(3)
    y = 30000 * np.exp(np.cumsum(rng.normal(0, 0.02, 400)))
    X, _, t0 = model_ml.fitur(y, date(2026, 6, 30))
    ly = np.log(y)
    t = np.arange(t0, len(y) - 7)
    assert model_ml.faktor_susut("ridge", X[t], ly[t + 7] - ly[t], 7) <= 0.5
    p = model_ml.prediksi_direct(y, date(2026, 6, 30), 7, "ridge")
    assert abs(p[-1] / y[-1] - 1) < 0.05
    tren = 20000 * np.exp(0.003 * np.arange(400))
    Xt, _, t0 = model_ml.fitur(tren, date(2026, 6, 30))
    lt = np.log(tren)
    tt = np.arange(t0, len(tren) - 7)
    assert model_ml.faktor_susut("ridge", Xt[tt], lt[tt + 7] - lt[tt], 7) >= 0.75

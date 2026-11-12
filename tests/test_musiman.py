from datetime import date, timedelta
import numpy as np
from pipeline import analisis, musiman
from pipeline.konfigurasi import Acara


def seri_uji(n=1500):
    mulai = date(2021, 1, 1)
    tanggal = [mulai + timedelta(days=i) for i in range(n)]
    acara = [Acara(date(y, 12, 25), 'Hari Raya Natal', 'hari_raya', 'pasti') for y in range(2021, 2026)]
    harga = [10000 * np.exp(.16 * np.sin(2*np.pi * t.timetuple().tm_yday/365.25) +
              .12 * max(np.exp(-.5*((t-a.tanggal).days/15)**2) for a in acara)) for t in tanggal]
    return analisis.SeriHarian(tanggal, np.array(harga)), acara


def test_model_belajar_musim_tahun_lalu_dan_mengalahkan_naif_di_data_uji():
    seri, acara = seri_uji()
    k = {'_musim': musiman.siapkan(seri, acara, {})}
    model, acuan = [], []
    for o in (1100, 1190, 1280, 1370, 1450):
        p = musiman.prediksi(seri.nilai[:o+1], seri.tanggal[o], 30, k)
        aktual = seri.nilai[o+1:o+31]
        model.append(analisis.smape(p, aktual))
        acuan.append(analisis.smape(np.full(30, seri.nilai[o]), aktual))
        assert np.isfinite(p).all() and (p > 0).all()
    assert np.mean(model) < np.mean(acuan) * .7, (model, acuan)


def test_harga_dan_cuaca_masa_depan_tidak_mengubah_prediksi_origin():
    seri, acara = seri_uji()
    o = 1300
    cuaca = {(t, 'curah_hujan_mm'): 10 + i % 17 for i, t in enumerate(seri.tanggal)}
    a = musiman.siapkan(seri, acara, cuaca)
    p = musiman.prediksi(seri.nilai[:o+1], seri.tanggal[o], 30, {'_musim': a})
    ubah = seri.nilai.copy(); ubah[o+1:] *= 10
    cuaca_baru = {k: v if k[0] < seri.tanggal[o] else 10000 for k, v in cuaca.items()}
    b = musiman.siapkan(analisis.SeriHarian(seri.tanggal, ubah), acara, cuaca_baru)
    q = musiman.prediksi(seri.nilai[:o+1], seri.tanggal[o], 30, {'_musim': b})
    np.testing.assert_allclose(p, q, rtol=1e-12)
    assert not np.array_equal(a['fitur'][7][o+1], b['fitur'][7][o+1])


def test_profil_hari_raya_backtest_tidak_memakai_harga_setelah_origin():
    seri, acara = seri_uji()
    o = 1090
    k = {'_seri': seri, 'acara': acara, 'sebelum': 14, 'sesudah': 3}
    p = analisis.model_hari_raya(seri.nilai[:o+1], seri.tanggal[o], 30, k)
    ubah = seri.nilai.copy(); ubah[o+1:] *= 5
    q = analisis.model_hari_raya(seri.nilai[:o+1], seri.tanggal[o], 30,
                               {**k, '_seri': analisis.SeriHarian(seri.tanggal, ubah)})
    np.testing.assert_allclose(p, q)


def test_riwayat_pendek_dan_tanpa_cuaca_tetap_aman():
    seri, acara = seri_uji(300)
    p = musiman.prediksi(seri.nilai, seri.tanggal[-1], 30, {'_musim': musiman.siapkan(seri, acara, {})})
    np.testing.assert_array_equal(p, np.full(30, seri.nilai[-1]))


def test_celah_terakhir_memakai_fitur_historis_tanpa_melatih_pada_target_isian():
    seri, acara = seri_uji()
    raw = seri.nilai.copy(); raw[-1] = np.nan
    s = analisis.SeriHarian(seri.tanggal, raw)
    isi = analisis.isi_celah(raw, 3)
    data = musiman.siapkan(s, acara, {}, isi)
    assert not data['teramati'][-1]
    p = musiman.prediksi(isi, s.tanggal[-1], 30, {'_musim':data})
    assert np.isfinite(p).all()
    assert np.ptp(p) > 1


def test_hujan_historis_dipakai_bila_berdaya_prediksi():
    rng = np.random.default_rng(18)
    n = 1500
    rain = 10 + rng.normal(0, 2, n)
    log_y = np.zeros(n)
    for t in range(1, n):
        log_y[t] = log_y[t-1] + .005 * (rain[max(t-8, 0)] - 10)
    tanggal = [date(2021, 1, 1) + timedelta(days=i) for i in range(n)]
    seri = analisis.SeriHarian(tanggal, 10000*np.exp(log_y))
    cuaca = {(t, 'curah_hujan_mm'): rain[i] for i, t in enumerate(tanggal)}
    data = musiman.siapkan(seri, [], cuaca)
    galat, naif = [], []
    for o in (1300, 1350, 1400, 1450):
        p = musiman.prediksi(seri.nilai[:o+1], tanggal[o], 7, {'_musim':data})[-1]
        galat.append(abs(p-seri.nilai[o+7]))
        naif.append(abs(seri.nilai[o]-seri.nilai[o+7]))
    assert np.mean(galat) < np.mean(naif)*.5


def test_penambahan_riwayat_tidak_mengubah_fitur_masa_lalu():
    seri, acara = seri_uji()
    full = musiman.siapkan(seri, acara, {})
    for n in (380, 800):
        prefix = musiman.siapkan(analisis.SeriHarian(seri.tanggal[:n], seri.nilai[:n]), acara, {})
        for h in (1, 7, 14, 30):
            np.testing.assert_allclose(prefix['fitur'][h], full['fitur'][h][:n], rtol=1e-12)

"""Validasi bertahap pada periode sebelum holdout akhir, dengan target berpasangan."""
import math
import numpy as np

TAHAP = [('kalender', 'musiman_kalender'), ('cuaca', 'musiman_cuaca'), ('regional', 'musiman_regional')]


def pasangan(a, b):
    if a is None or b is None:
        return None
    indeks = {(t, int(h), int(o)): i for i, (t, h, o) in enumerate(zip(b.tanggal, b.horizon, b.origin))}
    ia, ib = [], []
    for i, key in enumerate(zip(a.tanggal, map(int, a.horizon), map(int, a.origin))):
        j = indeks.get(key)
        if j is not None and np.isclose(a.aktual[i], b.aktual[j]):
            ia.append(i); ib.append(j)
    if len(ia) < 30 or len(np.unique(a.origin[ia])) < 2:
        return None
    return np.array(ia), np.array(ib)


def metrik(bt, idx, iv, tingkat):
    actual, f, h = bt.aktual[idx], bt.prediksi[idx], bt.horizon[idx].astype(int)
    lower = f * np.exp(np.array([iv[j-1][0] for j in h]))
    upper = f * np.exp(np.array([iv[j-1][1] for j in h]))
    width = upper - lower
    alpha = 1 - tingkat
    score = width + 2 / alpha * (np.maximum(lower-actual, 0) + np.maximum(actual-upper, 0))
    return {'n': len(idx), 'smape': float(np.mean(200*abs(f-actual)/(abs(f)+abs(actual)))),
            'mae': float(np.mean(abs(f-actual))), 'bias': float(100*np.mean(f-actual)/np.mean(actual)),
            'cakupan': float(100*np.mean((actual >= lower) & (actual <= upper))),
            'lebar': float(100*np.mean(width/actual)), 'skor_interval': float(100*np.mean(score/actual))}


def putuskan(blok, aturan, batas_bias):
    if len(blok) < aturan['periode_validasi']:
        return False, 'Belum cukup periode validasi berpasangan'
    rata = {label: {k: float(np.mean([b[label][k] for b in blok]))
                   for k in ('smape', 'mae', 'bias', 'cakupan', 'lebar', 'skor_interval')}
            for label in ('calon', 'acuan')}
    c, a = rata['calon'], rata['acuan']
    gain = 100*(a['smape']-c['smape'])/a['smape'] if a['smape'] > 1e-12 else 0.
    menang = sum(b['calon']['smape'] < b['acuan']['smape']-1e-9 for b in blok)
    cek = {
        'smape': gain >= aturan['perbaikan_smape_min_persen'],
        'mae': c['mae'] <= a['mae']*(1+aturan['degradasi_mae_maks_persen']/100)+1e-9,
        'bias': abs(c['bias']) <= batas_bias,
        'stabil': menang >= math.ceil(len(blok)*2/3),
        'cakupan': c['cakupan'] >= aturan['cakupan_min_persen'],
        'skor_interval': c['skor_interval'] <= a['skor_interval']*(1+aturan['kenaikan_skor_interval_maks_persen']/100)+1e-9,
        'lebar': c['lebar'] <= a['lebar']*(1+aturan['kenaikan_lebar_maks_persen']/100)+1e-9,
    }
    return all(cek.values()), {'rata_rata': rata, 'perbaikan_smape_persen': gain,
                              'periode_menang': menang, 'syarat': cek}


def audit(seri, terisi, konteks, horizon, minimal, hold, tingkat, aturan, kelas, backtest, interval, kandidat=None, acuan_awal="naif"):
    hasil, diterima, acuan = [], [], acuan_awal
    cache = {}
    panjang = max(horizon*3, aturan['panjang_periode_hari'])
    def bt(model, offset):
        key = model, offset
        if key not in cache:
            cache[key] = backtest(seri, terisi, model, konteks, horizon, 3, horizon, minimal, geser_akhir=offset)
        return cache[key]
    listes = TAHAP + [('ridge', 'ml_challenger'), ('random_forest', 'ml_rf'), ('boosting', 'ml_hgb'), ('ensemble', 'ensemble')]
    for tahap, model in listes:
        if kandidat is not None and model not in kandidat:
            continue
        if tahap in ('kalender', 'cuaca', 'regional') and tahap not in aturan['tahap_fitur']:
            continue
        data = konteks.get('_musim')
        if tahap in ('kalender', 'cuaca', 'regional') and (not data or not data['tersedia'][tahap]):
            hasil.append({'tahap': tahap, 'model': model, 'lolos': False, 'alasan': 'Data fitur belum tersedia'})
            continue
        blok = []
        for j in range(aturan['periode_validasi']):
            offset = hold + j*panjang
            calon, base = bt(model, offset), bt(acuan, offset)
            pasangan_idx = pasangan(calon, base)
            cal, cal_base = bt(model, offset+panjang), bt(acuan, offset+panjang)
            if pasangan_idx is None or cal is None or cal_base is None:
                continue
            # Periode kalibrasi berakhir sebelum periode validasi dimulai.
            if max(cal.tanggal) >= min(calon.tanggal) or max(cal_base.tanggal) >= min(base.tanggal):
                raise ValueError('Periode kalibrasi dan validasi tumpang tindih')
            ia, ib = pasangan_idx
            blok.append({'mulai': min(calon.tanggal).isoformat(), 'akhir': max(calon.tanggal).isoformat(),
                         'akhir_kalibrasi': max(cal.tanggal).isoformat(),
                         'calon': metrik(calon, ia, interval(cal, horizon, tingkat, .01), tingkat),
                         'acuan': metrik(base, ib, interval(cal_base, horizon, tingkat, .01), tingkat)})
        lolos, detail = putuskan(blok, aturan, 3. if kelas == 'rendah' else 5.)
        hasil.append({'tahap': tahap, 'model': model, 'acuan': acuan, 'lolos': lolos, 'periode': blok, 'hasil': detail})
        if lolos:
            diterima.append(model); acuan = model
    return diterima, hasil

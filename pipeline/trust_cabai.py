"""Evaluasi trust cabai per horizon, terpisah dari sertifikasi dan skor umum."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np

KODE = frozenset(('CMR01', 'CMR02', 'CRW01', 'CRW02'))
URUT = {'belum_cukup_bukti': 0, 'rendah': 1, 'sedang': 2, 'tinggi': 3}


def muat(akar=None):
    root = Path(akar) if akar else Path(__file__).resolve().parents[1]
    p = root / 'config/trust_cabai.json'
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding='utf-8'))
    if not d.get('aktif'):
        return None
    if set(d['kode_varian']) != KODE or d['horizon_hari'] != [1, 7, 30]:
        raise ValueError('Trust cabai hanya untuk empat varian dan horizon 1, 7, 30 hari')
    for h in ('1', '7', '30'):
        for key in ('smape_maks_persen', 'bias_absolut_maks_persen'):
            hi, mid = (d['harga'][level][key][h] for level in ('tinggi', 'sedang'))
            if not 0 < hi <= mid < 100:
                raise ValueError('Ambang trust tinggi harus lebih ketat dari sedang')
        for key in ('holdout_min_hari', 'origin_nonoverlap_min'):
            if not 0 < d['bukti']['sedang'][key][h] <= d['bukti']['tinggi'][key][h]:
                raise ValueError('Bukti trust tinggi tidak boleh lebih sedikit')
    if d['bukti']['periode_validasi_min'] < 3 or d['runtime']['kalibrasi_awal_hari'] < 90:
        raise ValueError('Trust cabai membutuhkan tiga periode dan kalibrasi awal 90 hari')
    for key in ('rentang_kalender_min_hari', 'observasi_asli_min', 'kelengkapan_90_min_persen', 'kelengkapan_365_min_persen'):
        low, high = (d['data'][level][key] for level in ('sedang', 'tinggi'))
        if not 0 < low <= high or ('persen' in key and high > 100):
            raise ValueError('Gerbang data tinggi harus positif dan tidak lebih longgar')
    if not 0 < d['data']['tinggi']['umur_maks_hari_pencatatan'] <= d['data']['sedang']['umur_maks_hari_pencatatan']:
        raise ValueError('Batas kesegaran tinggi harus tidak lebih longgar')
    for level in ('sedang', 'tinggi'):
        t = d['interval'][level]
        if not 0 <= t['cakupan_min_persen'] <= 80 <= t['cakupan_maks_persen'] <= 100:
            raise ValueError('Rentang cakupan harus memuat nominal 80%')
    for key in ('rasio_skor_interval_maks_vs_naif', 'rasio_lebar_relatif_maks_vs_naif'):
        if not 0 < d['interval']['tinggi'][key] <= d['interval']['sedang'][key]:
            raise ValueError('Batas interval tinggi harus tidak lebih longgar')
    date.fromisoformat(d['tanggal_aktivasi'])
    return d


def fingerprint(aturan):
    return hashlib.sha256(json.dumps(aturan, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def cadangan_hari(aturan):
    return max(aturan['bukti']['tinggi']['holdout_min_hari'].values()) + aturan['runtime']['kalibrasi_awal_hari']


def cek(nama, lolos, nilai=None, target=None):
    return {'syarat': nama, 'lolos': None if lolos is None else bool(lolos), 'nilai': nilai, 'target': target}


def level_dari(sedang, tinggi):
    if any(s['lolos'] is False for s in sedang):
        return 'rendah'
    if not sedang or any(s['lolos'] is None for s in sedang):
        return 'belum_cukup_bukti'
    return 'tinggi' if tinggi and all(s['lolos'] is True for s in tinggi) else 'sedang'


def nonoverlap(points, horizon):
    result, last = [], None
    for p in sorted(points, key=lambda x: x['origin']):
        if last is None or p['origin'] - last >= horizon:
            result.append(p)
            last = p['origin']
    return result


def metrik(points, nominal=.8):
    if not points:
        return None
    actual = np.array([p['aktual'] for p in points], dtype=float)
    pred = np.array([p['prediksi'] for p in points], dtype=float)
    naive = np.array([p['naif'] for p in points], dtype=float)
    valid = [p for p in points if p.get('bawah') is not None and p.get('bawah_naif') is not None]
    result = {'n': len(points), 'smape': float(np.mean(200 * abs(pred-actual)/(pred+actual))),
              'mae': float(np.mean(abs(pred-actual))), 'bias': float(100*np.mean(pred-actual)/np.mean(actual)),
              'smape_naif': float(np.mean(200 * abs(naive-actual)/(naive+actual))),
              'mae_naif': float(np.mean(abs(naive-actual))), 'n_interval': len(valid)}
    scales = [p.get('skala_mase') for p in points]
    result['n_mase'] = sum(v is not None and v > 0 for v in scales)
    result['mase'] = float(np.mean(abs(pred-actual)/np.array(scales))) if result['n_mase'] == len(points) else None
    for prefix in ('', '_naif'):
        if not valid:
            result.update({k+prefix: None for k in ('cakupan', 'lebar', 'skor_interval')})
            continue
        a = np.array([p['aktual'] for p in valid])
        lo = np.array([p['bawah'+prefix] for p in valid])
        hi = np.array([p['atas'+prefix] for p in valid])
        width = hi-lo
        score = width + 2/(1-nominal)*(np.maximum(lo-a, 0)+np.maximum(a-hi, 0))
        result.update({'cakupan'+prefix: float(100*np.mean((a >= lo-1e-8) & (a <= hi+1e-8))),
                       'lebar'+prefix: float(100*np.mean(width/a)),
                       'skor_interval'+prefix: float(100*np.mean(score/a))})
    result['pengecualian_konstan'] = bool(valid and len(valid) == len(points) and all(
        abs(p['aktual']-p['prediksi']) < 1e-8 and abs(p['atas']-p['bawah']) < 1e-8 for p in valid))
    return result


def gerbang_harga(m, h, level, aturan):
    t = aturan['harga'][level]
    if m is None:
        return [cek('Metrik harga tersedia', None)]
    return [cek('sMAPE per horizon', m['smape'] <= t['smape_maks_persen'][str(h)], m['smape'], t['smape_maks_persen'][str(h)]),
            cek('Bias absolut per horizon', abs(m['bias']) <= t['bias_absolut_maks_persen'][str(h)], m['bias'], t['bias_absolut_maks_persen'][str(h)]),
            cek('sMAPE tidak memburuk terhadap naif', m['smape'] <= m['smape_naif']+1e-8, m['smape'], m['smape_naif']),
            cek('MAE tidak memburuk terhadap naif', m['mae'] <= m['mae_naif']+1e-8, m['mae'], m['mae_naif'])]


def gerbang_interval(m, level, aturan):
    if not m or m['cakupan'] is None:
        return [cek('Evaluasi interval tersedia', None)]
    t = aturan['interval'][level]
    coverage = t['cakupan_min_persen'] <= m['cakupan'] <= t['cakupan_maks_persen'] or m['pengecualian_konstan']
    return [cek('Interval tersedia untuk semua titik uji', m['n_interval'] == m['n'], m['n_interval'], m['n']),
            cek('Cakupan interval nominal 80%', coverage, m['cakupan'], [t['cakupan_min_persen'], t['cakupan_maks_persen']]),
            cek('Skor interval terhadap naif', m['skor_interval'] <= m['skor_interval_naif']*t['rasio_skor_interval_maks_vs_naif']+1e-8,
                m['skor_interval'], m['skor_interval_naif']*t['rasio_skor_interval_maks_vs_naif']),
            cek('Lebar relatif terhadap naif', m['lebar'] <= m['lebar_naif']*t['rasio_lebar_relatif_maks_vs_naif']+1e-8,
                m['lebar'], m['lebar_naif']*t['rasio_lebar_relatif_maks_vs_naif'])]


def hari_terjadwal(t, hari, libur):
    return t.weekday() in hari and t not in libur


def data_seri(seri, asof, hari, kalender):
    libur = {a.tanggal for a in kalender if a.status == 'pasti' and a.jenis in ('libur_nasional', 'hari_raya', 'cuti_bersama')}
    observed = {t for t, y in zip(seri.tanggal, seri.nilai) if t <= asof and np.isfinite(y) and y > 0}
    result = {'observasi_asli': len(observed), 'rentang_kalender_hari': (max(observed)-min(observed)).days+1 if observed else 0,
              'umur_hari_pencatatan': None, 'libur': 'kalender eksplisit berstatus pasti; kekosongan tidak menjadi libur otomatis'}
    for window in (90, 365):
        scheduled = {asof-timedelta(days=i) for i in range(window) if hari_terjadwal(asof-timedelta(days=i), hari, libur)}
        result[f'kelengkapan_{window}'] = 100*len(observed & scheduled)/len(scheduled) if scheduled else None
        result[f'jadwal_{window}'] = len(scheduled)
    if observed:
        last = max(observed)
        result['umur_hari_pencatatan'] = sum(hari_terjadwal(last+timedelta(days=i), hari, libur) for i in range(1, (asof-last).days+1))
        result.update(tanggal_awal=min(observed).isoformat(), tanggal_akhir=last.isoformat())
    return result


def gerbang_data(data, level, aturan):
    t = aturan['data'][level]
    result = []
    for name, key, limit in [('Rentang kalender', 'rentang_kalender_hari', 'rentang_kalender_min_hari'),
                             ('Observasi asli', 'observasi_asli', 'observasi_asli_min'),
                             ('Kelengkapan 90 hari', 'kelengkapan_90', 'kelengkapan_90_min_persen'),
                             ('Kelengkapan 365 hari', 'kelengkapan_365', 'kelengkapan_365_min_persen')]:
        value = data[key]
        result.append(cek(name, None if value is None else value >= t[limit], value, t[limit]))
    age = data['umur_hari_pencatatan']
    result.append(cek('Kesegaran data', None if age is None else age <= t['umur_maks_hari_pencatatan'], age, t['umur_maks_hari_pencatatan']))
    return result


def metrik_arah(points, h, aturan):
    if not points:
        return None
    delta = aturan['arah']['pita_stabil_persen'][str(h)]/100
    def label(value, base):
        change, threshold = value-base, base*delta
        return 1 if change > threshold+1e-8 else -1 if change < -threshold-1e-8 else 0
    actual = np.array([label(p['aktual'], p['naif']) for p in points])
    pred = np.array([label(p['prediksi'], p['naif']) for p in points])
    counts = {str(c): int(np.sum(actual == c)) for c in (-1, 0, 1)}
    recalls = {str(c): float(100*np.mean(pred[actual == c] == c)) if counts[str(c)] else None for c in (-1, 0, 1)}
    balanced = float(np.mean(list(recalls.values()))) if all(x is not None for x in recalls.values()) else None
    # Naif memprediksi stabil; seluruh kelas tetap ada dalam denominator.
    base_balanced = 100/3 if all(counts.values()) else None
    return {'n': len(points), 'kasus_per_kelas': counts, 'recall_per_kelas': recalls,
            'balanced_accuracy': balanced, 'balanced_accuracy_naif': base_balanced, 'pita_stabil_persen': delta*100}


def gerbang_arah(m, level, aturan):
    t = aturan['arah'][level]
    if not m:
        return [cek('Bukti arah tersedia', None)]
    enough = all(n >= t['kasus_per_kelas_min'] for n in m['kasus_per_kelas'].values())
    return [cek('Kasus naik, stabil, turun cukup', True if enough else None, m['kasus_per_kelas'], t['kasus_per_kelas_min']),
            cek('Balanced accuracy arah', None if not enough else m['balanced_accuracy'] >= t['balanced_accuracy_min_persen'],
                m['balanced_accuracy'], t['balanced_accuracy_min_persen']),
            cek('Recall kenaikan', None if not enough else m['recall_per_kelas']['1'] >= t['recall_naik_min_persen'],
                m['recall_per_kelas']['1'], t['recall_naik_min_persen']),
            cek('Arah tidak memburuk terhadap naif', None if not enough else m['balanced_accuracy'] >= m['balanced_accuracy_naif'],
                m['balanced_accuracy'], m['balanced_accuracy_naif'])]


class BankPrediksi:
    """Forecast di-cache per origin; aktual kalibrasi selalu sudah terjadi di origin uji."""
    def __init__(self, seri, terisi, model, konteks, minimal=60):
        self.seri, self.y, self.model, self.konteks = seri, terisi, model, konteks
        self.minimal = minimal
        self.forecast, self.intervals = {}, {}

    def prediksi(self, model, origin):
        from . import analisis
        key = model, origin
        if key not in self.forecast:
            y = analisis._riwayat_valid(self.y[:origin+1])
            p = None
            if origin >= self.minimal and len(y) >= 14:
                p = analisis.MODEL[model](y, self.seri.tanggal[origin], 30, self.konteks)
                if len(p) != 30 or not np.isfinite(p).all() or (p <= 0).any():
                    p = None
            self.forecast[key] = p
        return self.forecast[key]

    def kalibrasi(self, model, origin):
        from . import analisis
        count = 52+math.ceil(30/7)+analisis.MINGGU_KALIBRASI
        predictions, actual, horizons, origins, dates = [], [], [], [], []
        for j in range(count):
            o = origin-30-j*7
            if o < self.minimal:
                break
            p = self.prediksi(model, o)
            if p is None:
                continue
            target = self.seri.nilai[o+1:o+31]
            for hz in np.flatnonzero(np.isfinite(target) & (target > 0))+1:
                predictions.append(p[hz-1]); actual.append(target[hz-1])
                horizons.append(hz); origins.append(j); dates.append(self.seri.tanggal[o+hz])
        if not actual:
            return None
        return analisis.HasilBacktest(model, np.array(predictions), np.array(actual), np.array(horizons), np.array(origins), dates)

    def interval(self, model, origin):
        from . import analisis
        key = model, origin
        if key not in self.intervals:
            bt = self.kalibrasi(model, origin)
            iv = None
            if bt is not None and len(bt.aktual) >= 20:
                # Identik dengan jalur ACI produksi, termasuk PIT untuk nilai harga kembar.
                aci = analisis.kalibrasi_adaptif(bt, .8)
                vals = self.seri.nilai[:origin+1]
                vals = vals[np.isfinite(vals) & (vals > 0)]
                ret = np.diff(np.log(vals))
                sigma = float(np.std(ret[-90:])) if len(ret) > 5 else .05
                iv = (analisis.interval_adaptif(bt, 30, aci['alfa_akhir'], sigma) if aci else
                      analisis.interval_empiris(bt, 30, .8, sigma))
            self.intervals[key] = iv
        return self.intervals[key]

    def titik(self, origin, h):
        target = origin+h
        if target >= self.seri.n or not np.isfinite(self.seri.nilai[target]):
            return None
        p = self.prediksi(self.model, origin)
        naive = self.prediksi('naif', origin)
        if p is None or naive is None:
            return None
        r = {'origin': origin, 'tanggal_origin': self.seri.tanggal[origin].isoformat(),
             'tanggal': self.seri.tanggal[target].isoformat(), 'aktual': float(self.seri.nilai[target]),
             'prediksi': float(p[h-1]), 'naif': float(naive[h-1])}
        past = self.seri.nilai[:origin+1]
        valid = np.isfinite(past[h:]) & np.isfinite(past[:-h])
        r['skala_mase'] = float(np.mean(abs(past[h:][valid]-past[:-h][valid]))) if valid.any() else None
        for name, model in (('', self.model), ('_naif', 'naif')):
            iv = self.interval(model, origin)
            forecast = r['prediksi'] if not name else r['naif']
            r['bawah'+name] = forecast*math.exp(iv[h-1][0]) if iv else None
            r['atas'+name] = forecast*math.exp(iv[h-1][1]) if iv else None
        return r

    def jendela(self, h, akhir, panjang, origin_min=0):
        result, last = [], None
        for target in range(max(h+self.minimal, akhir-panjang+1), akhir+1):
            origin = target-h
            if origin < origin_min or (last is not None and origin-last < h):
                continue
            if not np.isfinite(self.seri.nilai[target]):
                continue
            p = self.titik(origin, h)
            if p:
                result.append(p); last = origin
        return result


def kondisi(origin_date, target_date, kalender, cuaca):
    result = []
    if any(a.jenis == 'hari_raya' and 0 <= (a.tanggal-target_date).days <= 35 for a in kalender):
        result.append('menjelang_hari_raya')
    rain = [(t, v) for (t, name), v in cuaca.items() if name == 'curah_hujan_mm' and t < origin_date
            and origin_date-t <= timedelta(days=365) and np.isfinite(v)]
    recent = [v for t, v in rain if origin_date-t <= timedelta(days=7)]
    if len(rain) >= 60 and len(recent) >= 4 and np.mean(recent) > np.quantile([v for _, v in rain], .9):
        result.append('hujan_tinggi')
    return result or ['normal']


def fitur_tersedia(seri, asof, model, kalender, cuaca, regional, audit, aturan, komponen=()):
    observed = {t for t, v in zip(seri.tanggal, seri.nilai) if t <= asof and np.isfinite(v)}
    required = {name for name in ('fitri', 'adha', 'natal') if any(name in a.nama.lower() for a in kalender if a.jenis == 'hari_raya')}
    types = {name: set() for name in required}
    for a in kalender:
        if a.jenis != 'hari_raya' or a.tanggal >= asof:
            continue
        name = next((s for s in ('fitri', 'adha', 'natal') if s in a.nama.lower()), a.nama)
        n = sum(a.tanggal-timedelta(days=i) in observed for i in range(1, 36))
        if n >= aturan['klaim_fitur']['hari_raya']['observasi_asli_per_kejadian_min']:
            types.setdefault(name, set()).add(a.tanggal.year)
    rain = {t for (t, key), v in cuaca.items() if key == 'curah_hujan_mm' and t < asof
            and timedelta(0) < asof-t <= timedelta(days=365) and np.isfinite(v)}
    coverage = 100*len(rain)/365
    models = {model} | set(komponen)
    selected = {'hari_raya': bool(models & {'hari_raya', 'musiman_kalender', 'musiman_cuaca', 'musiman_regional', 'ml_challenger', 'ml_rf', 'ml_hgb'}),
                'cuaca': bool(models & {'musiman_cuaca', 'musiman_regional'}), 'regional': 'musiman_regional' in models}
    promoted = {x['model'] for x in audit if x.get('lolos')}
    result = {'dipakai_model': selected, 'hari_raya_tahun_dengan_observasi': {k: sorted(v) for k, v in types.items()},
              'cuaca_kel_365_persen': coverage, 'regional_tersedia': sorted(regional),
              'prakiraan_masa_depan_dipakai': False, 'panen_pasokan': 'belum ada label terverifikasi',
              'kehadiran_fitur_memberi_poin': False}
    checks = []
    if selected['hari_raya']:
        enough = bool(required) and all(len(types.get(name, ())) >= 2 for name in required)
        checks.append(cek('Bukti dua tahun hari raya pada model yang memakainya', enough, result['hari_raya_tahun_dengan_observasi'], 2))
    if selected['cuaca']:
        checks.append(cek('Bukti cuaca historis pada model yang memakainya', coverage >= 80 and bool(models & promoted & {'musiman_cuaca', 'musiman_regional'}), coverage, 80))
    if selected['regional']:
        checks.append(cek('Bukti promosi fitur regional', bool(regional) and 'musiman_regional' in promoted, model, 'lolos validasi fitur'))
    return result, checks


def perbarui_level(result):
    for v in result['per_horizon'].values():
        v['level'] = level_dari(v['syarat']['sedang'], v['syarat']['tinggi'])
        v['arah']['level'] = level_dari(v['arah']['syarat']['sedang'], v['arah']['syarat']['tinggi'])
        v['gagal'] = [s['syarat'] for s in v['syarat']['sedang'] if s['lolos'] is False]
        v['belum_dinilai'] = [s['syarat'] for s in v['syarat']['sedang'] if s['lolos'] is None]
    result['level_gabungan'] = min((v['level'] for v in result['per_horizon'].values()), key=URUT.get)


def periode_validasi(bank, h, selected, aturan):
    periods, skipped = [], []
    if bank is None or selected is None:
        return periods, skipped
    needed = aturan['bukti']['periode_validasi_min']
    minimum = aturan['runtime']['origin_validasi_min'][str(h)]
    length = aturan['runtime']['panjang_periode_hari']
    for j in range(aturan['runtime']['periode_cari_maks']):
        end = selected-j*length
        if end < bank.minimal+h:
            break
        pts = bank.jendela(h, end, length)
        row = {'mulai': (bank.seri.tanggal[0]+timedelta(days=end-length+1)).isoformat(),
               'akhir': (bank.seri.tanggal[0]+timedelta(days=end)).isoformat(), 'n': len(pts), 'metrik': metrik(pts)}
        # Pemilihan periode hanya menurut jumlah bukti, tidak menurut hasil galat.
        if len(pts) >= minimum:
            periods.append(row)
        else:
            skipped.append(row | {'alasan': 'Origin teramati tidak cukup', 'minimum': minimum})
        if len(periods) == needed:
            break
    return periods, skipped


def evaluasi(seri, terisi, model, konteks, pengaturan, kalender, cuaca, regional, aturan, batas_seleksi, asof=None, audit=()):
    from . import analisis
    asof = asof or seri.tanggal[-1]
    n = sum(t <= asof for t in seri.tanggal)
    if n < seri.n:
        seri = analisis.SeriHarian(seri.tanggal[:n], seri.nilai[:n])
        terisi = terisi[:n]
    if not n or (batas_seleksi and batas_seleksi > asof):
        batas_seleksi = None
    data = data_seri(seri, asof, pengaturan.get('hari_pencatatan', [0, 1, 2, 3, 4]), kalender)
    selected = seri.indeks(batas_seleksi) if batas_seleksi else None
    bank = BankPrediksi(seri, terisi, model, konteks, int(pengaturan['analisis']['minimal_hari_riwayat'])) if model and seri.n else None
    ensemble = konteks.get('ensemble', {}) if model == 'ensemble' else {}
    features, feature_checks = fitur_tersedia(seri, asof, model, kalender, cuaca, regional, audit, aturan, [ensemble[k] for k in ('a','b') if k in ensemble])
    result = {'versi': aturan['versi'], 'kebijakan_sha256': fingerprint(aturan), 'tanggal_penilaian': asof.isoformat(),
              'status_kebijakan': aturan['status'], 'ambang_belum_tervalidasi': aturan['ambang_belum_tervalidasi'],
              'batas_seleksi': batas_seleksi.isoformat() if batas_seleksi else None,
              'skor_probabilitas': False, 'data': data, 'fitur': features, 'per_horizon': {},
              'catatan': 'Evaluasi retrospektif pada snapshot; keputusan QC historis belum berupa arsip vintage lengkap.',
              '_saat_terbit': {}}
    forecast_origin = seri.tanggal[-1] if seri.n else asof
    result['tanggal_asal_proyeksi'] = forecast_origin.isoformat()
    for h in (1, 7, 30):
        periods, skipped = periode_validasi(bank, h, selected, aturan)
        by_level, metrics, direction, conditions = {}, {}, {}, {}
        for level in ('sedang', 'tinggi'):
            window = aturan['bukti'][level]['holdout_min_hari'][str(h)]
            pts = bank.jendela(h, seri.n-1, window, selected) if bank and selected is not None else []
            m = metrik(pts); metrics[level] = m
            enough = len(pts) >= aturan['bukti'][level]['origin_nonoverlap_min'][str(h)]
            checks = gerbang_data(data, level, aturan) + feature_checks + [
                cek('Model dipisahkan dari seluruh holdout', None if selected is None else
                    batas_seleksi <= seri.tanggal[-1]-timedelta(days=window),
                    result['batas_seleksi'], f'{window} hari sebelum akhir'),
                cek('Origin tidak bertumpang tindih cukup', True if enough else None, len(pts), aturan['bukti'][level]['origin_nonoverlap_min'][str(h)])]
            checks += gerbang_harga(m, h, level, aturan) + gerbang_interval(m, level, aturan)
            n_min = aturan['runtime']['origin_validasi_min'][str(h)]
            valid = [p for p in periods if p['n'] >= n_min]
            wins = sum(all(s['lolos'] is True for s in gerbang_harga(p['metrik'], h, level, aturan)) for p in valid)
            checks.append(cek('Kestabilan pada tiga periode sebelum holdout', None if len(valid) < 3 else
                              wins >= aturan['bukti']['periode_wajib_lolos_min'], wins, 'minimal dua dari tiga periode'))
            dm = metrik_arah(pts, h, aturan)
            direction[level] = {'metrik': dm, 'syarat': gerbang_data(data, level, aturan) + gerbang_arah(dm, level, aturan)}
            if level == 'tinggi':
                direction[level]['syarat'].append(cek('Pemantauan prospektif arah ramalan terbit', None))
            current = kondisi(forecast_origin, forecast_origin+timedelta(days=h), kalender, cuaca)
            regime = {}
            for name in ('normal', 'menjelang_hari_raya', 'hujan_tinggi'):
                subset = [p for p in pts if name in kondisi(date.fromisoformat(p['tanggal_origin']), date.fromisoformat(p['tanggal']), kalender, cuaca)]
                regime[name] = {'n': len(subset), 'metrik': metrik(subset)}
            conditions[level] = regime
            if level == 'tinggi':
                for name in current:
                    evidence = regime[name]
                    valid_regime = evidence['n'] >= aturan['runtime']['kasus_kondisi_min'][str(h)]
                    ok = all(x['lolos'] is True for x in gerbang_harga(evidence['metrik'], h, level, aturan)+gerbang_interval(evidence['metrik'], level, aturan))
                    checks.append(cek(f'Bukti kondisi {name}', ok if valid_regime else None, evidence['n'], 'cukup dan lolos batas tinggi'))
                checks.append(cek('Pemantauan prospektif ramalan terbit', None, 0, aturan['bukti']['tinggi']['prospektif_min_hari'][str(h)]))
            by_level[level] = checks
        result['per_horizon'][str(h)] = {'h': h, 'syarat': by_level, 'metrik': metrics, 'periode_validasi': periods,
                                         'periode_dilewati': skipped,
                                         'kondisi': conditions, 'kondisi_saat_ini': current,
                                         'arah': {'metrik': {l: direction[l]['metrik'] for l in direction},
                                                  'syarat': {l: direction[l]['syarat'] for l in direction}}}
        if bank and bank.prediksi(model, seri.n-1) is not None:
            o = seri.n-1
            p, baseline = bank.prediksi(model, o), bank.prediksi('naif', o)
            iv, base_iv = bank.interval(model, o), bank.interval('naif', o)
            result['_saat_terbit'][str(h)] = {'prediksi': float(p[h-1]),
                'bawah': round(float(p[h-1]*math.exp(iv[h-1][0]))) if iv else None,
                'atas': round(float(p[h-1]*math.exp(iv[h-1][1]))) if iv else None,
                'naif': float(baseline[h-1]),
                'bawah_naif': float(baseline[h-1]*math.exp(base_iv[h-1][0])) if base_iv else None,
                'atas_naif': float(baseline[h-1]*math.exp(base_iv[h-1][1])) if base_iv else None}
    perbarui_level(result)
    return result


def firma_prospektif(konf, hv, sumber, aturan):
    code_hash = hashlib.sha256()
    for name in ('analisis.py', 'model_ml.py', 'musiman.py', 'trust_cabai.py'):
        code_hash.update((Path(__file__).parent/name).read_bytes())
    relevant = {k: konf.pengaturan.get(k) for k in ('analisis', 'validasi', 'jendela_hari_raya', 'hari_pencatatan', 'kualitas')}
    return fingerprint({'policy': aturan, 'implementasi': code_hash.hexdigest(), 'model': hv.model_terpilih,
                        'pengaturan': relevant, 'kalender': [a.__dict__ | {'tanggal': a.tanggal.isoformat()} for a in konf.kalender],
                        'kode': hv.trust_cabai['kode'], 'wilayah': sumber.get('kode_wilayah'), 'sumber': sumber.get('kode_sumber')})


def baca_buku(path):
    if not path.exists():
        return {'versi': 1, 'ramalan': []}, None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('versi') != 1 or not isinstance(data.get('ramalan'), list) or not all(isinstance(r, dict) for r in data['ramalan']):
            raise ValueError('skema buku prospektif tidak dikenal')
        return data, None
    except (ValueError, OSError) as e:
        return {'versi': 1, 'ramalan': []}, f'Buku prospektif tidak dapat dibaca: {e}'


def lengkapi(konf, hv, sumber, aturan, kode, mode_demo=False, catat=True, waktu=None):
    """Mencatat ramalan sebelum target terjadi; backfill dan demo tidak menjadi bukti prospektif."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    if kode not in KODE:
        raise ValueError('Kriteria cabai tidak berlaku untuk varian ini')
    now = waktu or datetime.now(timezone.utc)
    issued = now.astimezone(ZoneInfo('Asia/Jakarta')).date()
    result = hv.trust_cabai
    if not result:
        reason = 'Data demo bukan bukti produksi' if mode_demo else 'Sumber training resmi atau bukti historis belum layak'
        result = {'versi': aturan['versi'], 'kebijakan_sha256': fingerprint(aturan), 'tanggal_penilaian': konf.hari_ini.isoformat(),
                  'status_kebijakan': aturan['status'], 'skor_probabilitas': False, 'per_horizon': {}, 'fitur': {}}
        for h in ('1', '7', '30'):
            result['per_horizon'][h] = {'h': int(h), 'syarat': {l: [cek(reason, None)] for l in ('sedang', 'tinggi')},
                                       'arah': {'syarat': {l: [cek(reason, None)] for l in ('sedang', 'tinggi')}}}
        hv.trust_cabai = result
    result['kode'] = kode
    result['sumber'] = sumber
    result['mode_demo'] = mode_demo
    result['status_uji_umum'] = hv.validasi.get('status')
    result['skor_uji_umum'] = {'lolos': sum(x['lolos'] is True for x in hv.validasi.get('syarat', [])),
                              'total': len(hv.validasi.get('syarat', []))}
    current = result.pop('_saat_terbit', {})
    signature = firma_prospektif(konf, hv, sumber, aturan)
    path = konf.akar/'data/registry/trust_cabai_prospektif.json'
    book, error = baca_buku(path)
    actual = {t.isoformat(): float(y) for t, y in zip(hv.seri.tanggal, hv.seri.nilai) if t <= konf.hari_ini and np.isfinite(y) and y > 0}
    prospective = {h: [] for h in ('1', '7', '30')}
    for r in book['ramalan']:
        if r.get('firma') != signature or r.get('kode') != kode:
            continue
        try:
            timestamp = datetime.fromisoformat(r['diterbitkan_pada'])
            published = timestamp.astimezone(ZoneInfo('Asia/Jakarta')).date()
            target = date.fromisoformat(r['tanggal'])
            h = str(r['h'])
            if (timestamp.tzinfo is None or timestamp > now or published.isoformat() < aturan['tanggal_aktivasi']
                    or target <= published or (target-published).days != r['h'] or h not in prospective
                    or r['tanggal'] not in actual):
                continue
            point = {k: r.get(k) for k in ('prediksi', 'naif', 'bawah', 'atas', 'bawah_naif', 'atas_naif')}
            if not all(v is not None and math.isfinite(v) and v > 0 for v in point.values()):
                continue
            point.update(origin=published.toordinal(), tanggal=r['tanggal'], aktual=actual[r['tanggal']])
            prospective[h].append(point)
        except (KeyError, ValueError, TypeError):
            continue
    prospect_summary = {}
    allowed = bool(sumber.get('boleh_training') and sumber.get('kode_sumber') in ('BD-SP2KP', 'BD-PIHPS')
                   and sumber.get('kode_wilayah') and not mode_demo)
    for h, info in result['per_horizon'].items():
        p = next((p for p in hv.proyeksi if p['h'] == int(h)), None)
        expected = current.get(h)
        match = bool(p and expected and expected['bawah'] is not None and expected['atas'] is not None and
                     abs(p['prediksi']-expected['prediksi']) <= 1 and p['bawah'] == expected['bawah'] and p['atas'] == expected['atas'])
        for level in ('sedang', 'tinggi'):
            info['syarat'][level].extend([
                cek('Sumber resmi layak dan bukan demo', allowed,
                    sumber.get('kode_sumber'), 'SP2KP/PIHPS dengan QC dan wilayah yang benar'),
                cek('Interval yang diuji sesuai interval terbit', True if match else None, match, 'metode dan batas identik')])
            info['arah']['syarat'][level].append(cek('Sumber resmi layak dan bukan demo', allowed))
        pts = nonoverlap(prospective[h], int(h))
        distinct = len({p['origin'] for p in prospective[h]})
        minimum = aturan['bukti']['tinggi']['prospektif_min_hari'][h]
        m = metrik(pts)
        checks = gerbang_harga(m, int(h), 'tinggi', aturan)+gerbang_interval(m, 'tinggi', aturan)
        passed = distinct >= minimum and all(x['lolos'] is True for x in checks) and error is None
        for s in info['syarat']['tinggi']:
            if s['syarat'] == 'Pemantauan prospektif ramalan terbit':
                s.update(lolos=passed, nilai=distinct, target=minimum)
        if not any(s['syarat'] == 'Pemantauan prospektif ramalan terbit' for s in info['syarat']['tinggi']):
            info['syarat']['tinggi'].append(cek('Pemantauan prospektif ramalan terbit', passed, distinct, minimum))
        dm = metrik_arah(pts, int(h), aturan)
        info['arah']['basis'] = {l: 'holdout_retrospektif' for l in ('sedang', 'tinggi')}
        info['arah']['prospektif'] = dm
        for level in ('sedang', 'tinggi'):
            support = bool(dm and all(n >= aturan['arah'][level]['kasus_per_kelas_min'] for n in dm['kasus_per_kelas'].values()))
            if support:
                # Bukti terbit dapat lebih panjang daripada holdout harga, terutama pada H+30.
                info['arah']['basis'][level] = 'ramalan_terbit_prospektif'
                info['arah']['metrik'][level] = dm
                info['arah']['syarat'][level] = gerbang_data(result['data'], level, aturan)+gerbang_arah(dm, level, aturan)+[
                    cek('Sumber resmi layak dan bukan demo', allowed), cek('Buku prospektif dapat diverifikasi', error is None)]
        direction_passed = distinct >= minimum and error is None and all(x['lolos'] is True for x in gerbang_arah(dm, 'tinggi', aturan))
        for s in info['arah']['syarat']['tinggi']:
            if s['syarat'] == 'Pemantauan prospektif arah ramalan terbit':
                s.update(lolos=direction_passed, nilai=distinct, target=minimum)
        if not any(s['syarat'] == 'Pemantauan prospektif arah ramalan terbit' for s in info['arah']['syarat']['tinggi']):
            info['arah']['syarat']['tinggi'].append(cek('Pemantauan prospektif arah ramalan terbit', direction_passed, distinct, minimum))
        prospect_summary[h] = {'hari_terbit_dengan_aktual': distinct, 'origin_nonoverlap': len(pts), 'metrik': m,
                               'target_hari': minimum, 'syarat': checks, 'galat_buku': error}
    result['prospektif'] = prospect_summary
    result['prospektif']['firma'] = signature
    can_record = (catat and allowed and konf.hari_ini == issued
                  and issued.isoformat() >= aturan['tanggal_aktivasi'] and error is None)
    if can_record:
        records = book['ramalan']
        ids = {r.get('id') for r in records}
        for h, expected in current.items():
            p = next((p for p in hv.proyeksi if p['h'] == int(h)), None)
            if not kode or not p or (date.fromisoformat(p['tanggal'])-issued).days != int(h):
                continue
            if any(expected.get(k) is None for k in ('naif', 'bawah_naif', 'atas_naif')):
                continue
            rid = f'{signature}:{kode}:{issued}:{h}'
            if rid not in ids:
                records.append({'id': rid, 'firma': signature, 'kode': kode, 'h': int(h), 'tanggal': p['tanggal'],
                                'diterbitkan_pada': now.isoformat(), 'prediksi': p['prediksi'], 'bawah': p['bawah'], 'atas': p['atas'],
                                'naif': expected['naif'], 'bawah_naif': expected['bawah_naif'], 'atas_naif': expected['atas_naif']})
                ids.add(rid)
        # Retensi tidak mengubah tanggal penerbitan atau mengganti ramalan yang sudah tercatat.
        cutoff = (issued-timedelta(days=aturan['runtime']['retensi_prospektif_hari'])).isoformat()
        book['ramalan'] = [r for r in records if isinstance(r.get('tanggal'), str) and r['tanggal'] >= cutoff]
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(book, ensure_ascii=False, indent=1, sort_keys=True, allow_nan=False)+'\n'
        if not path.exists() or path.read_text(encoding='utf-8') != text:
            temp = path.with_suffix('.tmp')
            try:
                temp.write_text(text, encoding='utf-8')
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
    result['prospektif']['pencatatan_aktif'] = bool(can_record)
    result['prospektif']['hari_penilaian_sama_dengan_waktu_terbit'] = konf.hari_ini == issued
    perbarui_level(result)
    if mode_demo:
        result['level_gabungan'] = 'belum_cukup_bukti'
        for h in result['per_horizon'].values():
            h['level'] = h['arah']['level'] = 'belum_cukup_bukti'

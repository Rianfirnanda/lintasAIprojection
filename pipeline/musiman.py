"""Regresi return langsung dengan kalender tujuan dan cuaca yang sudah teramati."""
from datetime import timedelta
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def siapkan(seri, acara, cuaca, terisi=None):
    n = seri.n
    y = np.asarray(seri.nilai if terisi is None else terisi, dtype=float)
    ly = np.log(np.maximum(y, 1))
    hari = seri.tanggal
    fitur = []
    kolom_cuaca = []
    for indikator in ('curah_hujan_mm', 'suhu_rata_c'):
        nilai = np.array([cuaca.get((t, indikator), np.nan) for t in hari])
        valid = np.isfinite(nilai)
        total = np.r_[0., np.cumsum(np.where(valid, nilai, 0.))]
        jumlah = np.r_[0, np.cumsum(valid)]
        for w in (7, 30):
            akhir = np.arange(n)
            awal = np.maximum(akhir - w, 0)
            cnt = jumlah[akhir] - jumlah[awal]
            kolom_cuaca += [(total[akhir] - total[awal]) / np.maximum(cnt, 1), cnt / w]
    for h in (1, 7, 14, 30):
        cols = []
        for harmonik in (1, 2):
            awal = np.array([2 * np.pi * t.timetuple().tm_yday / 365.25 for t in hari]) * harmonik
            akhir = np.array([2 * np.pi * (t + timedelta(days=h)).timetuple().tm_yday / 365.25 for t in hari]) * harmonik
            cols += [np.sin(akhir) - np.sin(awal), np.cos(akhir) - np.cos(awal)]
        # Nama tahun dan tahun Hijriah dilepas supaya hari raya yang sama lintas tahun berbagi koefisien.
        for nama in ('fitri', 'adha', 'natal', 'ramadan'):
            tanggal = [a.tanggal for a in acara if nama in a.nama.lower()]
            for lebar in (7, 21):
                def fase(t):
                    return max((np.exp(-0.5 * ((t - d).days / lebar) ** 2) for d in tanggal), default=0.)
                cols.append(np.array([fase(t + timedelta(days=h)) - fase(t) for t in hari]))
        for lag in (7, 30):
            ret = np.zeros(n)
            ret[lag:] = ly[lag:] - ly[:-lag]
            cols.append(np.nan_to_num(ret))
        tahun = np.zeros(n)
        if n > 365:
            tahun[365:n] = ly[h:n - 365 + h] - ly[:n - 365]
        cols.append(np.nan_to_num(tahun))
        # Cuaca hari origin belum tentu terbit saat prediksi dibuat. Gunakan observasi sampai H-1 saja.
        cols += kolom_cuaca
        fitur.append((h, np.column_stack(cols)))
    return {'seri': seri, 'log_harga': ly, 'teramati': np.isfinite(seri.nilai), 'fitur': dict(fitur)}


def prediksi(y, asal, h, konteks):
    data = konteks.get('_musim')
    if data is None:
        return np.full(h, y[-1])
    seri, ly = data['seri'], data['log_harga']
    o = (asal - seri.tanggal[0]).days
    if o < 730 or not np.isfinite(ly[o]):
        return np.full(h, y[-1])
    jangkar = {0: 0.}
    for hz, X in data['fitur'].items():
        if hz > max(h, 7):
            continue
        t = np.arange(max(30, o - 1460), o - hz + 1)
        valid = data['teramati'][t] & data['teramati'][t + hz] & np.isfinite(ly[t]) & np.isfinite(ly[t + hz])
        t = t[valid]
        if len(t) < 365:
            continue
        target = ly[t + hz] - ly[t]
        # Embargo pada validasi internal: target training harus sudah diketahui sebelum origin validasi.
        batas = max(0, len(t) - max(90, len(t) // 5))
        train = t[:batas][t[:batas] + hz < t[batas]]
        uji = t[batas:]
        model = make_pipeline(StandardScaler(), Ridge(alpha=20.))
        susut = 1.
        if len(train) >= 180 and len(uji) >= 30:
            model.fit(X[train], ly[train + hz] - ly[train])
            p = model.predict(X[uji])
            aktual = ly[uji + hz] - ly[uji]
            susut = min((0., .25, .5, .75, 1.), key=lambda w: np.mean(np.abs(w * p - aktual)))
        model.fit(X[t], target)
        jangkar[hz] = np.clip(susut * model.predict(X[o:o + 1])[0], -.4, .4)
    xs = sorted(jangkar)
    return y[-1] * np.exp(np.interp(np.arange(1, h + 1), xs, [jangkar[x] for x in xs]))

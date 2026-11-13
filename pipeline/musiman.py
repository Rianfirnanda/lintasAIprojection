"""Regresi return langsung dengan kalender tujuan dan cuaca yang sudah teramati."""
from datetime import timedelta
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def anomali_kausal(hari, cuaca, indikator, rata_rata):
    total, jumlah = {}, {}
    hasil = np.zeros(len(hari))
    for i, t in enumerate(hari):
        kemarin = t - timedelta(days=1)
        v = cuaca.get((kemarin, indikator))
        if v is not None and np.isfinite(v):
            total[kemarin.month] = total.get(kemarin.month, 0.) + v
            jumlah[kemarin.month] = jumlah.get(kemarin.month, 0) + 1
        if jumlah.get(t.month, 0) >= 10:
            hasil[i] = rata_rata[i] - total[t.month] / jumlah[t.month]
    return hasil


def fitur_regional(seri, ly, regional):
    hasil = []
    for wilayah in sorted(regional or {}):
        other = regional[wilayah]
        harga = dict(zip(other.tanggal, other.nilai))
        nilai = np.full(seri.n, np.nan)
        terakhir, tgl = None, None
        for i, t in enumerate(seri.tanggal):
            kemarin = t - timedelta(days=1)
            v = harga.get(kemarin)
            if v is not None and np.isfinite(v) and v > 0:
                terakhir, tgl = v, kemarin
            if tgl is not None and (kemarin - tgl).days <= 3:
                nilai[i] = terakhir
        lx = np.log(nilai)
        ret = np.zeros(seri.n)
        ret[7:] = np.nan_to_num(lx[7:] - lx[:-7])
        target_lag = np.r_[np.nan, ly[:-1]]
        spread = lx - target_lag
        relatif = np.zeros(seri.n)
        for i, v in enumerate(spread):
            bloc = spread[max(0, i-44):i+1]
            bloc = bloc[np.isfinite(bloc)]
            if np.isfinite(v) and len(bloc):
                relatif[i] = v - np.median(bloc)
        hasil += [ret, relatif, np.isfinite(spread).astype(float)]
    return hasil


def siapkan(seri, acara, cuaca, terisi=None, regional=None):
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
    kolom_anomali = []
    for i, indikator in enumerate(('curah_hujan_mm', 'suhu_rata_c')):
        kolom_anomali.append(anomali_kausal(hari, cuaca, indikator, kolom_cuaca[i*4]))
    kolom_cuaca += kolom_anomali
    kolom_regional = fitur_regional(seri, ly, regional)
    kelompok_fitur = {}
    for h in (1, 7, 14, 30):
        cols = []
        for harmonik in (1, 2):
            awal = np.array([2 * np.pi * t.timetuple().tm_yday / 365.25 for t in hari]) * harmonik
            akhir = np.array([2 * np.pi * (t + timedelta(days=h)).timetuple().tm_yday / 365.25 for t in hari]) * harmonik
            cols += [np.sin(akhir) - np.sin(awal), np.cos(akhir) - np.cos(awal)]
        # Nama tahun dan tahun Hijriah dilepas supaya hari raya yang sama lintas tahun berbagi koefisien.
        for nama in ('fitri', 'adha', 'natal', 'ramadan', 'tahun baru'):
            tanggal = [a.tanggal for a in acara if nama in a.nama.lower()
                       and (nama != 'tahun baru' or (a.tanggal.month, a.tanggal.day) == (1, 1))]
            for lebar in (7, 21):
                def fase(t):
                    return max((np.exp(-0.5 * ((t - d).days / lebar) ** 2) for d in tanggal), default=0.)
                cols.append(np.array([fase(t + timedelta(days=h)) - fase(t) for t in hari]))
            def pendekatan(t):
                return max((max(0., 1 - (d-t).days / 35) if 1 <= (d-t).days <= 35 else 0.
                            for d in tanggal), default=0.)
            cols.append(np.array([pendekatan(t + timedelta(days=h)) - pendekatan(t) for t in hari]))
        for lag in (7, 30):
            ret = np.zeros(n)
            ret[lag:] = ly[lag:] - ly[:-lag]
            cols.append(np.nan_to_num(ret))
        tahun = np.zeros(n)
        if n > 365:
            tahun[365:n] = ly[h:n - 365 + h] - ly[:n - 365]
        cols.append(np.nan_to_num(tahun))
        # Cuaca hari origin belum tentu terbit saat prediksi dibuat. Gunakan observasi sampai H-1 saja.
        kelompok_fitur['kalender'] = len(cols)
        cols += kolom_cuaca
        kelompok_fitur['cuaca'] = len(cols)
        cols += kolom_regional
        kelompok_fitur['regional'] = len(cols)
        fitur.append((h, np.column_stack(cols)))
    return {'seri': seri, 'log_harga': ly, 'teramati': np.isfinite(seri.nilai), 'fitur': dict(fitur), 'kelompok_fitur': kelompok_fitur,
            'tersedia': {'kalender': True, 'cuaca': any(np.any(v) for v in kolom_cuaca[1:8:2]),
                         'regional': any(np.any(v) for v in kolom_regional[2::3])}}


def prediksi(y, asal, h, konteks, tahap='cuaca'):
    data = konteks.get('_musim')
    if data is None:
        return np.full(h, y[-1])
    seri, ly = data['seri'], data['log_harga']
    o = (asal - seri.tanggal[0]).days
    if o < 730 or not np.isfinite(ly[o]):
        return np.full(h, y[-1])
    jangkar = {0: 0.}
    for hz, semua in data['fitur'].items():
        X = semua[:, :data['kelompok_fitur'][tahap]]
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

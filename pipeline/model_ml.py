"""Model machine learning direct multi-horizon untuk proyeksi harga (Challenger), sesuai Laporan Pengembangan Model:

  - Fitur dibangun ketat point-in-time dari riwayat harga sampai hari origin (tanpa data masa depan):
      return log terhadap lag 1, 2, 3, 7, 14, 21, 28, 30, 60, 90 hari; rata-rata, koefisien variasi, kuantil 10 dan 90 persen
      pada jendela 7, 14, 30, 60 hari (relatif terhadap harga origin); momentum; stabilitas (hari sejak harga berubah,
      jumlah perubahan 14 hari); kalender (hari dalam minggu, bulan, jarak ke hari raya berikutnya, fase H-14..H+3).
  - Target: log(harga t+h / harga t) untuk horizon jangkar 1, 7, 14, 30 hari (direct, bukan rekursif), sehingga galat
    tidak menumpuk. Horizon di antaranya diinterpolasi linear pada skala log. Prediksi return dibatasi [-0,4; 0,4].
  - Embargo sama dengan horizon: baris latih untuk horizon h hanya yang targetnya sudah terjadi sampai hari origin.
  - Tiga keluarga model: Ridge (regresi linear teregularisasi L2, alpha 10, fitur distandarkan), Gradient Boosting berbasis
    histogram (algoritma yang sama dengan LightGBM, implementasi scikit-learn), dan Random Forest.
Semua acak dikunci (random_state 42) agar hasil dapat diulang.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

LAG = (1, 2, 3, 7, 14, 21, 28, 30, 60, 90)
JENDELA = (7, 14, 30, 60)
JANGKAR_LINEAR = (1, 7, 14, 30)
JANGKAR_POHON = (7, 14, 30)
BATAS_RETURN = 0.4
MAKS_BARIS_LATIH = 900
MIN_BARIS_LATIH = 60


def _jendela(y: np.ndarray, w: int) -> np.ndarray:
    """Matriks (n, w): baris t berisi y[t-w+1..t]; baris awal yang kurang data diisi dengan nilai pertama."""
    pad = np.concatenate([np.full(w - 1, y[0]), y])
    return sliding_window_view(pad, w)


def fitur(y: np.ndarray, asal: date, acara: list | None = None) -> tuple[np.ndarray, list[str], int]:
    """Matriks fitur untuk setiap indeks t (baris t hanya memakai y[0..t]). Mengembalikan (X, nama_fitur, t_awal)."""
    n = len(y)
    ly = np.log(np.maximum(y, 1e-6))
    # Daftar lag dan jendela tetap (tidak bergantung panjang seri) supaya fitur awalan seri sama persis dengan fitur seri penuh.
    lag, jendela = list(LAG), list(JENDELA)
    kolom, nama = [], []
    for k in lag:
        r = np.zeros(n)
        if k < n:
            r[k:] = ly[k:] - ly[:-k]
        kolom.append(r)
        nama.append(f"ret_lag_{k}")
    for w in jendela:
        win = _jendela(y, w)
        rata = win.mean(axis=1)
        kolom += [np.log(rata / y), win.std(axis=1) / np.maximum(rata, 1e-6),
                  np.log(np.quantile(win, 0.1, axis=1) / y), np.log(np.quantile(win, 0.9, axis=1) / y)]
        nama += [f"rata_{w}", f"cv_{w}", f"q10_{w}", f"q90_{w}"]
    # stabilitas: hari sejak harga berubah dan jumlah perubahan 14 hari
    berubah = np.zeros(n, dtype=bool)
    berubah[1:] = np.abs(np.diff(y)) > 1e-9
    sejak = np.zeros(n)
    hit = 0
    for i in range(n):
        hit = 0 if berubah[i] else hit + 1
        sejak[i] = min(hit, 60) / 60
    kolom += [sejak, _jendela(berubah.astype(float), 14).mean(axis=1)]
    nama += ["hari_sejak_berubah", "frekuensi_berubah_14"]
    # kalender
    tgl0 = asal - timedelta(days=n - 1)
    hari = np.array([(tgl0 + timedelta(days=i)) for i in range(n)])
    dow = np.array([d.weekday() for d in hari])
    bln = np.array([d.month for d in hari])
    kolom += [np.sin(2 * math.pi * dow / 7), np.cos(2 * math.pi * dow / 7), np.sin(2 * math.pi * bln / 12), np.cos(2 * math.pi * bln / 12)]
    nama += ["dow_sin", "dow_cos", "bulan_sin", "bulan_cos"]
    if acara:
        tgl_acara = sorted({a.tanggal for a in acara})
        jarak = np.full(n, 60.0)
        fase = np.zeros(n)
        for i, d in enumerate(hari):
            berikut = next((t for t in tgl_acara if t >= d), None)
            if berikut is not None:
                jarak[i] = min((berikut - d).days, 60)
            dekat = min(((d - t).days for t in tgl_acara), key=abs, default=999)
            fase[i] = 1.0 if -14 <= dekat <= 3 else 0.0
        kolom += [jarak / 60, fase]
        nama += ["jarak_hari_raya", "fase_hari_raya"]
    X = np.column_stack(kolom)
    return X, nama, int(max(lag + jendela))


def buat_regresor(jenis: str):
    if jenis == "ridge":
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        return make_pipeline(StandardScaler(), Ridge(alpha=10.0))
    if jenis == "hgb":
        from sklearn.ensemble import HistGradientBoostingRegressor

        return HistGradientBoostingRegressor(max_iter=150, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=20,
                                             l2_regularization=1.0, random_state=42)
    if jenis == "rf":
        from sklearn.ensemble import RandomForestRegressor

        return RandomForestRegressor(n_estimators=80, max_depth=8, min_samples_leaf=5, max_features=0.5, n_jobs=-1, random_state=42)
    raise ValueError(jenis)


def fitur_tersimpan(y: np.ndarray, asal: date, acara: list | None, simpanan: dict | None) -> tuple[np.ndarray, int]:
    """Fitur untuk y. Bila `simpanan` memuat fitur seri penuh yang berawal pada tanggal yang sama, potong saja (fitur bersifat
    kausal: baris t hanya memakai y[0..t], jadi potongan awalan identik dengan menghitung ulang)."""
    awal = asal - timedelta(days=len(y) - 1)
    if simpanan is not None and awal in simpanan and len(simpanan[awal][0]) >= len(y):
        X, t0 = simpanan[awal]
        return X[:len(y)], t0
    X, _, t0 = fitur(y, asal, acara)
    return X, t0


def prediksi_direct(y: np.ndarray, asal: date, h: int, jenis: str, acara: list | None = None,
                    simpanan: dict | None = None) -> np.ndarray | None:
    """Prediksi harga h hari ke depan dari origin = hari terakhir y. None bila data tidak cukup (pemanggil memakai cara naif)."""
    if len(y) < 120 or float(np.std(np.diff(np.log(np.maximum(y, 1e-6))))) < 1e-9:
        return None
    X, t0 = fitur_tersimpan(y, asal, acara, simpanan)
    ly = np.log(np.maximum(y, 1e-6))
    n = len(y)
    jangkar = [a for a in (JANGKAR_LINEAR if jenis == "ridge" else JANGKAR_POHON) if a <= max(h, 7)]
    ret_jangkar = {0: 0.0}
    for a in jangkar:
        # embargo = horizon: target y[t+a] harus sudah terjadi (t+a <= n-1)
        t = np.arange(t0, n - a)
        if len(t) > MAKS_BARIS_LATIH:
            t = t[-MAKS_BARIS_LATIH:]
        if len(t) < MIN_BARIS_LATIH:
            continue
        target = ly[t + a] - ly[t]
        if float(np.std(target)) < 1e-12:
            ret_jangkar[a] = float(target.mean())
            continue
        m = buat_regresor(jenis)
        m.fit(X[t], target)
        ret_jangkar[a] = float(np.clip(m.predict(X[n - 1:n])[0], -BATAS_RETURN, BATAS_RETURN))
    if len(ret_jangkar) == 1:
        return None
    xs = np.array(sorted(ret_jangkar))
    ys = np.array([ret_jangkar[x] for x in xs])
    r = np.interp(np.arange(1, h + 1), xs, ys)  # di luar jangkar terakhir: nilai jangkar terakhir dipertahankan
    return y[-1] * np.exp(r)


def pentingnya_fitur(y: np.ndarray, asal: date, acara: list | None = None, h: int = 7) -> list[dict]:
    """Koefisien Ridge terstandar untuk horizon h: besar kontribusi tiap fitur (penjelasan, bukan SHAP)."""
    if len(y) < 120:
        return []
    X, nama, t0 = fitur(y, asal, acara)
    ly = np.log(np.maximum(y, 1e-6))
    t = np.arange(t0, len(y) - h)[-MAKS_BARIS_LATIH:]
    if len(t) < MIN_BARIS_LATIH:
        return []
    target = ly[t + h] - ly[t]
    if float(np.std(target)) < 1e-12:
        return []
    m = buat_regresor("ridge")
    m.fit(X[t], target)
    koef = m[-1].coef_
    urut = np.argsort(-np.abs(koef))
    total = float(np.sum(np.abs(koef))) or 1.0
    return [{"fitur": nama[i], "bobot_persen": round(float(abs(koef[i]) / total * 100), 1), "arah": "naik" if koef[i] > 0 else "turun"}
            for i in urut[:8]]

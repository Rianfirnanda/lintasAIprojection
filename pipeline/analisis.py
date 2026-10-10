"""Lapisan analisis: baseline, proyeksi, rolling-origin backtesting, interval prediksi, deteksi anomali, dan drift.

Menerapkan arsitektur Champion vs Challenger sesuai pedoman Bab 6 dan Laporan Pengembangan:
  Champion Baseline (transparan, stabil, hemat komputasi):
    naif          : harga terakhir (persistence baseline / pembanding utama)
    rata7         : rerata bergerak 7 hari terakhir (MA-7)
    holt_redam    : Holt linear trend dengan damping (pada log harga)
    ses           : Simple Exponential Smoothing (level-only)
    hari_raya     : naif x profil kenaikan historis sekitar hari raya (bila riwayat tersedia)
  Challenger (diadu secara walk-forward point-in-time anti-leakage):
    ml_challenger : direct multi-horizon point-in-time machine learning (lags, rolling stats, momentum)
    ensemble      : dynamic ensemble adaptif (kombinasi 50% baseline juara + 50% ML)

Syarat Promosi Challenger (Gerbang Bab 6):
  ML hanya menggantikan baseline jika sMAPE membaik >= 5%, menang di >= 8 dari 12 origin,
  MAE tidak memburuk > 2%, dan bias terkendali (<= 3% pangan pokok, <= 5% lainnya).
  Ensemble hanya aktif jika memperbaiki sMAPE >= 2% dari model tunggal terbaik.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

import numpy as np
from sklearn.linear_model import Ridge

from .konfigurasi import Acara


@dataclass
class SeriHarian:
    tanggal: list[date]
    nilai: np.ndarray  # NaN bila tidak ada observasi

    @property
    def n(self) -> int:
        return len(self.tanggal)

    def indeks(self, tgl: date) -> int:
        return (tgl - self.tanggal[0]).days


def bentuk_seri(pasangan: dict[date, float], akhir: date | None = None) -> SeriHarian | None:
    if not pasangan:
        return None
    mulai = min(pasangan)
    akhir = max(akhir or mulai, max(pasangan))
    n = (akhir - mulai).days + 1
    tanggal = [mulai + timedelta(days=i) for i in range(n)]
    nilai = np.full(n, np.nan)
    for t, v in pasangan.items():
        nilai[(t - mulai).days] = v
    return SeriHarian(tanggal, nilai)


def isi_celah(nilai: np.ndarray, maks: int) -> np.ndarray:
    """Forward-fill celah hingga `maks` hari. Celah lebih panjang dibiarkan NaN."""
    hasil = nilai.copy()
    terakhir = np.nan
    umur = 0
    for i, v in enumerate(nilai):
        if not np.isnan(v):
            terakhir, umur = v, 0
        else:
            umur += 1
            if not np.isnan(terakhir) and umur <= maks:
                hasil[i] = terakhir
    return hasil


# ---------------------------------------------------------------- model proyeksi

def _riwayat_valid(y: np.ndarray) -> np.ndarray:
    """Ambil segmen terakhir tanpa NaN (model butuh deret kontinu)."""
    idx = np.where(np.isnan(y))[0]
    return y[idx[-1] + 1:] if len(idx) else y


def model_naif(y: np.ndarray, asal: date, h: int, _k: dict) -> np.ndarray:
    return np.full(h, y[-1])


def model_rata7(y: np.ndarray, asal: date, h: int, _k: dict) -> np.ndarray:
    return np.full(h, float(np.mean(y[-7:])))


_GRID_HOLT = [(a, b, phi) for a in (0.2, 0.4, 0.6, 0.8) for b in (0.05, 0.15) for phi in (0.8, 0.95)]


def _holt(y: np.ndarray, a: float, b: float, phi: float) -> tuple[float, float, float]:
    level, tren, sse = y[0], 0.0, 0.0
    for obs in y[1:]:
        prediksi = level + phi * tren
        galat = obs - prediksi
        sse += galat * galat
        level_baru = a * obs + (1 - a) * prediksi
        tren = b * (level_baru - level) + (1 - b) * phi * tren
        level = level_baru
    return sse, level, tren


def model_holt_redam(y: np.ndarray, asal: date, h: int, _k: dict) -> np.ndarray:
    log_y = np.log(y[-180:])
    if len(log_y) < 10:
        return model_naif(y, asal, h, _k)
    terbaik = min((_holt(log_y, *p) + p for p in _GRID_HOLT), key=lambda r: r[0])
    _, level, tren, _, _, phi = terbaik
    langkah = np.cumsum(phi ** np.arange(1, h + 1))
    return np.exp(level + langkah * tren)


def model_ses(y: np.ndarray, asal: date, h: int, _k: dict) -> np.ndarray:
    """Simple Exponential Smoothing (SES) level-only untuk harga berfluktuasi stabil."""
    log_y = np.log(y[-120:]) if len(y) >= 120 else np.log(y)
    if len(log_y) < 5:
        return model_naif(y, asal, h, _k)
    best_sse = float("inf")
    best_level = log_y[0]
    for alpha in (0.1, 0.2, 0.3, 0.5, 0.7, 0.9):
        lvl = log_y[0]
        sse = 0.0
        for obs in log_y[1:]:
            pred = lvl
            err = obs - pred
            sse += err * err
            lvl = alpha * obs + (1 - alpha) * lvl
        if sse < best_sse:
            best_sse = sse
            best_level = lvl
    return np.full(h, float(np.exp(best_level)))


def profil_hari_raya(seri: SeriHarian, acara: list[Acara], sebelum: int, sesudah: int) -> dict[int, float] | None:
    """Rasio harga pada H-k terhadap acuan normal (median H-44..H-15), dirata-rata antar hari raya historis."""
    terisi = isi_celah(seri.nilai, 7)
    rasio: dict[int, list[float]] = {}
    for a in acara:
        i0 = seri.indeks(a.tanggal)
        if i0 - 44 < 0 or i0 + sesudah >= seri.n:
            continue
        acuan_blok = terisi[i0 - 44:i0 - 14]
        acuan_blok = acuan_blok[~np.isnan(acuan_blok)]
        if len(acuan_blok) < 10:
            continue
        acuan = float(np.median(acuan_blok))
        for k in range(-sebelum, sesudah + 1):
            v = terisi[i0 + k]
            if not np.isnan(v):
                rasio.setdefault(k, []).append(v / acuan)
    if len(rasio) < sebelum:  # data tidak cukup
        return None
    return {k: float(np.median(v)) for k, v in rasio.items()}


def offset_hari_raya(tgl: date, acara: list[Acara], sebelum: int, sesudah: int) -> tuple[int, Acara] | None:
    for a in acara:
        k = (tgl - a.tanggal).days
        if -sebelum <= k <= sesudah:
            return k, a
    return None


def model_hari_raya(y: np.ndarray, asal: date, h: int, k: dict) -> np.ndarray:
    profil, acara, sebelum, sesudah = k.get("profil", {}), k.get("acara", []), k.get("sebelum", 14), k.get("sesudah", 3)
    if not profil:
        return model_naif(y, asal, h, k)

    def faktor(tgl: date) -> float:
        o = offset_hari_raya(tgl, acara, sebelum, sesudah)
        return profil.get(o[0], 1.0) if o else 1.0

    f_asal = faktor(asal)
    return np.array([y[-1] * faktor(asal + timedelta(days=j)) / f_asal for j in range(1, h + 1)])


def _buat_fitur_ml(y: np.ndarray, t: int) -> list[float]:
    """Fitur point-in-time ketat anti-leakage dari riwayat harga hingga indeks t."""
    m7 = float(np.mean(y[max(0, t - 6):t + 1]))
    s7 = float(np.std(y[max(0, t - 6):t + 1])) if t >= 6 else 0.0
    m28 = float(np.mean(y[max(0, t - 27):t + 1])) if t >= 14 else m7
    lag1 = float(y[t])
    lag2 = float(y[t - 1]) if t >= 1 else lag1
    lag3 = float(y[t - 2]) if t >= 2 else lag2
    lag7 = float(y[t - 6]) if t >= 6 else lag3
    lag14 = float(y[t - 13]) if t >= 13 else lag7
    return [
        lag1, lag2, lag3, lag7, lag14,
        m7, s7, m28,
        lag1 - m7,
        lag1 / (m7 + 1e-6),
        s7 / (m7 + 1e-6),
    ]


def model_ml_challenger(y: np.ndarray, asal: date, h: int, konteks: dict) -> np.ndarray:
    """Model Machine Learning direct multi-horizon berbasis Ridge log-returns dengan fitur anti-leakage."""
    if len(y) < 30 or np.all(y == y[0]) or np.std(y) < 1e-6:
        return model_naif(y, asal, h, konteks)

    X = [_buat_fitur_ml(y, t) for t in range(14, len(y))]
    X_arr = np.array(X)
    preds = np.zeros(h)
    last_feat = np.array([_buat_fitur_ml(y, len(y) - 1)])

    for step in range(1, h + 1):
        n_avail = len(y) - step - 14
        if n_avail >= 15:
            X_sub = X_arr[:n_avail]
            y_base_sub = np.maximum(1e-6, y[14:14 + n_avail])
            y_target_sub = np.maximum(1e-6, y[14 + step:14 + step + n_avail])
            y_log_ret = np.log(y_target_sub / y_base_sub)
            reg = Ridge(alpha=10.0)
            reg.fit(X_sub, y_log_ret)
            r_pred = float(reg.predict(last_feat)[0])
            r_pred = np.clip(r_pred, -0.4, 0.4)
            preds[step - 1] = max(1.0, y[-1] * math.exp(r_pred))
        else:
            preds[step - 1] = preds[step - 2] if step > 1 else y[-1]
    return preds


def model_ensemble(y: np.ndarray, asal: date, h: int, konteks: dict) -> np.ndarray:
    """Dynamic Ensemble: kombinasi adaptif 50% baseline (Damped Holt/Naive) + 50% ML Challenger."""
    f_base = model_holt_redam(y, asal, h, konteks)
    f_ml = model_ml_challenger(y, asal, h, konteks)
    return 0.5 * f_base + 0.5 * f_ml


MODEL: dict[str, Callable] = {
    "naif": model_naif,
    "rata7": model_rata7,
    "holt_redam": model_holt_redam,
    "ses": model_ses,
    "hari_raya": model_hari_raya,
    "ml_challenger": model_ml_challenger,
    "ensemble": model_ensemble,
}

NAMA_MODEL = {
    "naif": "Harga terakhir (Baseline Naive, jadi pembanding)",
    "rata7": "Rata-rata 7 hari terakhir (MA-7)",
    "holt_redam": "Holt linier dengan damping (tren melandai)",
    "ses": "Simple Exponential Smoothing (penghalusan eksponensial)",
    "hari_raya": "Harga terakhir ditambah pola hari raya sebelumnya",
    "ml_challenger": "Machine Learning Multi-Horizon (Challenger)",
    "ensemble": "Dynamic Ensemble (Kombinasi Adaptif Baseline + ML)",
}

MODEL_BASELINE = {"naif", "rata7", "holt_redam", "ses", "hari_raya"}
MODEL_CHALLENGER = {"ml_challenger", "ensemble"}


# ---------------------------------------------------------------- metrik

def smape(f: np.ndarray, a: np.ndarray) -> float:
    return float(np.mean(2 * np.abs(f - a) / (np.abs(a) + np.abs(f))) * 100)


def metrik(f: np.ndarray, a: np.ndarray, y_base: np.ndarray | None = None,
           ambang_gejolak_persen: float = 5.0, insample_diff: float | None = None) -> dict:
    if len(a) == 0:
        return {}
    res = {
        "smape": round(smape(f, a), 3),
        "mae": round(float(np.mean(np.abs(f - a))), 1),
        "rmse": round(float(np.sqrt(np.mean((f - a) ** 2))), 1),
        "bias_persen": round(float(np.mean(f - a) / np.mean(a) * 100), 3),
        "n": int(len(a)),
    }
    if insample_diff and insample_diff > 1e-6:
        res["mase"] = round(float(np.mean(np.abs(f - a))) / insample_diff, 3)

    if y_base is not None and len(y_base) == len(a) and len(a) > 0:
        da_diff = a - y_base
        df_diff = f - y_base
        arah_cocok = (
            ((da_diff > 0) & (df_diff > 0)) |
            ((da_diff < 0) & (df_diff < 0)) |
            ((np.abs(da_diff) < 1e-6) & (np.abs(df_diff) < 1e-6))
        )
        res["akurasi_arah"] = round(float(np.mean(arah_cocok) * 100), 2)

        # Klasifikasi Peringatan Dini Gejolak / Lonjakan Harga
        act_spike = (da_diff / np.maximum(y_base, 1.0) * 100) >= ambang_gejolak_persen
        pred_spike = (df_diff / np.maximum(y_base, 1.0) * 100) >= ambang_gejolak_persen
        tp = int(np.sum(pred_spike & act_spike))
        fp = int(np.sum(pred_spike & ~act_spike))
        fn = int(np.sum(~pred_spike & act_spike))
        tn = int(np.sum(~pred_spike & ~act_spike))

        if tp + fp > 0:
            precision = tp / (tp + fp)
        else:
            precision = 1.0 if fn == 0 else 0.0

        if tp + fn > 0:
            recall = tp / (tp + fn)
        else:
            recall = 1.0 if fp == 0 else 0.0

        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        res.update({
            "tp_gejolak": tp,
            "fp_gejolak": fp,
            "fn_gejolak": fn,
            "tn_gejolak": tn,
            "precision_gejolak": round(precision, 3),
            "recall_gejolak": round(recall, 3),
            "f1_gejolak": round(f1, 3),
        })
    return res


@dataclass
class HasilBacktest:
    model: str
    prediksi: np.ndarray  # semua pasangan (origin, h) yang punya aktual
    aktual: np.ndarray
    horizon: np.ndarray
    origin: np.ndarray
    tanggal: list[date] = field(default_factory=list)  # tanggal target tiap pasangan
    metrik: dict = field(default_factory=dict)
    asal_harga: np.ndarray = field(default_factory=lambda: np.array([]))
    metrik_per_origin: dict[int, dict] = field(default_factory=dict)
    metrik_per_horizon: dict[int, dict] = field(default_factory=dict)


def backtest(seri: SeriHarian, terisi: np.ndarray, nama_model: str, konteks: dict,
             horizon: int, jumlah_origin: int, jarak: int, minimal: int,
             ambang_gejolak_persen: float = 5.0) -> HasilBacktest | None:
    fungsi = MODEL[nama_model]
    akhir = seri.n - 1
    f_all, a_all, h_all, o_all, t_all, base_all = [], [], [], [], [], []
    origin_metrics: dict[int, dict] = {}

    for j in range(jumlah_origin):
        o = akhir - horizon - j * jarak
        if o < minimal:
            break
        y = _riwayat_valid(terisi[:o + 1])
        if len(y) < 14:
            continue
        y_o = float(terisi[o])
        f = fungsi(y, seri.tanggal[o], horizon, konteks)

        f_j, a_j, base_j = [], [], []
        for h in range(1, horizon + 1):
            a = seri.nilai[o + h]
            if not np.isnan(a):
                f_all.append(f[h - 1])
                a_all.append(a)
                h_all.append(h)
                o_all.append(j)
                t_all.append(seri.tanggal[o + h])
                base_all.append(y_o)
                f_j.append(f[h - 1])
                a_j.append(a)
                base_j.append(y_o)
        if a_j:
            origin_metrics[j] = metrik(np.array(f_j), np.array(a_j), np.array(base_j), ambang_gejolak_persen)

    if not a_all:
        return None

    f_arr = np.array(f_all)
    a_arr = np.array(a_all)
    h_arr = np.array(h_all)
    o_arr = np.array(o_all)
    b_arr = np.array(base_all)

    # In-sample difference for MASE calculation
    valid_terisi = terisi[~np.isnan(terisi)]
    diff_insample = float(np.mean(np.abs(np.diff(valid_terisi)))) if len(valid_terisi) > 1 else None

    # Metrik agregat
    m_all = metrik(f_arr, a_arr, b_arr, ambang_gejolak_persen, diff_insample)
    m_all["jumlah_origin"] = int(len(set(o_all)))

    # Metrik per-horizon direct (H+7, H+14, H+30, dsb.)
    metrik_per_horizon: dict[int, dict] = {}
    for hz in np.unique(h_arr):
        idx_hz = h_arr == hz
        if np.any(idx_hz):
            metrik_per_horizon[int(hz)] = metrik(
                f_arr[idx_hz], a_arr[idx_hz], b_arr[idx_hz],
                ambang_gejolak_persen, diff_insample
            )

    hasil = HasilBacktest(
        model=nama_model,
        prediksi=f_arr,
        aktual=a_arr,
        horizon=h_arr,
        origin=o_arr,
        tanggal=t_all,
        metrik=m_all,
        asal_harga=b_arr,
        metrik_per_origin=origin_metrics,
        metrik_per_horizon=metrik_per_horizon,
    )
    return hasil


def _kuantil_residu(res: np.ndarray, hz: np.ndarray, h: int, alfa: float) -> tuple[float, float] | None:
    """Kuantil konformal (split-conformal) residu log pada horizon h±2: cakupan >= 1-alfa bila residu dapat ditukar."""
    pilih = np.sort(res[np.abs(hz - h) <= 2])
    n = len(pilih)
    k_bawah = math.floor((n + 1) * alfa / 2)
    k_atas = math.ceil((n + 1) * (1 - alfa / 2))
    if k_bawah < 1 or k_atas > n:
        return None
    return float(pilih[k_bawah - 1]), float(pilih[k_atas - 1])


def interval_empiris(bt: HasilBacktest, horizon: int, tingkat: float, sigma_harian: float) -> list[tuple[float, float]]:
    """Kuantil residu log(aktual/prediksi) per horizon; cadangan: volatilitas harian x sqrt(h)."""
    alfa = 1 - tingkat
    res = np.log(bt.aktual / bt.prediksi)
    z = 1.6449 if abs(tingkat - 0.9) < 1e-9 else 1.96
    hasil = []
    for h in range(1, horizon + 1):
        q = _kuantil_residu(res, bt.horizon, h, alfa)
        if q is None:
            lebar = z * sigma_harian * math.sqrt(h)
            q = (-lebar, lebar)
        hasil.append(q)
    return hasil


def cakupan_interval(bt: HasilBacktest, tingkat: float) -> float | None:
    """Cakupan interval diuji leave-one-origin-out agar tidak mengukur data yang dipakai membentuk interval."""
    res = np.log(bt.aktual / bt.prediksi)
    alfa = 1 - tingkat
    kena = total = 0
    for j in np.unique(bt.origin):
        latih = bt.origin != j
        uji = ~latih
        for r, h in zip(res[uji], bt.horizon[uji]):
            q = _kuantil_residu(res[latih], bt.horizon[latih], h, alfa)
            if q is None:
                continue
            total += 1
            kena += int(q[0] <= r <= q[1])
    return round(kena / total * 100, 1) if total else None


# ---------------------------------------------------------------- anomali, perubahan, drift

@dataclass
class Anomali:
    tanggal: date
    nilai: float
    baseline: float
    deviasi_persen: float
    z: float
    arah: str
    keparahan: str


def baseline_bergulir(seri: SeriHarian, jendela: int, minimal: int = 10) -> np.ndarray:
    hasil = np.full(seri.n, np.nan)
    for i in range(seri.n):
        blok = seri.nilai[max(0, i - jendela):i]
        blok = blok[~np.isnan(blok)]
        if len(blok) >= minimal:
            hasil[i] = np.median(blok)
    return hasil


def rata_bergerak(seri: SeriHarian, jendela: int = 7) -> np.ndarray:
    hasil = np.full(seri.n, np.nan)
    for i in range(seri.n):
        blok = seri.nilai[max(0, i - jendela + 1):i + 1]
        blok = blok[~np.isnan(blok)]
        if len(blok):
            hasil[i] = blok.mean()
    return hasil


def deteksi_anomali(seri: SeriHarian, jendela: int, z_ambang: float, ambang_persen: float) -> tuple[list[Anomali], int]:
    """Robust z-score terhadap median bergulir. Kembalikan anomali dan jumlah titik yang dievaluasi."""
    anomali: list[Anomali] = []
    dievaluasi = 0
    for i in range(seri.n):
        x = seri.nilai[i]
        if np.isnan(x):
            continue
        blok = seri.nilai[max(0, i - jendela):i]
        blok = blok[~np.isnan(blok)]
        if len(blok) < 10:
            continue
        dievaluasi += 1
        b = float(np.median(blok))
        mad = float(np.median(np.abs(blok - b)))
        skala = max(mad, 0.005 * b) / 0.6745
        z = (x - b) / skala
        pct = (x / b - 1) * 100
        if abs(z) >= z_ambang and abs(pct) >= ambang_persen:
            tinggi = abs(pct) >= 2 * ambang_persen or abs(z) >= 2 * z_ambang
            anomali.append(Anomali(
                tanggal=seri.tanggal[i], nilai=float(x), baseline=b, deviasi_persen=round(pct, 2),
                z=round(z, 2), arah="naik" if pct > 0 else "turun",
                keparahan="tinggi" if tinggi else "sedang",
            ))
    return anomali, dievaluasi


def episode_anomali(anomali: list[Anomali], celah_maks: int = 3) -> list[list[Anomali]]:
    """Gabungkan hari-hari anomali berurutan (arah sama, celah <= 3 hari) menjadi satu episode."""
    episode: list[list[Anomali]] = []
    for a in anomali:
        if episode and episode[-1][-1].arah == a.arah and (a.tanggal - episode[-1][-1].tanggal).days <= celah_maks:
            episode[-1].append(a)
        else:
            episode.append([a])
    return episode


PERIODE_PERUBAHAN = {"harian": 1, "mingguan": 7, "bulanan": 30, "triwulanan": 91, "semesteran": 182, "tahunan": 365}


def _indeks_acuan(seri: SeriHarian) -> tuple[int | None, dict[str, int | None]]:
    """Indeks harga terakhir dan indeks titik pembanding untuk tiap periode perubahan."""
    idx = np.where(~np.isnan(seri.nilai))[0]
    if not len(idx):
        return None, {k: None for k in PERIODE_PERUBAHAN}
    i = idx[-1]
    acuan = {}
    for nama, hari in PERIODE_PERUBAHAN.items():
        if nama == "harian":
            sebelum = idx[idx < i]
            acuan[nama] = int(sebelum[-1]) if len(sebelum) and i - sebelum[-1] <= 7 else None
        else:
            kandidat = idx[(idx <= i - hari) & (idx >= i - hari - 7)]
            acuan[nama] = int(kandidat[-1]) if len(kandidat) else None
    return int(i), acuan


def perubahan(seri: SeriHarian) -> dict[str, float | None]:
    i, acuan = _indeks_acuan(seri)
    if i is None:
        return {k: None for k in PERIODE_PERUBAHAN}
    kini = seri.nilai[i]
    return {nama: round(float((kini / seri.nilai[j] - 1) * 100), 2) if j is not None else None for nama, j in acuan.items()}


def harga_acuan(seri: SeriHarian) -> dict[str, dict | None]:
    """Harga pembanding yang dipakai `perubahan` (mis. harga sebulan lalu) beserta tanggalnya, untuk ditampilkan."""
    _, acuan = _indeks_acuan(seri)
    return {nama: {"harga": round(float(seri.nilai[j])), "tanggal": seri.tanggal[j].isoformat()} if j is not None else None
            for nama, j in acuan.items()}


TEPI_PSI = np.array([-np.inf, -0.05, -0.02, -0.005, 0.005, 0.02, 0.05, np.inf])


def psi(referensi: np.ndarray, terkini: np.ndarray) -> float | None:
    """Population Stability Index atas log-return harian dengan bin tetap (tahan terhadap harga yang dibulatkan)."""
    if len(referensi) < 30 or len(terkini) < 15:
        return None
    p = np.histogram(referensi, TEPI_PSI)[0] / len(referensi)
    q = np.histogram(terkini, TEPI_PSI)[0] / len(terkini)
    p = np.clip(p, 1e-3, None)
    q = np.clip(q, 1e-3, None)
    return round(float(np.sum((q - p) * np.log(q / p))), 4)


def log_return(seri: SeriHarian) -> tuple[list[date], np.ndarray]:
    idx = np.where(~np.isnan(seri.nilai))[0]
    if len(idx) < 2:
        return [], np.array([])
    v = seri.nilai[idx]
    return [seri.tanggal[i] for i in idx[1:]], np.diff(np.log(v))


def drift(seri: SeriHarian, hari_terkini: int = 30, hari_referensi: int = 120) -> dict:
    tgl, r = log_return(seri)
    if not len(r):
        return {"psi": None}
    akhir = seri.tanggal[-1]
    batas_kini = akhir - timedelta(days=hari_terkini)
    batas_ref = batas_kini - timedelta(days=hari_referensi)
    kini = np.array([x for t, x in zip(tgl, r) if t > batas_kini])
    ref = np.array([x for t, x in zip(tgl, r) if batas_ref < t <= batas_kini])
    nilai_psi = psi(ref, kini)
    vol_ref = float(np.std(ref)) if len(ref) > 5 else None
    vol_kini = float(np.std(kini)) if len(kini) > 5 else None
    rasio = vol_kini / vol_ref if vol_ref and vol_kini is not None and vol_ref > 0 else None
    p_psi = p_vol = None
    if nilai_psi is not None:
        p_psi, p_vol = uji_permutasi(ref, kini)
    return {
        "psi": nilai_psi, "p_psi": p_psi,
        "volatilitas_referensi": round(vol_ref * 100, 3) if vol_ref is not None else None,
        "volatilitas_terkini": round(vol_kini * 100, 3) if vol_kini is not None else None,
        "rasio_volatilitas": round(rasio, 2) if rasio is not None else None, "p_volatilitas": p_vol,
    }


def uji_permutasi(ref: np.ndarray, kini: np.ndarray, ulangan: int = 999) -> tuple[float, float]:
    """p-value permutasi untuk PSI dan rasio volatilitas (PSI sampel kecil bias ke atas, jadi perlu uji)."""
    rng = np.random.default_rng(0)
    gabung = np.concatenate([ref, kini])
    n = len(ref)
    psi_obs = psi(ref, kini)
    vol_obs = abs(math.log(max(np.std(kini), 1e-9) / max(np.std(ref), 1e-9)))
    lebih_psi = lebih_vol = 0
    for _ in range(ulangan):
        acak = rng.permutation(gabung)
        a, b = acak[:n], acak[n:]
        lebih_psi += psi(a, b) >= psi_obs
        lebih_vol += abs(math.log(max(np.std(b), 1e-9) / max(np.std(a), 1e-9))) >= vol_obs
    return round((lebih_psi + 1) / (ulangan + 1), 4), round((lebih_vol + 1) / (ulangan + 1), 4)


def penurunan_metrik(bt: "HasilBacktest", ukuran_blok: int = 4) -> dict:
    """Drift model: sMAPE dua periode terbaru (blok 4 origin ~ 4 minggu) dibanding periode acuan sebelumnya."""
    def blok(k: int) -> float | None:
        pilih = (bt.origin >= k * ukuran_blok) & (bt.origin < (k + 1) * ukuran_blok)
        return smape(bt.prediksi[pilih], bt.aktual[pilih]) if pilih.sum() >= 10 else None

    p0, p1, acuan = blok(0), blok(1), blok(2)
    if p0 is None or p1 is None or not acuan:
        return {}
    return {
        "smape_acuan": round(acuan, 3),
        "penurunan_periode_terakhir_persen": round((p0 / acuan - 1) * 100, 1),
        "penurunan_periode_sebelumnya_persen": round((p1 / acuan - 1) * 100, 1),
    }


# ---------------------------------------------------------------- orkestrasi per varian

@dataclass
class HasilVarian:
    seri: SeriHarian
    baseline: np.ndarray
    rata7: np.ndarray
    model_terpilih: str | None
    metrik_model: dict
    perbaikan_vs_naif_persen: float | None
    cakupan_interval_persen: float | None
    proyeksi: list[dict]
    anomali: list[Anomali]
    titik_dievaluasi: int
    perubahan: dict
    drift: dict
    profil_hari_raya: dict[int, float] | None
    catatan: list[str]
    model_rekomendasi: str | None = None
    status_persetujuan: str = "tidak_ada_model"
    segmen: dict = field(default_factory=dict)
    harga_acuan: dict = field(default_factory=dict)
    metrik_horizon: dict = field(default_factory=dict)
    proyeksi_multi_horizon: dict = field(default_factory=dict)


def smape_segmen(bt: HasilBacktest, acara: list[Acara], sebelum: int, sesudah: int) -> dict:
    """sMAPE backtest dipisah: periode hari raya (H-sebelum..H+sesudah) vs normal (untuk uji stabilitas antar-segmen)."""
    hr = np.array([offset_hari_raya(t, acara, sebelum, sesudah) is not None for t in bt.tanggal], dtype=bool)
    hasil = {}
    for nama, pilih in (("normal", ~hr), ("hari_raya", hr)):
        hasil[nama] = round(smape(bt.prediksi[pilih], bt.aktual[pilih]), 3) if pilih.sum() >= 5 else None
    return hasil


def analisis_varian(seri: SeriHarian, kelompok: str, acara: list[Acara], pengaturan: dict,
                    model_disetujui: str | None = None, wajib_persetujuan: bool = False) -> HasilVarian:
    a = pengaturan["analisis"]
    s = pengaturan["sinyal"]
    jhr = pengaturan["jendela_hari_raya"]
    horizon = a["horizon_hari"]
    catatan: list[str] = []

    terisi = isi_celah(seri.nilai, a["maks_celah_isi_hari"])
    baseline = baseline_bergulir(seri, a["jendela_baseline_hari"])
    rata7 = rata_bergerak(seri)
    anomali, dievaluasi = deteksi_anomali(seri, a["jendela_baseline_hari"], s["z_ambang"], s["ambang_persen"][kelompok])
    profil = profil_hari_raya(seri, acara, jhr["sebelum"], jhr["sesudah"])
    konteks = {"profil": profil or {}, "acara": acara, "sebelum": jhr["sebelum"], "sesudah": jhr["sesudah"], "kelompok": kelompok}

    jumlah_obs = int(np.sum(~np.isnan(seri.nilai)))
    y_akhir = _riwayat_valid(terisi)
    hasil_bt: dict[str, HasilBacktest] = {}
    ambang_gejolak = float(s.get("ambang_persen", {}).get(kelompok, 5.0))

    if jumlah_obs >= a["minimal_hari_riwayat"] and len(y_akhir) >= 14:
        for nama in MODEL:
            if nama == "hari_raya" and not profil:
                continue
            bt = backtest(seri, terisi, nama, konteks, horizon, a["jumlah_origin_backtest"],
                          a["jarak_origin_hari"], a["minimal_hari_riwayat"], ambang_gejolak)
            if bt:
                hasil_bt[nama] = bt
    else:
        catatan.append(
            f"Riwayat baru {jumlah_obs} hari observasi (minimal {a['minimal_hari_riwayat']}); "
            "proyeksi memakai model naif tanpa evaluasi backtest."
        )

    # -------------------------------- Seleksi Champion vs Challenger Sesuai Bab 6
    if not hasil_bt:
        rekomendasi = "naif" if len(y_akhir) else None
        baseline_champion = rekomendasi
    else:
        # 1. Tentukan Champion Baseline
        kandidat_base = [m for m in MODEL_BASELINE if m in hasil_bt]
        if not kandidat_base:
            kandidat_base = ["naif"] if "naif" in hasil_bt else list(hasil_bt.keys())
        baseline_champion = min(kandidat_base, key=lambda m: hasil_bt[m].metrik["smape"])
        rekomendasi = baseline_champion

        # 2. Uji Challenger ML terhadap Baseline Champion
        if "ml_challenger" in hasil_bt and baseline_champion in hasil_bt and baseline_champion != "ml_challenger":
            bt_base = hasil_bt[baseline_champion]
            bt_ml = hasil_bt["ml_challenger"]
            base_smape = bt_base.metrik.get("smape", 0.0)
            ml_smape = bt_ml.metrik.get("smape", 0.0)
            base_mae = bt_base.metrik.get("mae", 0.0)
            ml_mae = bt_ml.metrik.get("mae", 0.0)

            # Hitung kemenangan per origin
            origin_bersama = set(bt_base.metrik_per_origin.keys()) & set(bt_ml.metrik_per_origin.keys())
            total_origin = len(origin_bersama)
            menang_ml = sum(
                1 for o_idx in origin_bersama
                if bt_ml.metrik_per_origin[o_idx].get("smape", 999) < bt_base.metrik_per_origin[o_idx].get("smape", 999)
            )
            # Syarat Bab 6: menang di >= 8 dari 12 origin (atau >= 67% jika origin < 12)
            ambang_menang = 8 if total_origin >= 12 else max(1, math.ceil(total_origin * 0.67))

            perbaikan_smape = ((base_smape - ml_smape) / base_smape * 100) if base_smape > 0 else 0.0
            degradasi_mae = ((ml_mae - base_mae) / base_mae * 100) if base_mae > 0 else 0.0
            bias_ml = abs(bt_ml.metrik.get("bias_persen", 0.0))
            batas_bias = 3.0 if kelompok == "pokok" else 5.0

            if (perbaikan_smape >= 5.0 and menang_ml >= ambang_menang and
                    degradasi_mae <= 2.0 and bias_ml <= batas_bias):
                rekomendasi = "ml_challenger"
                catatan.append(
                    f"Challenger ML lolos gerbang Bab 6: sMAPE membaik {perbaikan_smape:.1f}% vs baseline "
                    f"({baseline_champion}), menang {menang_ml}/{total_origin} origin, bias {bias_ml:.2f}%."
                )
            else:
                catatan.append(
                    f"Challenger ML belum mengungguli baseline secara meyakinkan "
                    f"(perbaikan: {perbaikan_smape:.1f}% vs target 5%, menang origin: {menang_ml}/{total_origin}); "
                    f"Champion bertahan pada '{baseline_champion}'."
                )

        # 3. Uji Challenger Dynamic Ensemble terhadap juara sementara
        if "ensemble" in hasil_bt and rekomendasi in hasil_bt and rekomendasi != "ensemble":
            bt_terpilih = hasil_bt[rekomendasi]
            bt_ens = hasil_bt["ensemble"]
            cur_smape = bt_terpilih.metrik.get("smape", 0.0)
            ens_smape = bt_ens.metrik.get("smape", 0.0)
            cur_mae = bt_terpilih.metrik.get("mae", 0.0)
            ens_mae = bt_ens.metrik.get("mae", 0.0)

            perbaikan_ens = ((cur_smape - ens_smape) / cur_smape * 100) if cur_smape > 0 else 0.0
            degradasi_mae_ens = ((ens_mae - cur_mae) / cur_mae * 100) if cur_mae > 0 else 0.0

            if perbaikan_ens >= 2.0 and degradasi_mae_ens <= 2.0:
                rekomendasi = "ensemble"
                catatan.append(
                    f"Dynamic Ensemble aktif: memperbaiki sMAPE {perbaikan_ens:.1f}% (target >= 2%) "
                    f"terhadap model tunggal terbaik '{bt_terpilih.model}'."
                )

    # Persetujuan manusia: model baseline (naif) selalu boleh; model lain perlu disetujui bila diwajibkan.
    if rekomendasi is None:
        status = "tidak_ada_model"
    elif rekomendasi == "naif" or model_disetujui == rekomendasi:
        status = "disetujui"
    else:
        status = "menunggu_persetujuan"
    terpilih = rekomendasi
    if wajib_persetujuan and status == "menunggu_persetujuan":
        terpilih = model_disetujui if model_disetujui in hasil_bt else "naif"
        catatan.append(f"Model rekomendasi '{rekomendasi}' belum disetujui; proyeksi memakai '{terpilih}'.")

    segmen: dict = {}
    if hasil_bt:
        naif = hasil_bt.get("naif")
        perbaikan = None
        if naif and naif.metrik["smape"] > 0 and terpilih in hasil_bt:
            perbaikan = round((naif.metrik["smape"] - hasil_bt[terpilih].metrik["smape"]) / naif.metrik["smape"] * 100, 2)
        cakupan = cakupan_interval(hasil_bt[terpilih], a["tingkat_interval"]) if terpilih in hasil_bt else None
        info_drift_model = penurunan_metrik(hasil_bt[terpilih]) if terpilih in hasil_bt else {}
        segmen = {"terpilih": smape_segmen(hasil_bt[terpilih], acara, jhr["sebelum"], jhr["sesudah"])} if terpilih in hasil_bt else {}
        if naif:
            segmen["naif"] = smape_segmen(naif, acara, jhr["sebelum"], jhr["sesudah"])
    else:
        perbaikan, cakupan = None, None
        info_drift_model = {}

    proyeksi: list[dict] = []
    if terpilih and len(y_akhir):
        asal = seri.tanggal[-1]
        f = MODEL[terpilih](y_akhir, asal, horizon, konteks)
        _, r = log_return(seri)
        sigma = float(np.std(r[-90:])) if len(r) > 5 else 0.05
        if terpilih in hasil_bt:
            iv = interval_empiris(hasil_bt[terpilih], horizon, a["tingkat_interval"], sigma)
        else:
            lebar = 1.6449 * max(sigma, 0.01)
            iv = [(-lebar * math.sqrt(h), lebar * math.sqrt(h)) for h in range(1, horizon + 1)]
        for h in range(1, horizon + 1):
            yhat = float(f[h - 1])
            proyeksi.append({
                "tanggal": (asal + timedelta(days=h)).isoformat(), "h": h,
                "prediksi": round(yhat), "bawah": round(yhat * math.exp(iv[h - 1][0])),
                "atas": round(yhat * math.exp(iv[h - 1][1])),
            })
        if np.isnan(seri.nilai[-1]):
            catatan.append("Tidak ada observasi pada tanggal terakhir; proyeksi berangkat dari nilai terakhir yang tersedia.")

    # Proyeksi ringkasan multi-horizon direct (H+7, H+14, H+30)
    proyeksi_multi = {
        7: next((p for p in proyeksi if p["h"] == 7), None),
        14: next((p for p in proyeksi if p["h"] == 14), None),
        30: next((p for p in proyeksi if p["h"] == 30), None),
    }

    metrik_horizon = {m: bt.metrik_per_horizon for m, bt in hasil_bt.items()}

    return HasilVarian(
        seri=seri, baseline=baseline, rata7=rata7, model_terpilih=terpilih,
        metrik_model={m: bt.metrik for m, bt in hasil_bt.items()},
        perbaikan_vs_naif_persen=perbaikan, cakupan_interval_persen=cakupan,
        proyeksi=proyeksi, anomali=anomali, titik_dievaluasi=dievaluasi,
        perubahan=perubahan(seri), drift={**drift(seri), **info_drift_model}, profil_hari_raya=profil, catatan=catatan,
        model_rekomendasi=rekomendasi, status_persetujuan=status, segmen=segmen, harga_acuan=harga_acuan(seri),
        metrik_horizon=metrik_horizon, proyeksi_multi_horizon=proyeksi_multi,
    )

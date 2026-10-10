"""Lapisan analisis: baseline, proyeksi, rolling-origin backtesting, interval prediksi, deteksi anomali, dan drift.

Menerapkan arsitektur Champion vs Challenger sesuai pedoman Bab 6 dan Laporan Pengembangan Model Prediksi:
  Champion Baseline (transparan, stabil, hemat komputasi):
    naif          : harga terakhir (persistence baseline / pembanding utama)
    naif_musiman7 : harga pada hari yang sama minggu lalu (Seasonal Naive-7)
    rata7         : rerata bergerak 7 hari terakhir (MA-7)
    holt_redam    : Holt linear trend dengan damping pada log harga; alpha, beta, phi ditala grid search per origin
    ses           : Simple Exponential Smoothing (level-only); alpha ditala per origin
    hari_raya     : naif x profil kenaikan historis H-14..H+3 sekitar hari raya (bila riwayat tersedia)
  Challenger (diadu secara walk-forward point-in-time anti-leakage, lihat model_ml.py):
    ml_challenger : Ridge direct multi-horizon (fitur lag, rolling, momentum, stabilitas, kalender)
    ml_hgb        : Gradient Boosting berbasis histogram (setara LightGBM)
    ml_rf         : Random Forest
    ensemble      : dynamic ensemble: baseline juara + ML terbaik, bobot dipilih dari galat backtest (0,3/0,5/0,7)
  Kandidat mengikuti kelas volatilitas (laporan, "Alur Pemilihan Model Berdasarkan Volatilitas"): kelas rendah menguji
  baseline dan Ridge; kelas sedang dan tinggi juga menguji Gradient Boosting, Random Forest, dan ensemble.

Syarat Promosi (Gerbang Bab 6):
  Baseline selain naif hanya menjadi juara bila menang terhadap naif di >= 8 dari 12 origin (>= 67% bila origin lebih sedikit).
  ML hanya menggantikan baseline jika sMAPE membaik >= 5%, menang di >= 8 dari 12 origin,
  MAE tidak memburuk > 2%, dan bias terkendali (<= 3% kelas rendah, <= 5% lainnya).
  Ensemble hanya aktif jika memperbaiki sMAPE >= 2% dari model tunggal terbaik dan MAE tidak memburuk > 2%.
"""

from __future__ import annotations

import math
from statistics import NormalDist
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

import numpy as np

from . import model_ml
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


def isi_celah(nilai: np.ndarray, maks: int, wajib: np.ndarray | None = None) -> np.ndarray:
    """Forward-fill celah hingga `maks` hari. Celah lebih panjang dibiarkan NaN. Bila `wajib` (penanda hari pencatatan) diberikan,
    yang dihitung hanya hari pencatatan yang kosong: akhir pekan dan libur pencatatan ikut terisi tanpa menambah umur celah."""
    hasil = nilai.copy()
    terakhir = np.nan
    umur = 0
    for i, v in enumerate(nilai):
        if not np.isnan(v):
            terakhir, umur = v, 0
        else:
            umur += 1 if wajib is None or wajib[i] else 0
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


# Ruang tuning sesuai Laporan Progres (alpha 0,1-0,5; beta 0,01-0,15; phi 0,80-0,98), dipilih per origin dari data latih saja.
_GRID_HOLT = [(a, b, phi) for a in (0.1, 0.25, 0.4, 0.5) for b in (0.01, 0.05, 0.15) for phi in (0.8, 0.88, 0.95, 0.98)]
_GRID_SES = (0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.7, 0.9)


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


def parameter_holt(y: np.ndarray) -> tuple[float, float, float, float, float] | None:
    """(alpha, beta, phi, level, tren) terbaik pada log harga 180 hari terakhir (SSE satu langkah terkecil)."""
    log_y = np.log(y[-180:])
    if len(log_y) < 10:
        return None
    sse, level, tren, a, b, phi = min((_holt(log_y, *p) + p for p in _GRID_HOLT), key=lambda r: r[0])
    return a, b, phi, level, tren


def model_holt_redam(y: np.ndarray, asal: date, h: int, _k: dict) -> np.ndarray:
    p = parameter_holt(y)
    if p is None:
        return model_naif(y, asal, h, _k)
    _, _, phi, level, tren = p
    langkah = np.cumsum(phi ** np.arange(1, h + 1))
    return np.exp(level + langkah * tren)


def parameter_ses(y: np.ndarray) -> tuple[float, float] | None:
    """(alpha, level) terbaik pada log harga 120 hari terakhir."""
    log_y = np.log(y[-120:]) if len(y) >= 120 else np.log(y)
    if len(log_y) < 5:
        return None
    terbaik = (float("inf"), _GRID_SES[0], log_y[0])
    for alpha in _GRID_SES:
        lvl, sse = log_y[0], 0.0
        for obs in log_y[1:]:
            err = obs - lvl
            sse += err * err
            lvl = alpha * obs + (1 - alpha) * lvl
        if sse < terbaik[0]:
            terbaik = (sse, alpha, lvl)
    return terbaik[1], float(terbaik[2])


def model_ses(y: np.ndarray, asal: date, h: int, _k: dict) -> np.ndarray:
    """Simple Exponential Smoothing (SES) level-only untuk harga berfluktuasi stabil."""
    p = parameter_ses(y)
    if p is None:
        return model_naif(y, asal, h, _k)
    return np.full(h, float(np.exp(p[1])))


def model_naif_musiman7(y: np.ndarray, asal: date, h: int, _k: dict) -> np.ndarray:
    """Seasonal Naive-7: harga t+j sama dengan harga pada hari yang sama di minggu terakhir yang sudah teramati."""
    if len(y) < 7:
        return model_naif(y, asal, h, _k)
    n = len(y)
    return np.array([y[n - 1 + j - 7 * math.ceil(j / 7)] for j in range(1, h + 1)])


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


def _model_ml(jenis: str) -> Callable:
    def prakira(y: np.ndarray, asal: date, h: int, konteks: dict) -> np.ndarray:
        p = model_ml.prediksi_direct(y, asal, h, jenis, konteks.get("acara"), konteks.get("_fitur"))
        return p if p is not None else model_naif(y, asal, h, konteks)
    return prakira


model_ml_challenger = _model_ml("ridge")
model_ml_hgb = _model_ml("hgb")
model_ml_rf = _model_ml("rf")


def model_ensemble(y: np.ndarray, asal: date, h: int, konteks: dict) -> np.ndarray:
    """Dynamic Ensemble: w x baseline juara + (1-w) x ML terbaik; komponen dan w dipilih dari backtest (konteks["ensemble"])."""
    e = konteks.get("ensemble") or {"a": "holt_redam", "b": "ml_challenger", "w": 0.5}
    return e["w"] * MODEL[e["a"]](y, asal, h, konteks) + (1 - e["w"]) * MODEL[e["b"]](y, asal, h, konteks)


MODEL: dict[str, Callable] = {
    "naif": model_naif,
    "naif_musiman7": model_naif_musiman7,
    "rata7": model_rata7,
    "holt_redam": model_holt_redam,
    "ses": model_ses,
    "hari_raya": model_hari_raya,
    "ml_challenger": model_ml_challenger,
    "ml_hgb": model_ml_hgb,
    "ml_rf": model_ml_rf,
    "ensemble": model_ensemble,
}

NAMA_MODEL = {
    "naif": "Harga terakhir (cara paling sederhana, jadi pembanding)",
    "naif_musiman7": "Harga hari yang sama minggu lalu (Seasonal Naive-7)",
    "rata7": "Rata-rata 7 hari terakhir (MA-7)",
    "holt_redam": "Tren melandai (Damped Holt)",
    "ses": "Penghalusan eksponensial (SES)",
    "hari_raya": "Harga terakhir ditambah pola hari raya sebelumnya",
    "ml_challenger": "Machine learning Ridge (regresi linear)",
    "ml_hgb": "Machine learning Gradient Boosting (setara LightGBM)",
    "ml_rf": "Machine learning Random Forest",
    "ensemble": "Gabungan cara statistik dan machine learning (Dynamic Ensemble)",
}

MODEL_BASELINE = {"naif", "naif_musiman7", "rata7", "holt_redam", "ses", "hari_raya"}
MODEL_ML = ("ml_challenger", "ml_hgb", "ml_rf")
MODEL_CHALLENGER = set(MODEL_ML) | {"ensemble"}
URUT_BASELINE = ("naif", "naif_musiman7", "rata7", "ses", "holt_redam", "hari_raya")  # urutan kesederhanaan bila seri
# Kandidat per kelas volatilitas (laporan: "Alur Pemilihan Model Berdasarkan Volatilitas").
KANDIDAT_KELAS = {
    "rendah": URUT_BASELINE + ("ml_challenger",),
    "sedang": URUT_BASELINE + MODEL_ML,
    "tinggi": URUT_BASELINE + MODEL_ML,
}
BOBOT_ENSEMBLE = (0.3, 0.5, 0.7)


# ---------------------------------------------------------------- metrik

def smape(f: np.ndarray, a: np.ndarray) -> float:
    return float(np.mean(2 * np.abs(f - a) / (np.abs(a) + np.abs(f))) * 100)


def metrik(f: np.ndarray, a: np.ndarray, y_base: np.ndarray | None = None,
           ambang_gejolak_persen: float = 5.0, insample_diff: float | np.ndarray | None = None) -> dict:
    if len(a) == 0:
        return {}
    res = {
        "smape": round(smape(f, a), 3),
        "mae": round(float(np.mean(np.abs(f - a))), 1),
        "rmse": round(float(np.sqrt(np.mean((f - a) ** 2))), 1),
        "bias_persen": round(float(np.mean(f - a) / np.mean(a) * 100), 3),
        "n": int(len(a)),
    }
    if insample_diff is not None:
        # MASE: galat absolut dibagi galat cara naif pada data latih (skala bisa berbeda per titik, mis. per horizon).
        skala = np.broadcast_to(np.asarray(insample_diff, dtype=float), f.shape)
        gal = np.abs(f - a)
        ada = skala > 1e-6
        # Skala nol (harga tidak pernah berubah): MASE hanya terdefinisi bila tebakan juga tepat.
        if ada.all() or (gal[~ada] < 1e-6).all():
            res["mase"] = round(float(np.mean(np.where(ada, gal / np.where(ada, skala, 1.0), 0.0))), 3)

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
    skala_mase: np.ndarray = field(default_factory=lambda: np.array([]))


def rangkum_backtest(nama_model: str, f_arr: np.ndarray, a_arr: np.ndarray, h_arr: np.ndarray, o_arr: np.ndarray,
                     t_all: list[date], b_arr: np.ndarray, skala: np.ndarray, ambang_gejolak_persen: float = 5.0) -> HasilBacktest:
    """Metrik agregat, per origin, dan per horizon dari pasangan (prediksi, aktual) hasil rolling-origin."""
    m_all = metrik(f_arr, a_arr, b_arr, ambang_gejolak_persen, skala)
    m_all["jumlah_origin"] = int(len(np.unique(o_arr)))
    per_origin = {int(j): metrik(f_arr[o_arr == j], a_arr[o_arr == j], b_arr[o_arr == j], ambang_gejolak_persen)
                  for j in np.unique(o_arr)}
    m_all["smape_median_origin"] = round(float(np.median([m["smape"] for m in per_origin.values()])), 3) if per_origin else None
    per_h = {int(hz): metrik(f_arr[h_arr == hz], a_arr[h_arr == hz], b_arr[h_arr == hz], ambang_gejolak_persen, skala[h_arr == hz])
             for hz in np.unique(h_arr)}
    return HasilBacktest(model=nama_model, prediksi=f_arr, aktual=a_arr, horizon=h_arr, origin=o_arr, tanggal=t_all, metrik=m_all,
                         asal_harga=b_arr, metrik_per_origin=per_origin, metrik_per_horizon=per_h, skala_mase=skala)


def gabung_ensemble(a: HasilBacktest, b: HasilBacktest, w: float, ambang_gejolak_persen: float = 5.0) -> HasilBacktest | None:
    """Backtest ensemble w*a + (1-w)*b dari prediksi kedua model pada pasangan (origin, horizon) yang sama (tanpa melatih ulang)."""
    if len(a.prediksi) != len(b.prediksi) or not (np.array_equal(a.origin, b.origin) and np.array_equal(a.horizon, b.horizon)):
        return None
    f = w * a.prediksi + (1 - w) * b.prediksi
    return rangkum_backtest("ensemble", f, a.aktual, a.horizon, a.origin, a.tanggal, a.asal_harga, a.skala_mase, ambang_gejolak_persen)


def backtest(seri: SeriHarian, terisi: np.ndarray, nama_model: str, konteks: dict,
             horizon: int, jumlah_origin: int, jarak: int, minimal: int,
             ambang_gejolak_persen: float = 5.0, geser_akhir: int = 0) -> HasilBacktest | None:
    """Rolling-origin point-in-time. `geser_akhir` menyisihkan sekian hari terakhir (holdout): tidak ada origin maupun target di sana."""
    fungsi = MODEL[nama_model]
    akhir = seri.n - 1 - geser_akhir
    f_all, a_all, h_all, o_all, t_all, base_all = [], [], [], [], [], []
    o_tertua = None

    for j in range(jumlah_origin):
        o = akhir - horizon - j * jarak
        if o < minimal:
            break
        y = _riwayat_valid(terisi[:o + 1])
        if len(y) < 14:
            continue
        y_o = float(terisi[o])
        f = fungsi(y, seri.tanggal[o], horizon, konteks)
        o_tertua = o if o_tertua is None else min(o_tertua, o)

        for h in range(1, horizon + 1):
            a = seri.nilai[o + h]
            if not np.isnan(a):
                f_all.append(f[h - 1])
                a_all.append(a)
                h_all.append(h)
                o_all.append(j)
                t_all.append(seri.tanggal[o + h])
                base_all.append(y_o)

    if not a_all:
        return None

    # Skala MASE per horizon: galat cara naif h hari pada data latih, yaitu data sampai origin tertua (point-in-time).
    h_arr = np.array(h_all)
    latih = terisi[:o_tertua + 1] if o_tertua is not None else terisi
    skala_h: dict[int, float] = {}
    for hz in np.unique(h_arr):
        hz = int(hz)
        d = np.abs(latih[hz:] - latih[:-hz]) if len(latih) > hz else np.array([])
        d = d[~np.isnan(d)]
        skala_h[hz] = float(np.mean(d)) if len(d) else 0.0
    skala = np.array([skala_h[int(hz)] for hz in h_arr])
    return rangkum_backtest(nama_model, np.array(f_all), np.array(a_all), h_arr, np.array(o_all), t_all, np.array(base_all), skala,
                            ambang_gejolak_persen)


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
    z = NormalDist().inv_cdf(1 - alfa / 2)
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


def cakupan_pit(res_kal: np.ndarray, h_kal: np.ndarray, res_uji: np.ndarray, h_uji: np.ndarray, alfa: float) -> float | None:
    """Cakupan interval tengah (1-alfa) dengan PIT acak (Czado, Gneiting & Held, 2009) yang tahan terhadap nilai kembar.

    Harga pangan sering tidak berubah berhari-hari, sehingga banyak selisih bernilai tepat nol. Pada data seperti itu cakupan
    biasa selalu 100% (interval berapa pun lebarnya memuat nol) dan syarat 75-85% tidak bisa dinilai. PIT acak membagi rata
    peluang pada nilai kembar, sehingga cakupan yang dihitung adalah cakupan yang diharapkan dari interval terkalibrasi.
    Untuk data tanpa nilai kembar hasilnya sama dengan cakupan biasa."""
    lo, hi = alfa / 2, 1 - alfa / 2
    kena = total = 0.0
    for r, h in zip(res_uji, h_uji):
        pilih = res_kal[np.abs(h_kal - h) <= 2]
        n = len(pilih)
        if n < 10:
            continue
        f_lo = float(np.sum(pilih < r - 1e-12)) / (n + 1)
        f_hi = (float(np.sum(pilih <= r + 1e-12)) + 1) / (n + 1)
        kena += max(0.0, min(f_hi, hi) - max(f_lo, lo)) / (f_hi - f_lo)
        total += 1
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
    holdout: dict | None = None
    validasi: dict = field(default_factory=dict)
    diagnostik: dict = field(default_factory=dict)
    kelengkapan_persen: float | None = None
    jumlah_obs: int = 0
    kelas_volatilitas: str = "sedang"
    parameter: dict = field(default_factory=dict)
    terbaik_per_horizon: dict = field(default_factory=dict)
    sumber_seri: dict = field(default_factory=dict)


def smape_segmen(bt: HasilBacktest, acara: list[Acara], sebelum: int, sesudah: int) -> dict:
    """sMAPE backtest dipisah: periode hari raya (H-sebelum..H+sesudah) vs normal (untuk uji stabilitas antar-segmen)."""
    hr = np.array([offset_hari_raya(t, acara, sebelum, sesudah) is not None for t in bt.tanggal], dtype=bool)
    hasil = {}
    for nama, pilih in (("normal", ~hr), ("hari_raya", hr)):
        hasil[nama] = round(smape(bt.prediksi[pilih], bt.aktual[pilih]), 3) if pilih.sum() >= 5 else None
    return hasil


# ---------------------------------------------------------------- validasi: holdout, uji statistik, diagnostik, status

VALIDASI_BAWAAN = {
    "minimal_hari_riwayat_valid": 730,
    "kelengkapan_min_persen": 95.0,
    "holdout_hari": 90,
    "jarak_origin_holdout_hari": 5,
    "origin_tinggi": 18,
    "ambang_smape_persen": {"volatil": 15.0, "protein": 10.0, "pokok": 5.0, "pabrikan": 5.0},
    "bias_maks_persen": {"rendah": 3.0, "sedang": 5.0, "tinggi": 5.0},
    "akurasi_arah_min_persen": {"tinggi": 60.0},
    "cakupan_min_persen": 75.0,
    "cakupan_maks_persen": 85.0,
    # Rentang prakiraan dikalibrasi dari residu origin mingguan selama setahun sebelum holdout (bukan hanya origin seleksi),
    # supaya mewakili beberapa musim harga. Model mesin belajar memakai setengahnya karena mahal dihitung.
    "origin_kalibrasi": 52,
    "jarak_origin_kalibrasi_hari": 7,
}
KELAS_VOLATILITAS = {"volatil": "tinggi", "protein": "sedang", "pokok": "rendah", "pabrikan": "rendah"}
# Laporan Pengembangan Model, tabel "Rekomendasi Model dan Validasi per Varian": Bawang Putih berkelas volatilitas sedang
# (sMAPE <= 10%) walaupun satu kelompok dengan cabai dan bawang merah.
KELAS_VARIAN = {"BWP01": "sedang"}
AMBANG_SMAPE_KELAS = {"rendah": 5.0, "sedang": 10.0, "tinggi": 15.0}


def kelas_volatilitas(kelompok: str, kode: str | None = None) -> str:
    return KELAS_VARIAN.get(kode or "", KELAS_VOLATILITAS.get(kelompok, "sedang"))


def pengaturan_validasi(pengaturan: dict) -> dict:
    v = {**VALIDASI_BAWAAN, **(pengaturan.get("validasi") or {})}
    for kunci in ("ambang_smape_persen", "bias_maks_persen", "akurasi_arah_min_persen"):
        v[kunci] = {**VALIDASI_BAWAAN[kunci], **(v.get(kunci) or {})}
    return v


def gabung_backtest(a: HasilBacktest, b: HasilBacktest | None) -> HasilBacktest:
    """Residu dua backtest digabung (untuk membentuk interval akhir dari seluruh bukti out-of-sample)."""
    if b is None:
        return a
    return HasilBacktest(model=a.model, prediksi=np.concatenate([a.prediksi, b.prediksi]), aktual=np.concatenate([a.aktual, b.aktual]),
                         horizon=np.concatenate([a.horizon, b.horizon]), origin=np.concatenate([a.origin, b.origin + 1000]),
                         tanggal=a.tanggal + b.tanggal, metrik=a.metrik)


def uji_diebold_mariano(galat_a: np.ndarray, galat_b: np.ndarray, horizon: int) -> dict:
    """Uji Diebold-Mariano (kerugian absolut, varians Newey-West dengan lag horizon-1, koreksi sampel kecil Harvey).
    d = |e_a| - |e_b|: statistik negatif berarti model A lebih baik. Pasangan diurutkan menurut waktu oleh pemanggil."""
    d = np.abs(galat_a) - np.abs(galat_b)
    n = len(d)
    if n < 8 or float(np.std(d)) < 1e-12:
        return {"n": int(n), "statistik": None, "p": None}
    dm = d - d.mean()
    lag = max(0, min(horizon - 1, n - 2))
    gamma0 = float(np.dot(dm, dm) / n)
    var = gamma0 + 2 * sum((1 - k / (lag + 1)) * float(np.dot(dm[k:], dm[:-k]) / n) for k in range(1, lag + 1))
    var = max(var, 1e-12) / n
    stat = float(d.mean() / math.sqrt(var))
    koreksi = math.sqrt(max((n + 1 - 2 * horizon + horizon * (horizon - 1) / n) / n, 1e-6))
    stat *= koreksi
    p = 2 * (1 - NormalDist().cdf(abs(stat)))  # pendekatan normal; sampel kecil membuat uji ini konservatif
    return {"n": int(n), "statistik": round(stat, 3), "p": round(p, 4)}


def kelengkapan_seri(seri: SeriHarian, hari_catat: list[int], jendela: int = 365, libur: set | None = None) -> float | None:
    """Persen hari pencatatan (mis. Senin-Jumat, di luar libur pencatatan) yang punya harga dalam jendela hari terakhir."""
    n = min(seri.n, jendela)
    libur = libur or set()
    wajib = lambda t: t.weekday() in hari_catat and t not in libur  # noqa: E731
    diharapkan = sum(1 for t in seri.tanggal[-n:] if wajib(t))
    ada = sum(1 for t, x in zip(seri.tanggal[-n:], seri.nilai[-n:]) if wajib(t) and not np.isnan(x))
    return round(ada / diharapkan * 100, 1) if diharapkan else None


def diagnostik_deret(seri: SeriHarian, terisi: np.ndarray) -> dict:
    """Diagnostik sesuai matriks metode: stasioneritas (ADF dan KPSS), kekuatan musiman (STL mingguan), rezim volatilitas,
    dan patahan struktural (PSI). Gagal dihitung -> nilai None, bukan karangan."""
    hasil: dict = {"adf_p": None, "kpss_p": None, "stasioner": None, "kekuatan_musiman": None, "rezim_volatilitas": None,
                   "patahan_struktural": None, "psi": None}
    y = _riwayat_valid(terisi)
    if len(y) < 60:
        return hasil
    ly = np.log(y)
    try:
        import warnings

        from statsmodels.tsa.seasonal import STL
        from statsmodels.tsa.stattools import adfuller, kpss

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if float(np.std(ly)) > 1e-9:
                hasil["adf_p"] = round(float(adfuller(ly, autolag="AIC")[1]), 4)
                hasil["kpss_p"] = round(float(kpss(ly, regression="c", nlags="auto")[1]), 4)
                hasil["stasioner"] = bool(hasil["adf_p"] < 0.05 and hasil["kpss_p"] > 0.05)
            if len(ly) >= 28 and float(np.std(ly)) > 1e-9:
                r = STL(ly, period=7, robust=True).fit()
                kuat = 1 - float(np.var(r.resid)) / max(float(np.var(r.seasonal + r.resid)), 1e-12)
                hasil["kekuatan_musiman"] = round(max(0.0, kuat), 3)
    except Exception:  # noqa: BLE001 - pustaka tidak ada atau seri degenerat
        pass
    ret = np.diff(ly)
    if len(ret) >= 120:
        sd30, sd_all = float(np.std(ret[-30:])), float(np.std(ret))
        rasio = sd30 / sd_all if sd_all > 1e-12 else None
        if rasio is not None:
            hasil["rezim_volatilitas"] = "tinggi" if rasio > 1.5 else "rendah" if rasio < 0.67 else "normal"
    ps = psi(y[:-90], y[-90:]) if len(y) >= 270 else None
    if ps is not None:
        hasil["psi"] = round(ps, 3)
        hasil["patahan_struktural"] = bool(ps > 0.25)
    return hasil


def nilai_validasi(kelompok: str, v: dict, jumlah_obs: int, kelengkapan: float | None, holdout: dict | None,
                   kode: str | None = None) -> dict:
    """Status model: "valid" hanya bila semua syarat Protokol Validasi terpenuhi pada holdout; selain itu "eksperimen"
    (tetap tampil, tetapi berlabel eksperimen dan tidak dipublikasikan sebagai proyeksi resmi)."""
    kelas = kelas_volatilitas(kelompok, kode)
    ambang = AMBANG_SMAPE_KELAS[kelas] if kode in KELAS_VARIAN else v["ambang_smape_persen"][kelompok]
    bias_maks = v["bias_maks_persen"][kelas]
    arah_min = v["akurasi_arah_min_persen"].get(kelas)
    syarat: list[dict] = []

    def cek(nama, ok, nilai, target):
        syarat.append({"syarat": nama, "lolos": None if ok is None else bool(ok), "nilai": nilai, "target": target})

    cek("Riwayat harga", jumlah_obs >= v["minimal_hari_riwayat_valid"], jumlah_obs, f">= {v['minimal_hari_riwayat_valid']} hari")
    cek("Kelengkapan data", None if kelengkapan is None else kelengkapan >= v["kelengkapan_min_persen"], kelengkapan,
        f">= {v['kelengkapan_min_persen']:g}%")
    if holdout:
        cek("sMAPE holdout", holdout["smape"] <= ambang, holdout["smape"], f"<= {ambang:g}%")
        cek("Bias holdout", abs(holdout["bias_persen"]) <= bias_maks, holdout["bias_persen"], f"<= {bias_maks:g}%")
        # Cakupan dinilai pada 52 origin mingguan setahun terakhir (kalibrasi selalu dari masa sebelumnya) bila tersedia: 13 origin
        # holdout yang saling tumpang tindih terlalu sedikit untuk menilai rentang 80% (galat bakunya sekitar 10-15 poin).
        # Cakupan holdout 90 hari tetap dilaporkan di holdout["cakupan_persen"].
        setahun = holdout.get("cakupan_setahun") or {}
        nilai_cak = setahun.get("persen", holdout["cakupan_persen"])
        cek("Cakupan interval 80% (setahun, PIT acak)" if setahun else "Cakupan interval 80% (PIT acak)",
            None if nilai_cak is None else v["cakupan_min_persen"] <= nilai_cak <= v["cakupan_maks_persen"], nilai_cak,
            f"{v['cakupan_min_persen']:g}-{v['cakupan_maks_persen']:g}%")
        cek("MASE holdout", None if holdout.get("mase") is None else holdout["mase"] < 1, holdout.get("mase"), "< 1")
        if holdout.get("model") != "naif":
            # Stabilitas (Protokol Validasi): menang terhadap cara naif pada sedikitnya 2/3 origin uji (8 dari 12).
            beda = holdout.get("origin_berbeda_vs_naif") or 0
            perlu = math.ceil(beda * 2 / 3)
            cek("Stabil antar-origin", holdout.get("menang_origin_vs_naif", 0) >= perlu,
                f"{holdout.get('menang_origin_vs_naif', 0)}/{beda}", f">= {perlu}/{beda} origin yang berbeda hasilnya")
        if arah_min is not None:
            cek("Akurasi arah", None if holdout.get("akurasi_arah") is None else holdout["akurasi_arah"] >= arah_min,
                holdout.get("akurasi_arah"), f">= {arah_min:g}%")
    else:
        cek("Holdout 90 hari", False, None, "tersedia")
    gagal = [s["syarat"] for s in syarat if s["lolos"] is False]
    belum = [s["syarat"] for s in syarat if s["lolos"] is None]
    status = "valid" if not gagal and not belum else "eksperimen"
    return {"status": status, "syarat": syarat, "gagal": gagal, "belum_dinilai": belum, "ambang_smape": ambang,
            "kelas_volatilitas": kelas}


def cakupan_bergulir(seri: SeriHarian, terisi: np.ndarray, model: str, konteks: dict, horizon: int, minimal: int,
                     tingkat: float, minggu_uji: int = 52, minggu_kalibrasi: int = 52) -> dict | None:
    """Cakupan rentang dinilai tiap minggu selama setahun terakhir: rentang untuk origin minggu j hanya dikalibrasi dari origin
    yang targetnya sudah terjadi sebelum origin j (point-in-time). Keterangan pendamping, bukan syarat status Valid: masa
    uji 90 hari terlalu pendek untuk menilai rentang bila tingkat gejolak harga sedang berubah."""
    if model not in MODEL_BASELINE:
        return None  # mesin belajar terlalu mahal untuk 100+ origin; cukup syarat holdout
    jeda = math.ceil(horizon / 7)
    bt = backtest(seri, terisi, model, konteks, horizon, minggu_uji + jeda + minggu_kalibrasi, 7, minimal)
    if bt is None:
        return None
    res = np.log(bt.aktual / bt.prediksi)
    alfa = 1 - tingkat
    cak = []
    for j in range(minggu_uji):
        uji = bt.origin == j
        kal = (bt.origin > j + jeda) & (bt.origin <= j + jeda + minggu_kalibrasi)
        if not uji.any() or kal.sum() < 100:
            continue
        c = cakupan_pit(res[kal], bt.horizon[kal], res[uji], bt.horizon[uji], alfa)
        if c is not None:
            cak.append(c)
    if len(cak) < 12:
        return None
    return {"persen": round(float(np.mean(cak)), 1), "minggu": len(cak),
            "minggu_dalam_75_85": int(sum(1 for c in cak if 75 <= c <= 85))}


def evaluasi_holdout(seri: SeriHarian, terisi: np.ndarray, model: str, konteks: dict, horizon: int, v: dict, minimal: int,
                     ambang_gejolak: float, bt_seleksi: HasilBacktest | None, tingkat: float) -> tuple[dict | None, HasilBacktest | None, HasilBacktest | None]:
    """Uji akhir pada `holdout_hari` terakhir (tidak dipakai memilih model). Mengembalikan (metrik, bt model, bt naif)."""
    hold, jarak = int(v["holdout_hari"]), int(v["jarak_origin_holdout_hari"])
    if hold < horizon + jarak or bt_seleksi is None:
        return None, None, None
    jumlah = (hold - horizon) // jarak + 1
    bt = backtest(seri, terisi, model, konteks, horizon, jumlah, jarak, minimal, ambang_gejolak)
    bt_naif = backtest(seri, terisi, "naif", konteks, horizon, jumlah, jarak, minimal, ambang_gejolak) if model != "naif" else bt
    if bt is None or bt_naif is None or len(np.unique(bt.origin)) < 3:
        return None, None, None
    # cakupan: interval dibentuk HANYA dari residu seleksi (sebelum holdout), lalu diuji pada holdout
    res_s = np.log(bt_seleksi.aktual / bt_seleksi.prediksi)
    res_h = np.log(bt.aktual / bt.prediksi)
    alfa = 1 - tingkat
    kena = total = 0
    for r, h in zip(res_h, bt.horizon):
        q = _kuantil_residu(res_s, bt_seleksi.horizon, int(h), alfa)
        if q is None:
            continue
        total += 1
        kena += int(q[0] <= r <= q[1])
    cak_pit = cakupan_pit(res_s, bt_seleksi.horizon, res_h, bt.horizon, alfa)
    m = dict(bt.metrik)
    mn = bt_naif.metrik
    menang, berbeda = _menang(bt, bt_naif)
    urut = np.lexsort((bt.horizon, bt.origin))
    dm = uji_diebold_mariano((bt.aktual - bt.prediksi)[urut], (bt_naif.aktual - bt_naif.prediksi)[urut], horizon) if model != "naif" else None
    lebar = [(math.exp(_kuantil_residu(res_s, bt_seleksi.horizon, h, alfa)[1]) - math.exp(_kuantil_residu(res_s, bt_seleksi.horizon, h, alfa)[0]))
             for h in (7, 14, horizon) if _kuantil_residu(res_s, bt_seleksi.horizon, h, alfa)]
    hasil = {
        "model": model, "hari": hold, "jumlah_origin": int(len(np.unique(bt.origin))), "n": m["n"], "smape": m["smape"], "mae": m["mae"],
        "mase": m.get("mase"), "bias_persen": m["bias_persen"], "akurasi_arah": m.get("akurasi_arah"),
        "cakupan_persen": cak_pit,
        "cakupan_mentah_persen": round(kena / total * 100, 1) if total else None,
        "porsi_harga_tetap_persen": round(float(np.mean(np.abs(res_h) < 1e-9)) * 100, 1) if len(res_h) else None,
        "lebar_interval_relatif_persen": round(100 * float(np.mean(lebar)), 1) if lebar else None,
        "smape_naif": mn["smape"], "mae_naif": mn["mae"], "perbaikan_vs_naif_persen":
            round((mn["smape"] - m["smape"]) / mn["smape"] * 100, 2) if mn["smape"] > 0 else None,
        "menang_origin_vs_naif": int(menang), "origin_berbeda_vs_naif": int(berbeda), "uji_dm": dm,
        "per_horizon": {str(h): {"n": bt.metrik_per_horizon[h]["n"], "smape": bt.metrik_per_horizon[h]["smape"],
                                 "mae": bt.metrik_per_horizon[h]["mae"], "bias_persen": bt.metrik_per_horizon[h]["bias_persen"]}
                        for h in (7, 14, 30) if h in bt.metrik_per_horizon},
        # prediksi H+7 lawan kenyataan selama masa uji, untuk grafik "model vs kenyataan"
        "titik_h7": [{"tanggal": t.isoformat(), "aktual": round(float(a)), "prediksi": round(float(p))}
                     for t, a, p, h in sorted(zip(bt.tanggal, bt.aktual, bt.prediksi, bt.horizon), key=lambda z: z[0]) if int(h) == 7],
    }
    return hasil, bt, bt_naif


def _menang(bt: HasilBacktest, acuan: HasilBacktest) -> tuple[int, int]:
    """(jumlah origin bt lebih tepat dari acuan, jumlah origin yang hasilnya berbeda). Origin seri (sMAPE sama persis, biasanya
    karena harga tidak berubah sehingga semua cara sama tepat) tidak dihitung sebagai menang maupun kalah."""
    bersama = set(bt.metrik_per_origin) & set(acuan.metrik_per_origin)
    beda = [j for j in bersama if abs(bt.metrik_per_origin[j]["smape"] - acuan.metrik_per_origin[j]["smape"]) > 1e-9]
    return sum(1 for j in beda if bt.metrik_per_origin[j]["smape"] < acuan.metrik_per_origin[j]["smape"]), len(beda)


def _skor(bt: HasilBacktest) -> float:
    """Skor seleksi: median sMAPE per origin (laporan: "pilih model dengan median sMAPE terendah")."""
    m = bt.metrik
    return m.get("smape_median_origin") if m.get("smape_median_origin") is not None else m["smape"]


def simpanan_fitur(terisi: np.ndarray, tanggal: list[date], acara: list[Acara]) -> dict:
    """Fitur ML per segmen data tanpa celah (kunci: tanggal awal segmen), dihitung sekali per varian lalu dipotong per origin."""
    hasil: dict = {}
    nan = np.isnan(terisi)
    i = 0
    while i < len(terisi):
        if nan[i]:
            i += 1
            continue
        j = i
        while j < len(terisi) and not nan[j]:
            j += 1
        if j - i >= 120:
            X, _, t0 = model_ml.fitur(terisi[i:j], tanggal[j - 1], acara)
            hasil[tanggal[i]] = (X, t0)
        i = j
    return hasil


def analisis_varian(seri: SeriHarian, kelompok: str, acara: list[Acara], pengaturan: dict,
                    model_disetujui: str | None = None, wajib_persetujuan: bool = False, kode: str | None = None,
                    libur_pasar: set | None = None) -> HasilVarian:
    a = pengaturan["analisis"]
    s = pengaturan["sinyal"]
    jhr = pengaturan["jendela_hari_raya"]
    horizon = a["horizon_hari"]
    catatan: list[str] = []

    # Isian maju dibatasi `maks_celah_isi_hari` HARI PENCATATAN (rancangan: <= 3 hari); akhir pekan dan libur pencatatan tidak dihitung.
    hari_catat = list(pengaturan.get("hari_pencatatan", [0, 1, 2, 3, 4]))
    libur = libur_pasar or set()
    wajib = np.array([t.weekday() in hari_catat and t not in libur for t in seri.tanggal], dtype=bool)
    terisi = isi_celah(seri.nilai, a["maks_celah_isi_hari"], wajib)
    baseline = baseline_bergulir(seri, a["jendela_baseline_hari"])
    rata7 = rata_bergerak(seri)
    anomali, dievaluasi = deteksi_anomali(seri, a["jendela_baseline_hari"], s["z_ambang"], s["ambang_persen"][kelompok])
    profil = profil_hari_raya(seri, acara, jhr["sebelum"], jhr["sesudah"])
    konteks = {"profil": profil or {}, "acara": acara, "sebelum": jhr["sebelum"], "sesudah": jhr["sesudah"], "kelompok": kelompok}
    kelas = kelas_volatilitas(kelompok, kode)
    kandidat = [m for m in KANDIDAT_KELAS[kelas] if a.get("model_pohon", True) or m not in ("ml_hgb", "ml_rf")]

    jumlah_obs = int(np.sum(~np.isnan(seri.nilai)))
    y_akhir = _riwayat_valid(terisi)
    hasil_bt: dict[str, HasilBacktest] = {}
    ambang_gejolak = float(s.get("ambang_persen", {}).get(kelompok, 5.0))
    v = pengaturan_validasi(pengaturan)
    # Seri volatil diuji dengan lebih banyak origin. Bila riwayat cukup, holdout final disisihkan: tidak dipakai memilih model.
    jumlah_origin = max(int(a["jumlah_origin_backtest"]), int(v["origin_tinggi"])) if kelompok == "volatil" else int(a["jumlah_origin_backtest"])
    jarak_sel = int(a["jarak_origin_hari"])
    hold = int(v["holdout_hari"])
    butuh = hold + horizon + (jumlah_origin - 1) * jarak_sel + int(a["minimal_hari_riwayat"])
    geser = hold if seri.n >= butuh else 0
    if not geser and jumlah_obs >= a["minimal_hari_riwayat"]:
        catatan.append(f"Riwayat belum cukup untuk menyisihkan holdout {hold} hari; evaluasi memakai seluruh riwayat dan model berstatus eksperimen.")

    if jumlah_obs >= a["minimal_hari_riwayat"] and len(y_akhir) >= 14:
        if any(m in MODEL_ML for m in kandidat):
            konteks["_fitur"] = simpanan_fitur(terisi, seri.tanggal, acara)
        for nama in kandidat:
            if nama == "hari_raya" and not profil:
                continue
            bt = backtest(seri, terisi, nama, konteks, horizon, jumlah_origin,
                          jarak_sel, a["minimal_hari_riwayat"], ambang_gejolak, geser)
            if bt:
                hasil_bt[nama] = bt
    else:
        catatan.append(
            f"Riwayat baru {jumlah_obs} hari observasi (minimal {a['minimal_hari_riwayat']}); "
            "proyeksi memakai model naif tanpa evaluasi backtest."
        )

    # -------------------------------- Seleksi Champion vs Challenger Sesuai Bab 6
    baseline_champion = None
    if not hasil_bt:
        rekomendasi = "naif" if len(y_akhir) else None
        baseline_champion = rekomendasi
    else:
        naif_bt = hasil_bt.get("naif")
        # 1. Champion baseline: median sMAPE terendah; selain naif wajib menang terhadap naif di >= 2/3 origin (8 dari 12).
        lolos_base = []
        for m in URUT_BASELINE:
            if m not in hasil_bt:
                continue
            if m == "naif" or naif_bt is None:
                lolos_base.append(m)
                continue
            menang, total = _menang(hasil_bt[m], naif_bt)
            if total and menang >= math.ceil(total * 2 / 3):
                lolos_base.append(m)
        if not lolos_base:
            lolos_base = [next(m for m in URUT_BASELINE if m in hasil_bt)] if any(m in hasil_bt for m in URUT_BASELINE) else list(hasil_bt)
        baseline_champion = min(lolos_base, key=lambda m: (_skor(hasil_bt[m]), URUT_BASELINE.index(m) if m in URUT_BASELINE else 99))
        rekomendasi = baseline_champion
        if baseline_champion != "naif" and naif_bt is not None:
            menang, total = _menang(hasil_bt[baseline_champion], naif_bt)
            catatan.append(f"Cara statistik '{baseline_champion}' lebih tepat dari harga terakhir di {menang} dari {total} titik uji.")

        # 2. Challenger ML terbaik diadu dengan champion baseline.
        ml_ada = [m for m in MODEL_ML if m in hasil_bt]
        ml_terbaik = min(ml_ada, key=lambda m: _skor(hasil_bt[m])) if ml_ada else None
        if ml_terbaik and baseline_champion in hasil_bt:
            bt_base, bt_ml = hasil_bt[baseline_champion], hasil_bt[ml_terbaik]
            base_s, ml_s = _skor(bt_base), _skor(bt_ml)
            perbaikan_smape = ((base_s - ml_s) / base_s * 100) if base_s > 0 else 0.0
            degradasi_mae = ((bt_ml.metrik["mae"] - bt_base.metrik["mae"]) / bt_base.metrik["mae"] * 100) if bt_base.metrik["mae"] > 0 else 0.0
            menang_ml, total_origin = _menang(bt_ml, bt_base)
            ambang_menang = 8 if total_origin >= 12 else max(1, math.ceil(total_origin * 0.67))
            bias_ml = abs(bt_ml.metrik.get("bias_persen", 0.0))
            batas_bias = 3.0 if kelas == "rendah" else 5.0
            if perbaikan_smape >= 5.0 and menang_ml >= ambang_menang and degradasi_mae <= 2.0 and bias_ml <= batas_bias:
                rekomendasi = ml_terbaik
                catatan.append(f"Machine learning '{ml_terbaik}' lolos gerbang Bab 6: sMAPE membaik {perbaikan_smape:.1f}% terhadap "
                               f"'{baseline_champion}', menang {menang_ml}/{total_origin} origin, bias {bias_ml:.2f}%.")
            else:
                catatan.append(f"Machine learning terbaik ('{ml_terbaik}') belum mengungguli cara statistik secara meyakinkan "
                               f"(perbaikan {perbaikan_smape:.1f}% dari target 5%, menang {menang_ml}/{total_origin} origin); "
                               f"juara tetap '{baseline_champion}'.")

        # 3. Dynamic Ensemble: champion baseline + ML terbaik, bobot dipilih dari backtest; aktif hanya bila membaik >= 2%.
        if ml_terbaik and kelas in ("sedang", "tinggi") and baseline_champion in hasil_bt and baseline_champion != ml_terbaik:
            calon = [(w, gabung_ensemble(hasil_bt[baseline_champion], hasil_bt[ml_terbaik], w, ambang_gejolak)) for w in BOBOT_ENSEMBLE]
            calon = [(w, bt) for w, bt in calon if bt is not None]
            if calon:
                w, bt_ens = min(calon, key=lambda x: _skor(x[1]))
                bt_kini = hasil_bt[rekomendasi]
                kini_s, ens_s = _skor(bt_kini), _skor(bt_ens)
                perbaikan_ens = ((kini_s - ens_s) / kini_s * 100) if kini_s > 0 else 0.0
                degradasi_mae_ens = ((bt_ens.metrik["mae"] - bt_kini.metrik["mae"]) / bt_kini.metrik["mae"] * 100) if bt_kini.metrik["mae"] > 0 else 0.0
                konteks["ensemble"] = {"a": baseline_champion, "b": ml_terbaik, "w": w}
                hasil_bt["ensemble"] = bt_ens
                if perbaikan_ens >= 2.0 and degradasi_mae_ens <= 2.0:
                    rekomendasi = "ensemble"
                    catatan.append(f"Dynamic Ensemble aktif: {round(w * 100)}% '{baseline_champion}' + {round((1 - w) * 100)}% "
                                   f"'{ml_terbaik}' memperbaiki sMAPE {perbaikan_ens:.1f}% (target >= 2%).")

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

    holdout, bt_hold = None, None
    kalibrasi: dict[str, HasilBacktest] = {}

    def bt_kalibrasi(model: str) -> HasilBacktest:
        if model not in kalibrasi:
            n_kal = int(v["origin_kalibrasi"]) // (2 if model in MODEL_CHALLENGER else 1)
            bt_k = backtest(seri, terisi, model, konteks, horizon, max(n_kal, jumlah_origin), int(v["jarak_origin_kalibrasi_hari"]),
                            a["minimal_hari_riwayat"], ambang_gejolak, geser) if model in hasil_bt else None
            kalibrasi[model] = bt_k if bt_k is not None and len(bt_k.aktual) >= len(hasil_bt[model].aktual) else hasil_bt[model]
        return kalibrasi[model]

    if geser and terpilih in hasil_bt:
        holdout, bt_hold, _ = evaluasi_holdout(seri, terisi, terpilih, konteks, horizon, v, a["minimal_hari_riwayat"], ambang_gejolak,
                                               bt_kalibrasi(terpilih), a["tingkat_interval"])
        dm = (holdout or {}).get("uji_dm") or {}
        if (holdout and terpilih in MODEL_CHALLENGER and dm.get("p") is not None and dm["p"] < 0.05 and (dm.get("statistik") or 0) > 0):
            catatan.append(f"Uji Diebold-Mariano pada holdout menunjukkan '{terpilih}' lebih buruk dari cara naif (p={dm['p']}); kembali ke '{baseline_champion}'.")
            rekomendasi = terpilih = baseline_champion
            holdout, bt_hold, _ = evaluasi_holdout(seri, terisi, terpilih, konteks, horizon, v, a["minimal_hari_riwayat"], ambang_gejolak,
                                                   bt_kalibrasi(terpilih), a["tingkat_interval"])
        if holdout is None:
            catatan.append("Holdout tidak dapat dihitung (origin tidak cukup); model berstatus eksperimen.")
        else:
            holdout["cakupan_setahun"] = cakupan_bergulir(seri, terisi, terpilih, konteks, horizon, a["minimal_hari_riwayat"],
                                                          a["tingkat_interval"])
    kelengkapan = kelengkapan_seri(seri, list(pengaturan.get("hari_pencatatan", [0, 1, 2, 3, 4])), libur=libur_pasar)
    validasi = nilai_validasi(kelompok, v, jumlah_obs, kelengkapan, holdout, kode) if terpilih else {"status": "eksperimen", "syarat": [],
                                                                                              "gagal": ["Tidak ada model"], "belum_dinilai": []}
    diagnostik = diagnostik_deret(seri, terisi)

    segmen: dict = {}
    if hasil_bt:
        naif = hasil_bt.get("naif")
        perbaikan = None
        if naif and naif.metrik["smape"] > 0 and terpilih in hasil_bt:
            perbaikan = round((naif.metrik["smape"] - hasil_bt[terpilih].metrik["smape"]) / naif.metrik["smape"] * 100, 2)
        cakupan = cakupan_interval(hasil_bt[terpilih], a["tingkat_interval"]) if terpilih in hasil_bt else None
        if holdout and (holdout.get("cakupan_setahun") or {}).get("persen") is not None:
            cakupan = holdout["cakupan_setahun"]["persen"]  # sama dengan yang dipakai syarat status Valid
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
            iv = interval_empiris(gabung_backtest(bt_kalibrasi(terpilih), bt_hold), horizon, a["tingkat_interval"], sigma)
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

    # Parameter hasil tuning pada data terakhir (untuk kartu model) dan model terbaik per horizon (laporan: champion per
    # varian dan horizon; produksi memakai satu champion per varian, sisanya informasi).
    parameter: dict = {}
    if len(y_akhir):
        ph = parameter_holt(y_akhir)
        if ph:
            parameter["holt_redam"] = {"alpha": ph[0], "beta": ph[1], "phi": ph[2]}
        ps = parameter_ses(y_akhir)
        if ps:
            parameter["ses"] = {"alpha": ps[0]}
        if konteks.get("ensemble"):
            parameter["ensemble"] = dict(konteks["ensemble"])
        if any(m in hasil_bt for m in MODEL_ML):
            parameter["fitur_penting_h7"] = model_ml.pentingnya_fitur(y_akhir, seri.tanggal[-1], acara, 7)
    terbaik_per_horizon = {}
    for hz in (7, 14, 30):
        ada = {m: bt.metrik_per_horizon[hz]["smape"] for m, bt in hasil_bt.items() if hz in bt.metrik_per_horizon}
        if ada:
            terbaik = min(ada, key=ada.get)
            terbaik_per_horizon[str(hz)] = {"model": terbaik, "smape": ada[terbaik]}

    return HasilVarian(
        seri=seri, baseline=baseline, rata7=rata7, model_terpilih=terpilih,
        metrik_model={m: bt.metrik for m, bt in hasil_bt.items()},
        perbaikan_vs_naif_persen=perbaikan, cakupan_interval_persen=cakupan,
        proyeksi=proyeksi, anomali=anomali, titik_dievaluasi=dievaluasi,
        perubahan=perubahan(seri), drift={**drift(seri), **info_drift_model}, profil_hari_raya=profil, catatan=catatan,
        model_rekomendasi=rekomendasi, status_persetujuan=status, segmen=segmen, harga_acuan=harga_acuan(seri),
        metrik_horizon=metrik_horizon, proyeksi_multi_horizon=proyeksi_multi,
        holdout=holdout, validasi=validasi, diagnostik=diagnostik, kelengkapan_persen=kelengkapan, jumlah_obs=jumlah_obs,
        kelas_volatilitas=kelas, parameter=parameter, terbaik_per_horizon=terbaik_per_horizon,
    )

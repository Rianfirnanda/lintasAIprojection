"""Lapisan analisis: baseline, proyeksi, rolling-origin backtesting, interval prediksi, deteksi anomali, dan drift.

Semua model sengaja dibuat sederhana, transparan, dan dapat diaudit:
  naif        : harga terakhir (model pembanding/baseline sesuai Rancangan Aksi Perubahan)
  rata7       : rerata 7 hari terakhir
  holt_redam  : Holt linear trend dengan damping (pada log harga)
  hari_raya   : naif x profil kenaikan historis sekitar hari raya (hanya bila riwayat hari raya tersedia)
Model terpilih = sMAPE backtest terendah. Keunggulan dibanding model naif dilaporkan terhadap target >= 10%.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

import numpy as np

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
    profil, acara, sebelum, sesudah = k["profil"], k["acara"], k["sebelum"], k["sesudah"]

    def faktor(tgl: date) -> float:
        o = offset_hari_raya(tgl, acara, sebelum, sesudah)
        return profil.get(o[0], 1.0) if o else 1.0

    f_asal = faktor(asal)
    return np.array([y[-1] * faktor(asal + timedelta(days=j)) / f_asal for j in range(1, h + 1)])


MODEL: dict[str, Callable] = {
    "naif": model_naif,
    "rata7": model_rata7,
    "holt_redam": model_holt_redam,
    "hari_raya": model_hari_raya,
}

NAMA_MODEL = {
    "naif": "Naif (harga terakhir, sebagai pembanding)",
    "rata7": "Rerata bergerak 7 hari",
    "holt_redam": "Holt damped trend (log harga)",
    "hari_raya": "Naif + profil hari raya historis",
}


# ---------------------------------------------------------------- metrik

def smape(f: np.ndarray, a: np.ndarray) -> float:
    return float(np.mean(2 * np.abs(f - a) / (np.abs(a) + np.abs(f))) * 100)


def metrik(f: np.ndarray, a: np.ndarray) -> dict:
    if len(a) == 0:
        return {}
    return {
        "smape": round(smape(f, a), 3),
        "mae": round(float(np.mean(np.abs(f - a))), 1),
        "rmse": round(float(np.sqrt(np.mean((f - a) ** 2))), 1),
        "bias_persen": round(float(np.mean(f - a) / np.mean(a) * 100), 3),
        "n": int(len(a)),
    }


@dataclass
class HasilBacktest:
    model: str
    prediksi: np.ndarray  # semua pasangan (origin, h) yang punya aktual
    aktual: np.ndarray
    horizon: np.ndarray
    origin: np.ndarray
    tanggal: list[date] = field(default_factory=list)  # tanggal target tiap pasangan
    metrik: dict = field(default_factory=dict)


def backtest(seri: SeriHarian, terisi: np.ndarray, nama_model: str, konteks: dict,
             horizon: int, jumlah_origin: int, jarak: int, minimal: int) -> HasilBacktest | None:
    fungsi = MODEL[nama_model]
    akhir = seri.n - 1
    f_all, a_all, h_all, o_all, t_all = [], [], [], [], []
    for j in range(jumlah_origin):
        o = akhir - horizon - j * jarak
        if o < minimal:
            break
        y = _riwayat_valid(terisi[:o + 1])
        if len(y) < 14:
            continue
        f = fungsi(y, seri.tanggal[o], horizon, konteks)
        for h in range(1, horizon + 1):
            a = seri.nilai[o + h]
            if not np.isnan(a):
                f_all.append(f[h - 1])
                a_all.append(a)
                h_all.append(h)
                o_all.append(j)
                t_all.append(seri.tanggal[o + h])
    if not a_all:
        return None
    hasil = HasilBacktest(nama_model, np.array(f_all), np.array(a_all), np.array(h_all), np.array(o_all), t_all)
    hasil.metrik = metrik(hasil.prediksi, hasil.aktual)
    hasil.metrik["jumlah_origin"] = int(len(set(o_all)))
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


def perubahan(seri: SeriHarian) -> dict[str, float | None]:
    idx = np.where(~np.isnan(seri.nilai))[0]
    if not len(idx):
        return {k: None for k in PERIODE_PERUBAHAN}
    i = idx[-1]
    kini = seri.nilai[i]
    hasil = {}
    for nama, hari in PERIODE_PERUBAHAN.items():
        if nama == "harian":
            sebelum = idx[idx < i]
            j = sebelum[-1] if len(sebelum) and i - sebelum[-1] <= 7 else None
        else:
            kandidat = idx[(idx <= i - hari) & (idx >= i - hari - 7)]
            j = kandidat[-1] if len(kandidat) else None
        hasil[nama] = round(float((kini / seri.nilai[j] - 1) * 100), 2) if j is not None else None
    return hasil


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
    konteks = {"profil": profil or {}, "acara": acara, "sebelum": jhr["sebelum"], "sesudah": jhr["sesudah"]}

    jumlah_obs = int(np.sum(~np.isnan(seri.nilai)))
    y_akhir = _riwayat_valid(terisi)
    hasil_bt: dict[str, HasilBacktest] = {}
    if jumlah_obs >= a["minimal_hari_riwayat"] and len(y_akhir) >= 14:
        for nama in MODEL:
            if nama == "hari_raya" and not profil:
                continue
            bt = backtest(seri, terisi, nama, konteks, horizon, a["jumlah_origin_backtest"],
                          a["jarak_origin_hari"], a["minimal_hari_riwayat"])
            if bt:
                hasil_bt[nama] = bt
    else:
        catatan.append(
            f"Riwayat baru {jumlah_obs} hari observasi (minimal {a['minimal_hari_riwayat']}); "
            "proyeksi memakai model naif tanpa evaluasi backtest."
        )

    rekomendasi = min(hasil_bt, key=lambda m: hasil_bt[m].metrik["smape"]) if hasil_bt else ("naif" if len(y_akhir) else None)
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
        if naif and naif.metrik["smape"] > 0:
            perbaikan = round((naif.metrik["smape"] - hasil_bt[terpilih].metrik["smape"]) / naif.metrik["smape"] * 100, 2)
        cakupan = cakupan_interval(hasil_bt[terpilih], a["tingkat_interval"])
        info_drift_model = penurunan_metrik(hasil_bt[terpilih])
        segmen = {"terpilih": smape_segmen(hasil_bt[terpilih], acara, jhr["sebelum"], jhr["sesudah"])}
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

    return HasilVarian(
        seri=seri, baseline=baseline, rata7=rata7, model_terpilih=terpilih,
        metrik_model={m: bt.metrik for m, bt in hasil_bt.items()},
        perbaikan_vs_naif_persen=perbaikan, cakupan_interval_persen=cakupan,
        proyeksi=proyeksi, anomali=anomali, titik_dievaluasi=dievaluasi,
        perubahan=perubahan(seri), drift={**drift(seri), **info_drift_model}, profil_hari_raya=profil, catatan=catatan,
        model_rekomendasi=rekomendasi, status_persetujuan=status, segmen=segmen,
    )

"""Proyeksi periodik: triwulanan (3 bulan), semesteran (6 bulan), dan tahunan (12 bulan ke depan).

Sasarannya rata-rata harga bulanan. Tiap periode punya tiga skenario: rendah, dasar, dan tinggi (kuantil 10%, 50%, 90%
dari sebaran galat backtest bulanan pada bulan ke-h yang sama; sama dengan interval 80%).
Periode baru ditampilkan bila riwayat memenuhi syaratnya (Protokol Validasi): triwulanan butuh 36 bulan, semesteran 48 bulan,
tahunan 60 bulan data bulanan lengkap. Bila belum, keluarannya "menunggu data" lengkap dengan sisa waktunya, tanpa angka karangan.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

import numpy as np

from . import analisis

PERIODE = {
    "triwulanan": {"nama": "Triwulanan", "bulan": 3, "minimal_bulan": 36, "satuan": "triwulan"},
    "semesteran": {"nama": "Semesteran", "bulan": 6, "minimal_bulan": 48, "satuan": "semester"},
    "tahunan": {"nama": "Tahunan", "bulan": 12, "minimal_bulan": 60, "satuan": "tahun"},
}
MIN_OBS_BULAN = 10  # bulan dianggap lengkap bila ada minimal 10 hari berharga (hari kerja)
MIN_RIWAYAT_MODEL = 15  # model musiman butuh lebih dari satu tahun
MODEL_BULANAN = ("naif", "rata3", "holt_redam", "musiman")
NAMA_MODEL = {"naif": "Rata-rata bulan terakhir (pembanding)", "rata3": "Rata-rata 3 bulan terakhir",
              "holt_redam": "Holt linier dengan damping", "musiman": "Pola musiman setahun lalu disesuaikan tingkat terkini"}


def bulan_str(y: int, m: int) -> str:
    return f"{y:04d}-{m:02d}"


def tambah_bulan(y: int, m: int, k: int) -> tuple[int, int]:
    i = y * 12 + (m - 1) + k
    return i // 12, i % 12 + 1


def rata_bulanan(seri: analisis.SeriHarian, tanggal_data: date) -> tuple[list[tuple[int, int]], np.ndarray]:
    """Rata-rata harga per bulan kalender untuk bulan yang lengkap (bulan berjalan tidak ikut)."""
    kumpul: dict[tuple[int, int], list[float]] = defaultdict(list)
    for t, x in zip(seri.tanggal, seri.nilai):
        if not np.isnan(x):
            kumpul[(t.year, t.month)].append(float(x))
    bulan = sorted(k for k in kumpul if k < (tanggal_data.year, tanggal_data.month) and len(kumpul[k]) >= MIN_OBS_BULAN)
    # hanya deretan bulan yang bersambung sampai bulan lengkap terakhir
    deret = []
    for k in bulan:
        if deret and tambah_bulan(*deret[-1], 1) != k:
            deret = []
        deret.append(k)
    return deret, np.array([float(np.mean(kumpul[k])) for k in deret])


def _prediksi(nama: str, y: np.ndarray, h: int) -> np.ndarray:
    """Prediksi rata-rata bulan ke-1..h di ruang log; y = riwayat sampai origin (positif)."""
    ly = np.log(y)
    n = len(ly)
    if nama == "naif":
        return np.exp(np.full(h, ly[-1]))
    if nama == "rata3":
        return np.exp(np.full(h, ly[-3:].mean()))
    if nama == "holt_redam":
        a, b, phi = 0.5, 0.2, 0.9
        level, trend = ly[0], 0.0
        for x in ly[1:]:
            prev = level
            level = a * x + (1 - a) * (prev + phi * trend)
            trend = b * (level - prev) + (1 - b) * phi * trend
        return np.exp(np.array([level + sum(phi ** i for i in range(1, k + 1)) * trend for k in range(1, h + 1)]))
    if nama == "musiman":
        if n < MIN_RIWAYAT_MODEL:
            return np.full(h, np.nan)
        geser = ly[-3:].mean() - ly[-15:-12].mean()  # perubahan tingkat 3 bulan terakhir dibanding setahun lalu
        hasil = []
        for k in range(1, h + 1):
            ref = n - 12 + ((k - 1) % 12)  # bulan yang sama setahun lalu, diulang bila horizon > 12
            hasil.append(ly[ref] + geser)
        return np.exp(np.array(hasil))
    raise KeyError(nama)


def backtest_bulanan(y: np.ndarray, nama: str, h_maks: int) -> dict:
    """Rolling-origin bulanan: untuk tiap origin o, ramalkan bulan o+1..o+h_maks bila ada kenyataannya."""
    p, a, hh, origin = [], [], [], []
    for o in range(MIN_RIWAYAT_MODEL - 1, len(y) - 1):
        f = _prediksi(nama, y[: o + 1], h_maks)
        for h in range(1, min(h_maks, len(y) - 1 - o) + 1):
            if np.isnan(f[h - 1]):
                continue
            p.append(f[h - 1]), a.append(y[o + h]), hh.append(h), origin.append(o)
    return {"p": np.array(p), "a": np.array(a), "h": np.array(hh), "o": np.array(origin)}


def _kuantil(res: np.ndarray, hh: np.ndarray, h: int, alfa: float) -> tuple[float, float] | None:
    pilih = res[np.abs(hh - h) <= 1]
    if len(pilih) < 8:
        return None
    return float(np.quantile(pilih, alfa)), float(np.quantile(pilih, 1 - alfa))


def _cakupan(res: np.ndarray, hh: np.ndarray, oo: np.ndarray, alfa: float) -> float | None:
    """Cakupan leave-one-origin-out: interval tiap titik dibentuk tanpa origin tersebut."""
    kena = total = 0
    for o in np.unique(oo):
        m = oo == o
        for r, h in zip(res[m], hh[m]):
            q = _kuantil(res[~m], hh[~m], int(h), alfa)
            if q is None:
                continue
            total += 1
            kena += int(q[0] <= r <= q[1])
    return round(kena / total * 100, 1) if total else None


def proyeksi_varian(y: np.ndarray, bulan: list[tuple[int, int]], h_maks: int, tingkat: float, kelompok: str, v: dict) -> dict:
    alfa = (1 - tingkat) / 2
    bt = {m: backtest_bulanan(y, m, h_maks) for m in MODEL_BULANAN}
    bt = {m: b for m, b in bt.items() if len(b["a"]) >= 12}
    if "naif" not in bt:
        return {"status": "eksperimen", "gagal": ["Riwayat bulanan terlalu pendek untuk diuji"], "belum_dinilai": []}
    smape = {m: analisis.smape(b["p"], b["a"]) for m, b in bt.items()}
    terbaik = min(smape, key=smape.get)
    # model selain pembanding hanya dipakai bila lebih baik minimal 2% dari pembanding
    model = terbaik if terbaik == "naif" or smape[terbaik] <= smape["naif"] * 0.98 else "naif"
    b = bt[model]
    res = np.log(b["a"] / b["p"])
    f = _prediksi(model, y, h_maks)
    sigma = float(np.std(np.diff(np.log(y)))) if len(y) > 3 else 0.05
    rendah, dasar, tinggi = [], [], []
    for h in range(1, h_maks + 1):
        q = _kuantil(res, b["h"], h, alfa)
        lo, hi = q if q else (-1.2816 * sigma * math.sqrt(h), 1.2816 * sigma * math.sqrt(h))
        dasar.append(round(float(f[h - 1])))
        rendah.append(round(float(f[h - 1] * math.exp(min(lo, 0.0)))))
        tinggi.append(round(float(f[h - 1] * math.exp(max(hi, 0.0)))))
    sm = analisis.smape(b["p"], b["a"])
    bias = float(np.mean(b["p"] - b["a"]) / np.mean(b["a"]) * 100)
    cak = _cakupan(res, b["h"], b["o"], alfa)
    perbaikan = (smape["naif"] - sm) / smape["naif"] * 100 if smape["naif"] > 0 else None
    kelas = analisis.KELAS_VOLATILITAS[kelompok]
    gagal, belum = [], []
    if sm > v["ambang_smape_persen"][kelompok]:
        gagal.append("sMAPE")
    if abs(bias) > v["bias_maks_persen"][kelas]:
        gagal.append("Bias")
    if cak is None:
        belum.append("Cakupan interval 80%")
    elif not v["cakupan_min_persen"] <= cak <= v["cakupan_maks_persen"]:
        gagal.append("Cakupan interval 80%")
    return {
        "model": model, "nama_model": NAMA_MODEL[model], "smape_per_model": {m: round(x, 3) for m, x in smape.items()},
        "dasar": dasar, "rendah": rendah, "tinggi": tinggi,
        "evaluasi": {"smape": round(sm, 3), "smape_naif": round(smape["naif"], 3), "bias_persen": round(bias, 3),
                     "cakupan_persen": cak, "perbaikan_vs_naif_persen": None if perbaikan is None else round(perbaikan, 2),
                     "n_titik": int(len(b["a"])), "n_origin": int(len(np.unique(b["o"])))},
        "status": "valid" if not gagal and not belum else "eksperimen", "gagal": gagal, "belum_dinilai": belum,
    }


def bentuk(konf, hasil_varian: dict, tanggal_data: date | None) -> dict:
    v = analisis.pengaturan_validasi(konf.pengaturan)
    tingkat = konf.pengaturan["analisis"]["tingkat_interval"]
    if not tanggal_data or not hasil_varian:
        return {"periode": {}, "tanggal_data": None}
    riwayat = {kode: rata_bulanan(hv.seri, tanggal_data) for kode, hv in hasil_varian.items()}
    n_bulan = min((len(b) for b, _ in riwayat.values()), default=0)
    keluaran = {}
    for kunci, info in PERIODE.items():
        h = info["bulan"]
        entri = {"nama": info["nama"], "bulan_per_periode": h, "minimal_bulan": info["minimal_bulan"], "bulan_tersedia": n_bulan,
                 "tersedia": n_bulan >= info["minimal_bulan"]}
        if not entri["tersedia"]:
            kurang = info["minimal_bulan"] - n_bulan
            entri["alasan"] = (f"Proyeksi {info['nama'].lower()} butuh {info['minimal_bulan']} bulan data harga lengkap; "
                               f"baru {n_bulan} bulan (kurang {kurang} bulan). Terisi otomatis setelah data cukup.")
            entri["varian"] = []
            keluaran[kunci] = entri
            continue
        y0, m0 = tambah_bulan(*max(b[-1] for b, _ in riwayat.values()), 1)
        entri["bulan_target"] = [bulan_str(*tambah_bulan(y0, m0, i)) for i in range(h)]
        entri["varian"] = []
        for kode, hv in hasil_varian.items():
            bulan, y = riwayat[kode]
            if len(bulan) < info["minimal_bulan"] or bulan[-1] != tambah_bulan(y0, m0, -1) or np.any(y <= 0):
                continue
            kelompok = konf.varian[kode].kelompok
            pv = proyeksi_varian(y, bulan, h, tingkat, kelompok, v)
            if "dasar" not in pv:
                entri["varian"].append({"kode": kode, **pv})
                continue
            rata = {k: round(float(np.mean(pv[k]))) for k in ("rendah", "dasar", "tinggi")}
            terakhir = y[-h:]
            entri["varian"].append({
                "kode": kode, **pv, "rata_periode": rata, "rata_periode_lalu": round(float(np.mean(terakhir))),
                "perubahan_vs_periode_lalu_persen": round((rata["dasar"] / float(np.mean(terakhir)) - 1) * 100, 2),
                "riwayat_bulanan": [{"bulan": bulan_str(*k), "rata": round(float(x))} for k, x in zip(bulan[-24:], y[-24:])]})
        keluaran[kunci] = entri
    return {"tanggal_data": tanggal_data.isoformat(), "tingkat_interval": tingkat, "periode": keluaran,
            "aturan": {"metode": "Rata-rata harga bulanan; model dipilih lewat backtest rolling-origin bulanan; skenario = kuantil 10/50/90 galat backtest.",
                       "skenario": "rendah = kuantil bawah, dasar = prediksi titik, tinggi = kuantil atas"}}

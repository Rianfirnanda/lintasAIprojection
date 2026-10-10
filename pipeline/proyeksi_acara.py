"""Proyeksi menjelang dan sesudah hari raya (Idul Fitri, Idul Adha, Natal).

Dua kelompok keluaran:
- Pra-hari raya: dari titik asal H-7 dan H-3, sasaran harga pada Hari H.
- Pasca-hari raya: dari Hari H, sasaran harga pada H+3, H+7, dan H+14.

Metode: rasio historis. Untuk tiap hari raya yang sudah lewat dihitung log-rasio harga sasaran terhadap harga titik asal.
Proyeksi = harga titik asal x median rasio dari hari raya lain sejenis; interval 80% dari sebaran selisih rasio terhadap median.
Evaluasi leave-one-event-out (satu hari raya disisihkan bergiliran) melawan cara naif (harga tidak berubah).
Proyeksi baru dibuat bila titik asalnya sudah tiba (data harga sudah sampai H-7), tidak pernah dari data masa depan.
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta

import numpy as np

from . import analisis

OFFSET_PRA = (-7, -3)
OFFSET_PASCA = (3, 7, 14)
MIN_ACARA = 3  # minimal hari raya sejenis berdata (Protokol Validasi)
MIN_ACARA_CAKUPAN = 8  # di bawah ini cakupan interval tidak bermakna untuk dinilai
MUNDUR_HARI = 4  # hari raya sering jatuh pada akhir pekan; PIHPS hanya mencatat hari kerja
KATA_JENIS = (("fitri", "Idul Fitri"), ("adha", "Idul Adha"), ("natal", "Natal"))


def jenis_acara(nama: str) -> str:
    n = nama.lower()
    for kata, jenis in KATA_JENIS:
        if kata in n:
            return jenis
    return re.sub(r"\s*\d+\s*H?$", "", nama).strip()


def kode_offset(k: int) -> str:
    return "H" if k == 0 else f"H{k:+d}"


class _Harga:
    """Harga harian dengan pencarian 'terakhir pada atau sebelum tanggal t' (maks MUNDUR_HARI hari)."""

    def __init__(self, seri: analisis.SeriHarian):
        self.peta = {t: float(v) for t, v in zip(seri.tanggal, seri.nilai) if not np.isnan(v)}

    def sampai(self, t: date, mundur: int = MUNDUR_HARI) -> tuple[float, date] | None:
        for d in range(mundur + 1):
            x = t - timedelta(days=d)
            if x in self.peta:
                return self.peta[x], x
        return None


def _pasangan(offset: int) -> tuple[int, int]:
    """(offset titik asal, offset sasaran) terhadap Hari H."""
    return (offset, 0) if offset < 0 else (0, offset)


def _kumpul(harga: _Harga, tanggal_hr: date, offset: int, tanggal_data: date) -> dict | None:
    """Log-rasio realisasi untuk satu hari raya dan satu offset, bila titik asal dan sasaran sama-sama sudah berdata."""
    oa, os_ = _pasangan(offset)
    t_asal, t_sasaran = tanggal_hr + timedelta(days=oa), tanggal_hr + timedelta(days=os_)
    if t_sasaran > tanggal_data:
        return None
    a, s = harga.sampai(t_asal), harga.sampai(t_sasaran)
    # titik asal harus benar-benar sebelum atau sama dengan sasaran dan tidak jauh dari tanggalnya
    if a is None or s is None or a[1] > s[1] or a[0] <= 0 or s[0] <= 0:
        return None
    return {"tanggal_hr": tanggal_hr, "asal_tanggal": a[1], "asal": a[0], "sasaran_tanggal": s[1], "sasaran": s[0],
            "lr": math.log(s[0] / a[0])}


def _prediksi(lr_latih: list[float], asal: float, tingkat: float) -> tuple[float, float, float]:
    med = float(np.median(lr_latih))
    sisa = np.array(lr_latih) - med
    alfa = (1 - tingkat) / 2
    bawah, atas = (float(np.quantile(sisa, alfa)), float(np.quantile(sisa, 1 - alfa))) if len(sisa) >= 2 else (0.0, 0.0)
    return asal * math.exp(med), asal * math.exp(med + min(bawah, 0.0)), asal * math.exp(med + max(atas, 0.0))


def evaluasi_offset(kejadian: list[dict], tingkat: float) -> dict | None:
    """Leave-one-event-out. `kejadian` = hasil `_kumpul` seluruh hari raya sejenis yang sudah berdata."""
    n = len(kejadian)
    if n < MIN_ACARA:
        return None
    f, a, naif, kena, rincian = [], [], [], 0, []
    for j, e in enumerate(kejadian):
        latih = [x["lr"] for i, x in enumerate(kejadian) if i != j]
        yhat, lo, hi = _prediksi(latih, e["asal"], tingkat)
        f.append(yhat)
        a.append(e["sasaran"])
        naif.append(e["asal"])
        k = lo <= e["sasaran"] <= hi
        kena += int(k)
        rincian.append({"tanggal_hr": e["tanggal_hr"].isoformat(), "asal": round(e["asal"]), "sasaran": round(e["sasaran"]),
                        "prediksi": round(yhat), "bawah": round(lo), "atas": round(hi), "dalam_interval": bool(k)})
    f, a, naif = np.array(f), np.array(a), np.array(naif)
    sm, sn = analisis.smape(f, a), analisis.smape(naif, a)
    return {"n_acara": n, "smape": round(sm, 3), "smape_naif": round(sn, 3),
            "perbaikan_vs_naif_persen": round((sn - sm) / sn * 100, 2) if sn > 0 else None,
            "bias_persen": round(float(np.mean(f - a) / np.mean(a) * 100), 3), "mae": round(float(np.mean(np.abs(f - a))), 1),
            "cakupan_persen": round(kena / n * 100, 1), "rincian": rincian}


def status_evaluasi(ev: dict | None, kelompok: str, v: dict) -> dict:
    """Valid hanya bila memenuhi Protokol Validasi; selain itu Eksperimen dengan alasan yang jelas."""
    if ev is None:
        return {"status": "eksperimen", "gagal": [f"Hari raya sejenis berdata kurang dari {MIN_ACARA}"], "belum_dinilai": []}
    kelas = analisis.KELAS_VOLATILITAS[kelompok]
    gagal, belum = [], []
    if ev["smape"] > v["ambang_smape_persen"][kelompok]:
        gagal.append("sMAPE")
    if abs(ev["bias_persen"]) > v["bias_maks_persen"][kelas]:
        gagal.append("Bias")
    if ev["perbaikan_vs_naif_persen"] is None or ev["perbaikan_vs_naif_persen"] <= 0:
        gagal.append("Tidak lebih baik dari cara naif")
    if ev["n_acara"] < MIN_ACARA_CAKUPAN:
        belum.append(f"Cakupan interval 80% (butuh {MIN_ACARA_CAKUPAN} hari raya, baru {ev['n_acara']})")
    elif not v["cakupan_min_persen"] <= ev["cakupan_persen"] <= v["cakupan_maks_persen"]:
        gagal.append("Cakupan interval 80%")
    return {"status": "valid" if not gagal and not belum else "eksperimen", "gagal": gagal, "belum_dinilai": belum}


def fase(hr: date, tanggal_data: date) -> str:
    if tanggal_data < hr + timedelta(days=OFFSET_PRA[0]):
        return "belum_dimulai"
    if tanggal_data < hr:
        return "pra"
    if tanggal_data <= hr + timedelta(days=OFFSET_PASCA[-1]):
        return "pasca"
    return "selesai"


def bentuk(konf, hasil_varian: dict, tanggal_data: date | None) -> dict:
    """Seluruh keluaran untuk proyeksi_acara.json."""
    v = analisis.pengaturan_validasi(konf.pengaturan)
    tingkat = konf.pengaturan["analisis"]["tingkat_interval"]
    hari_raya = sorted(konf.hari_raya(), key=lambda a: a.tanggal)
    if not tanggal_data or not hasil_varian:
        return {"tanggal_data": None, "acara": [], "evaluasi": [], "aturan": {}}
    offsets = OFFSET_PRA + OFFSET_PASCA

    harga = {kode: _Harga(hv.seri) for kode, hv in hasil_varian.items()}

    evaluasi_out, acara_out = [], []
    # sejarah per (varian, jenis, offset)
    sejarah: dict[tuple[str, str, int], list[dict]] = {}
    for kode in hasil_varian:
        for a in hari_raya:
            jenis = jenis_acara(a.nama)
            for off in offsets:
                e = _kumpul(harga[kode], a.tanggal, off, tanggal_data)
                if e:
                    sejarah.setdefault((kode, jenis, off), []).append(e)

    for kode, hv in hasil_varian.items():
        kelompok = konf.varian[kode].kelompok
        for jenis in sorted({jenis_acara(a.nama) for a in hari_raya}):
            per_offset = {}
            for off in offsets:
                ev = evaluasi_offset(sejarah.get((kode, jenis, off), []), tingkat)
                per_offset[kode_offset(off)] = {**(ev or {"n_acara": len(sejarah.get((kode, jenis, off), []))}),
                                                **status_evaluasi(ev, kelompok, v)}
            evaluasi_out.append({"kode": kode, "jenis": jenis, "offset": per_offset})

    # proyeksi aktif untuk hari raya yang titik asalnya sudah tiba, plus status hari raya terdekat yang belum dimulai
    for a in hari_raya:
        fs = fase(a.tanggal, tanggal_data)
        if fs == "selesai" and (tanggal_data - a.tanggal).days > 60:
            continue
        if fs == "belum_dimulai" and (a.tanggal - tanggal_data).days > 120:
            continue
        jenis = jenis_acara(a.nama)
        entri = {"nama": a.nama, "tanggal": a.tanggal.isoformat(), "status_kalender": a.status, "jenis": jenis, "fase": fs,
                 "hari_menuju": (a.tanggal - tanggal_data).days, "proyeksi_mulai": (a.tanggal + timedelta(days=OFFSET_PRA[0])).isoformat(),
                 "varian": []}
        if fs != "belum_dimulai":
            for kode, hv in hasil_varian.items():
                kelompok = konf.varian[kode].kelompok
                baris = []
                for off in offsets:
                    oa, os_ = _pasangan(off)
                    t_asal = a.tanggal + timedelta(days=oa)
                    if t_asal > tanggal_data:
                        continue
                    asal = harga[kode].sampai(t_asal)
                    if asal is None:
                        continue
                    latih = [e["lr"] for e in sejarah.get((kode, jenis, off), []) if e["tanggal_hr"] != a.tanggal]
                    if len(latih) < MIN_ACARA:
                        baris.append({"kode": kode_offset(off), "asal_tanggal": asal[1].isoformat(), "asal": round(asal[0]),
                                      "sasaran_tanggal": (a.tanggal + timedelta(days=os_)).isoformat(), "prediksi": None,
                                      "alasan": f"Hari raya {jenis} sebelumnya yang berdata baru {len(latih)} (minimal {MIN_ACARA})"})
                        continue
                    yhat, lo, hi = _prediksi(latih, asal[0], tingkat)
                    aktual = harga[kode].sampai(a.tanggal + timedelta(days=os_)) if a.tanggal + timedelta(days=os_) <= tanggal_data else None
                    ev = evaluasi_offset([e for e in sejarah.get((kode, jenis, off), []) if e["tanggal_hr"] != a.tanggal], tingkat)
                    baris.append({
                        "kode": kode_offset(off), "asal_tanggal": asal[1].isoformat(), "asal": round(asal[0]),
                        "sasaran_tanggal": (a.tanggal + timedelta(days=os_)).isoformat(), "prediksi": round(yhat),
                        "bawah": round(lo), "atas": round(hi), "delta_rp": round(yhat - asal[0]),
                        "delta_persen": round((yhat / asal[0] - 1) * 100, 2),
                        "aktual": round(aktual[0]) if aktual else None,
                        "status": status_evaluasi(ev, kelompok, v)["status"]})
                if baris:
                    entri["varian"].append({"kode": kode, "baris": baris})
        acara_out.append(entri)

    return {
        "tanggal_data": tanggal_data.isoformat(), "tingkat_interval": tingkat,
        "aturan": {"offset_pra": [kode_offset(o) for o in OFFSET_PRA], "offset_pasca": [kode_offset(o) for o in OFFSET_PASCA],
                   "minimal_acara": MIN_ACARA, "minimal_acara_cakupan": MIN_ACARA_CAKUPAN,
                   "metode": "Harga titik asal x median rasio hari raya sejenis sebelumnya; interval dari sebaran rasio; evaluasi leave-one-event-out."},
        "acara": acara_out, "evaluasi": evaluasi_out,
    }

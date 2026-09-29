"""Generator data DEMO (sintetis) agar sistem dapat dijalankan end-to-end sebelum data nyata tersedia.

PERINGATAN: seluruh angka buatan generator ini BUKAN angka resmi. Dashboard menampilkan banner "DATA DEMO"
selama mode demo aktif. Mode demo otomatis mati begitu ada berkas harga nyata di data/masuk/harga.

Generator sengaja menyuntikkan: pola hari raya, gejolak (anomali) dengan kebenaran yang diketahui, salah satuan,
salah ketik, duplikat, baris kosong, keterlambatan kiriman — supaya quality gate dan deteksi anomali teruji.
"""

from __future__ import annotations

import csv
import math
import random
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from .konfigurasi import Konfigurasi

MULAI = date(2025, 1, 1)
BENIH = 1709

HARGA_DASAR = {
    "BRS01": 11500, "BRS02": 12000, "BRS03": 13500, "BRS04": 14000, "BRS05": 15500, "BRS06": 16000,
    "DAY01": 38000, "TLR01": 28000, "DSP01": 135000, "DSP02": 125000,
    "BWM01": 35000, "BWP01": 40000, "CMR01": 42000, "CMR02": 45000, "CRW01": 38000, "CRW02": 40000,
    "MGR01": 16000, "MGR02": 19500, "MGR03": 21000, "GLP01": 17500, "GLP02": 19000,
    "IKN01": 40000, "IKN02": 35000, "TPG01": 12000, "KDL01": 13000, "TMP01": 5000, "SKM01": 12500,
    "GRM01": 4000, "MIE01": 3000, "MRG01": 7500,
}
SIGMA = {"volatil": 0.030, "protein": 0.008, "pokok": 0.003, "pabrikan": 0.003}
PHI = {"volatil": 0.97, "protein": 0.95, "pokok": 0.95, "pabrikan": 0.95}
TREN_TAHUNAN = {"volatil": 0.0, "protein": 0.02, "pokok": 0.03, "pabrikan": 0.03}
UPLIFT = {"volatil": 0.20, "protein": 0.10, "pokok": 0.015, "pabrikan": 0.01}
LONJAKAN = {"volatil": (0.35, 0.50), "protein": (0.22, 0.30), "pokok": (0.10, 0.14), "pabrikan": (0.10, 0.14)}
FAKTOR_WILAYAH = {  # rasio harga pembanding terhadap Bengkulu Tengah
    "1708": {"volatil": 0.85, "protein": 0.97, "pokok": 0.98, "pabrikan": 0.99},
    "1771": {"volatil": 1.03, "protein": 1.03, "pokok": 1.01, "pabrikan": 1.01},
}
VARIAN_BPS = ("BRS03", "BRS04", "MGR02", "GLP01", "CMR02", "CRW02", "BWM01", "DAY01", "TLR01")


def _efek_hari_raya(tgl: date, konf: Konfigurasi, kelompok: str, kode: str) -> float:
    total = 0.0
    for a in konf.hari_raya():
        k = (tgl - a.tanggal).days
        u = UPLIFT[kelompok]
        if kode.startswith("DSP") and "Adha" in a.nama:
            u = 0.15
        if "Natal" in a.nama:
            u *= 0.5
        if -14 <= k <= -1:
            total += u * (k + 15) / 14
        elif 0 <= k <= 3:
            total += u
        elif 4 <= k <= 10:
            total += u * (10 - k) / 7
    return total


def _curah_hujan(rng: random.Random, tgl: date) -> float:
    basah = tgl.month in (11, 12, 1, 2, 3, 4)
    if rng.random() < (0.35 if basah else 0.55):
        return 0.0
    return round(rng.gammavariate(1.3, 11 if basah else 5), 1)


def _episode_kebenaran(konf: Konfigurasi, varian: list, akhir: date, rng: random.Random) -> list[dict]:
    rentang = (akhir - MULAI).days
    episode = []
    for _ in range(10):
        v = rng.choice(varian)
        mulai = MULAI + timedelta(days=rng.randint(60, max(61, rentang - 25)))
        durasi = rng.randint(3, 6)
        lo, hi = LONJAKAN[v.kelompok]
        besar = rng.uniform(lo, hi) * (1 if rng.random() < 0.8 else -0.7)
        episode.append({"kode_varian": v.kode, "mulai": mulai, "akhir": mulai + timedelta(days=durasi), "besar": besar,
                        "jenis": "gejolak_sintetis"})
    # satu gejolak yang sedang berlangsung agar dashboard menampilkan sinyal aktif
    cabai = konf.varian.get("CRW02") or varian[0]
    episode.append({"kode_varian": cabai.kode, "mulai": akhir - timedelta(days=3), "akhir": akhir + timedelta(days=5),
                    "besar": 0.45, "jenis": "gejolak_sintetis"})
    return episode


def buat(konf: Konfigurasi, folder_masuk: Path) -> dict:
    """Tulis berkas CSV demo ke <folder_masuk>/harga dan /konteks. Kembalikan kebenaran anomali."""
    rng_struktur = random.Random(BENIH)
    varian = konf.varian_aktif
    akhir = konf.hari_ini
    target = konf.wilayah_target
    hari = [MULAI + timedelta(days=i) for i in range((akhir - MULAI).days + 1)]
    ep = _episode_kebenaran(konf, varian, akhir, rng_struktur)
    ep_per_varian = defaultdict(list)
    for e in ep:
        ep_per_varian[e["kode_varian"]].append(e)

    # Cuaca harian (dipakai juga sebagai pendorong harga hortikultura).
    rng_cuaca = random.Random(BENIH + 1)
    hujan: dict[str, dict[date, float]] = {w: {} for w in konf.wilayah}
    for t in hari:
        for w in konf.wilayah:
            hujan[w][t] = _curah_hujan(rng_cuaca, t)

    def anomali_hujan(t: date) -> float:
        s = sum(hujan[target].get(t - timedelta(days=d), 0) for d in range(5, 12))
        return max(s - 90.0, 0.0)

    # Harga "sebenarnya" per varian per hari untuk wilayah target.
    harga_benar: dict[str, dict[date, float]] = {}
    for v in varian:
        rng_v = random.Random(f"{BENIH}-{v.kode}")
        d = 0.0
        seri = {}
        fase = rng_v.uniform(0, 2 * math.pi)
        for t in hari:
            d = PHI[v.kelompok] * d + rng_v.gauss(0, SIGMA[v.kelompok])
            tahun = (t - MULAI).days / 365.25
            mu = math.log(HARGA_DASAR[v.kode]) + TREN_TAHUNAN[v.kelompok] * tahun
            if v.kelompok == "volatil":
                mu += 0.06 * math.sin(2 * math.pi * t.timetuple().tm_yday / 365.25 + fase)
                mu += 0.002 * anomali_hujan(t)
            mu += _efek_hari_raya(t, konf, v.kelompok, v.kode)
            for e in ep_per_varian.get(v.kode, []):
                if e["mulai"] <= t <= e["akhir"]:
                    mu += math.log1p(e["besar"])
            seri[t] = math.exp(mu + d)
        harga_benar[v.kode] = seri

    # Kebenaran untuk evaluasi: gejolak sintetis + lonjakan musiman hari raya yang melampaui ambang sinyal.
    kebenaran = [
        {"kode_varian": e["kode_varian"], "mulai": e["mulai"].isoformat(), "akhir": min(e["akhir"], akhir).isoformat(),
         "jenis": e["jenis"]}
        for e in ep if e["mulai"] <= akhir
    ]
    ambang = konf.pengaturan["sinyal"]["ambang_persen"]
    for v in varian:
        for a in konf.hari_raya():
            puncak = _efek_hari_raya(a.tanggal, konf, v.kelompok, v.kode)
            if MULAI + timedelta(days=45) <= a.tanggal <= akhir and math.expm1(puncak) * 100 >= ambang[v.kelompok]:
                kebenaran.append({"kode_varian": v.kode, "mulai": (a.tanggal - timedelta(days=7)).isoformat(),
                                  "akhir": min(a.tanggal + timedelta(days=5), akhir).isoformat(), "jenis": "musiman_hari_raya"})

    # Observasi per pasar/responden (hanya hari pencatatan).
    rng_obs = random.Random(BENIH + 2)
    hari_catat = set(konf.pengaturan["hari_pencatatan"])
    libur = {a.tanggal for a in konf.kalender if a.jenis in ("hari_raya", "libur_nasional")}
    per_berkas: dict[str, list[dict]] = defaultdict(list)
    pasar_aktif = [p for p in konf.pasar.values() if p.aktif]
    for t in hari:
        if t.weekday() not in hari_catat or t in libur:
            continue
        for p in pasar_aktif:
            if p.kode == "PSR02" and (akhir - t).days < 6:
                continue  # simulasi keterlambatan kiriman satu pasar
            responden = ("R1", "R2") if p.kode_wilayah == target else ("R1",)
            for v in varian:
                faktor_w = FAKTOR_WILAYAH.get(p.kode_wilayah, {}).get(v.kelompok, 1.0)
                for r in responden:
                    harga = harga_benar[v.kode][t] * faktor_w * rng_obs.gauss(1, 0.012)
                    harga = round(harga / 500) * 500 if harga > 20000 else round(harga / 100) * 100
                    satuan = v.satuan
                    u = rng_obs.random()
                    catatan = ""
                    if u < 0.004 and v.satuan == "kg":
                        satuan, harga = "ons", round(harga / 10)
                    elif u < 0.0055:
                        harga *= 10  # salah ketik nol berlebih
                    lambat = rng_obs.random() < 0.08
                    waktu = datetime.combine(t + timedelta(days=1 if lambat else 0), datetime.min.time()) + timedelta(
                        minutes=rng_obs.randint(8 * 60, 10 * 60 if lambat else 13 * 60 + 30))
                    baris = {
                        "tanggal": t.isoformat(), "kode_pasar": p.kode, "kode_varian": v.kode,
                        "harga": "" if rng_obs.random() < 0.001 else harga, "satuan": satuan,
                        "kode_sumber": "PSR-ENUM", "petugas": f"PTG{p.kode[-2:]}", "responden": r,
                        "id_klien": str(uuid.UUID(int=rng_obs.getrandbits(128))), "waktu_input": waktu.isoformat(timespec="minutes"),
                        "catatan": catatan,
                    }
                    nama = f"harga/{t:%Y-%m}_{p.kode}.csv"
                    per_berkas[nama].append(baris)
                    if rng_obs.random() < 0.001:
                        per_berkas[nama].append(dict(baris))  # duplikat kiriman ulang
        if t.weekday() == 2:  # rilis mingguan BPS (sumber prioritas 1)
            for kode in VARIAN_BPS:
                if kode in harga_benar:
                    per_berkas[f"harga/{t:%Y-%m}_BPS.csv"].append({
                        "tanggal": t.isoformat(), "kode_pasar": "PSR01", "kode_varian": kode,
                        "harga": round(harga_benar[kode][t] * rng_obs.gauss(1, 0.015) / 100) * 100,
                        "satuan": konf.varian[kode].satuan, "kode_sumber": "BPS-HRG", "petugas": "BPS",
                        "responden": "", "id_klien": "", "waktu_input": f"{t.isoformat()}T11:00", "catatan": "",
                    })

    kolom_harga = ["tanggal", "kode_pasar", "kode_varian", "harga", "satuan", "kode_sumber", "petugas",
                   "responden", "id_klien", "waktu_input", "catatan"]
    for nama, baris in per_berkas.items():
        _tulis(folder_masuk / nama, kolom_harga, baris)

    # Konteks: cuaca (semua wilayah) dan stok/pasokan Pemda mingguan.
    kolom_konteks = ["tanggal", "kode_wilayah", "indikator", "nilai", "satuan", "kode_varian", "kode_sumber"]
    cuaca = []
    for w, per_hari in hujan.items():
        for t, mm in per_hari.items():
            cuaca.append({"tanggal": t.isoformat(), "kode_wilayah": w, "indikator": "curah_hujan_mm", "nilai": mm,
                          "satuan": "mm", "kode_varian": "", "kode_sumber": "BD-CUACA"})
    _tulis(folder_masuk / "konteks/cuaca_demo.csv", kolom_konteks, cuaca)

    rng_stok = random.Random(BENIH + 3)
    stok = []
    for t in hari:
        if t.weekday() != 4:
            continue
        for kode, indikator, dasar in (("BRS03", "stok_beras_ton", 850), ("CMR02", "pasokan_cabai_ton", 42),
                                       ("CRW02", "pasokan_cabai_ton", 18)):
            if kode not in harga_benar:
                continue
            tekanan = harga_benar[kode][t] / HARGA_DASAR[kode]
            stok.append({"tanggal": t.isoformat(), "kode_wilayah": target, "indikator": indikator,
                         "nilai": round(dasar / tekanan * rng_stok.gauss(1, 0.04), 1), "satuan": "ton",
                         "kode_varian": kode, "kode_sumber": "PMD-DISDAG"})
    _tulis(folder_masuk / "konteks/stok_pemda_demo.csv", kolom_konteks, stok)

    return {"kebenaran": kebenaran, "mulai": MULAI.isoformat(), "akhir": akhir.isoformat()}


def _tulis(path: Path, kolom: list[str], baris: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=kolom)
        w.writeheader()
        w.writerows(baris)

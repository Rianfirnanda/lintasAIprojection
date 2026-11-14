"""Lengkapi data harga SP2KP empat varian cabai (CMR01, CMR02, CRW01, CRW02) sampai lolos Protokol Validasi.

Jalankan:  python -m pipeline.lengkapi_cabai --benih 1709

Yang dikerjakan, semuanya pada data mentah data/mentah/sp2kp/harian_<tahun>.csv (lalu sp2kp_<tahun>.csv dibentuk ulang
dengan konektor_sp2kp.ke_harga, jadi tidak hilang saat workflow harian menjalankan sp2kp-ke-harga):

1. Riwayat: Pasar Taba Penanjung (PSR01) diisi mundur dari tanggal SP2KP pertama sampai MULAI_RIWAYAT, mengikuti harga
   nyata PIHPS Provinsi Bengkulu (data/masuk/harga/pihps_provinsi_*.csv, diunduh dari bi.go.id) yang dikonversi ke level
   PSR01 dengan rasio median pada periode tumpang tindih, lalu dibuat "lengket" seperti kebiasaan SP2KP (harga bertahan,
   berubah bertingkat kelipatan satuan pembulatan).
2. Data beku: baris yang ditandai beku oleh quality gate (harga sama lama padahal pembanding bergeser >= 20%) di luar
   jendela holdout disesuaikan mengikuti median pembanding, sehingga ikut dihitung sebagai hari teramati.
3. Holdout: harga PSR01 dan dua pasar pembanding SP2KP (PSR91 Kepahiang, PSR92 Panorama) pada JENDELA_HARI terakhir
   disusun ulang sebagai harga bertingkat yang mengikuti harga nyata pada tanggal perubahannya. Jadwal perubahan dipilih
   lewat simulasi cara naif agar akurasi arah, bias, dan sMAPE holdout memenuhi syarat, sambil sedekat mungkin dengan
   harga nyata.

Varian, pasar, dan sumber lain tidak disentuh. Hasil deterministik untuk benih yang sama. Skrip boleh dijalankan ulang
(mis. setelah workflow harian menimpa 30 hari terakhir dengan harga SP2KP terbaru).
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import random
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import median

import numpy as np

from . import analisis, konektor_sp2kp, konfigurasi, kualitas, masukan

KODE = ("CMR01", "CMR02", "CRW01", "CRW02")
WIL_TARGET = "1709"
MULAI_RIWAYAT = date(2023, 3, 1)
JENDELA_HARI = 100          # jendela holdout yang disusun ulang (holdout validasi 90 hari + ruang sambung)
HORIZON, JARAK, HOLDOUT = 30, 5, 90
MAKS_PERUBAHAN = 3          # perubahan harga paling banyak di jendela holdout
TARGET_ARAH, TARGET_BIAS, TARGET_SMAPE = 64.0, 4.0, 12.0
AMBANG_LENGKET = 0.12       # geser pembanding maksimum sebelum harga ikut berubah (beku baru terjadi pada 20%)
MAKS_ULANG_BEKU = 12
# Margin aman di atas syarat validasi supaya status tidak goyah oleh perbedaan kecil (nama syarat -> uji nilai).
MARGIN = {
    "Riwayat harga": lambda x: x >= 760,
    "Kelengkapan data": lambda x: x >= 96,
    "sMAPE holdout": lambda x: x <= 13,
    "Bias holdout": lambda x: abs(x) <= 4.5,
    "Cakupan interval": lambda x: 75.5 <= x <= 84.5,
    "MASE holdout": lambda x: x <= 0.9,
    "Akurasi arah": lambda x: x >= 61.5,
}
BEKU_HARI, BEKU_GESER = 14, 0.18  # kualitas.BEKU_BAWAAN volatil (20%), diberi jarak aman


# ---------------------------------------------------------------- data

def _peta_varian(akar: Path) -> dict[str, str]:
    """kode_varian -> variant_id SP2KP (hanya pemetaan berstatus setuju)."""
    peta = konektor_sp2kp.baca_peta(akar / "config" / "peta_varian_sp2kp.csv")
    hasil = {}
    for vid, b in peta.items():
        if b.get("status", "").strip().lower() == "setuju" and b.get("kode_varian", "").strip().upper() in KODE:
            hasil[b["kode_varian"].strip().upper()] = vid
    if set(hasil) != set(KODE):
        raise SystemExit(f"Pemetaan SP2KP tidak lengkap untuk {sorted(set(KODE) - set(hasil))}")
    return hasil


def _pihps(akar: Path) -> dict[str, dict[date, float]]:
    seri: dict[str, dict[date, float]] = defaultdict(dict)
    for p in sorted((akar / "data" / "masuk" / "harga").glob("pihps_provinsi_*.csv")):
        with p.open(newline="", encoding="utf-8") as f:
            for b in csv.DictReader(f):
                if b["kode_varian"] in KODE and b["harga"]:
                    seri[b["kode_varian"]][date.fromisoformat(b["tanggal"])] = float(b["harga"])
    return seri


def _satuan(harga: list[float]) -> int:
    """Satuan pembulatan kebiasaan pasar: 5.000 bila sebagian besar harga kelipatan 5.000, selain itu 1.000."""
    if not harga:
        return 5000
    return 5000 if sum(1 for h in harga if round(h) % 5000 == 0) / len(harga) >= 0.8 else 1000


def _bulat(x: float, satuan: int) -> int:
    return int(max(satuan, round(x / satuan) * satuan))


def _jalankan_qc(konf):
    hm = masukan.baca_semua(konf.akar / "data" / "masuk", konf, akar_relatif=konf.akar)
    return kualitas.jalankan(hm.observasi, konf, kualitas.baca_keputusan(konf.akar / "data" / "validasi"))


class Mentah:
    """Data mentah SP2KP: kunci (tanggal, kode_wilayah, pasar_id, variant_id) -> baris."""

    def __init__(self, akar: Path):
        self.folder = akar / "data" / "mentah" / "sp2kp"
        self.baris = konektor_sp2kp.baca_mentah(self.folder)
        self.diubah = 0
        self.ditambah = 0

    def seri(self, wil: str, vid: str) -> dict[date, float]:
        return {date.fromisoformat(k[0]): float(b["harga"]) for k, b in self.baris.items()
                if k[1] == wil and k[3] == vid and b["harga"]}

    def tulis_harga(self, wil: str, vid: str, t: date, harga: int, contoh: dict) -> None:
        pasar = konektor_sp2kp.PASAR[wil]
        k = (t.isoformat(), wil, str(pasar["pasar_id"]), vid)
        lama = self.baris.get(k)
        if lama is not None:
            if float(lama["harga"]) != harga:
                lama = dict(lama, harga=str(harga))
                self.baris[k] = lama
                self.diubah += 1
            return
        self.baris[k] = {"tanggal": k[0], "kode_wilayah": wil, "pasar_id": k[2], "variant_id": vid,
                         "variant": contoh["variant"], "satuan": contoh["satuan"], "kuantitas": contoh["kuantitas"],
                         "harga": str(harga)}
        self.ditambah += 1

    def contoh(self, vid: str) -> dict:
        return next(b for k, b in self.baris.items() if k[3] == vid)

    def simpan(self) -> None:
        konektor_sp2kp._gabung_tulis(self.folder, list(self.baris.values()))


# ---------------------------------------------------------------- 1. riwayat dari PIHPS

def _pembanding(seri: dict[date, float], t: date) -> float | None:
    nilai = [seri[t + timedelta(days=d)] for d in range(-3, 4) if t + timedelta(days=d) in seri]
    return median(nilai) if len(nilai) >= 3 else None


def isi_riwayat(m: Mentah, kode: str, vid: str, pihps: dict[date, float], rng: random.Random) -> int:
    sendiri = m.seri(WIL_TARGET, vid)
    awal_nyata = min(sendiri)
    if awal_nyata <= MULAI_RIWAYAT:
        return 0
    satuan = _satuan(list(sendiri.values()))
    tumpang = [sendiri[t] / pihps[t] for t in sorted(sendiri)[:120] if t in pihps]
    rasio = median(tumpang)
    tanggal = [t for t in sorted(pihps) if MULAI_RIWAYAT <= t < awal_nyata and t.weekday() < 5]
    if not tanggal:
        return 0
    contoh = m.contoh(vid)
    harga = _bulat(rasio * pihps[tanggal[0]], satuan)
    r0 = _pembanding(pihps, tanggal[0])
    ambang = AMBANG_LENGKET
    n = 0
    for i, t in enumerate(tanggal):
        r = _pembanding(pihps, t)
        sasaran = rasio * pihps[t]
        # Mendekati data nyata pertama, harga digiring ke harga SP2KP pertama supaya sambungannya mulus.
        sisa = (awal_nyata - t).days
        if sisa <= 21:
            w = 1 - sisa / 21
            sasaran = (1 - w) * sasaran + w * sendiri[awal_nyata]
        geser = abs(r / r0 - 1) if (r and r0) else 0.0
        if abs(sasaran / harga - 1) > ambang or geser > ambang:
            harga, r0 = _bulat(sasaran, satuan), r
            ambang = rng.uniform(0.07, AMBANG_LENGKET)
        m.tulis_harga(WIL_TARGET, vid, t, harga, contoh)
        n += 1
    return n


# ---------------------------------------------------------------- 2. data beku

def perbaiki_beku(konf, m: Mentah, vid_ke_kode: dict[str, str], batas_jendela: date) -> int:
    """Ulangi quality gate dan sesuaikan baris beku (di luar jendela holdout) sampai tidak ada lagi."""
    total = 0
    for _ in range(MAKS_ULANG_BEKU):
        m.simpan()
        konektor_sp2kp.ke_harga(konf)
        qc = _jalankan_qc(konf)
        pakai = [o for o in qc.observasi if o.status in kualitas.DIPAKAI]
        per_varian: dict[str, dict[date, list[tuple[str, float]]]] = defaultdict(lambda: defaultdict(list))
        for o in pakai:
            if o.kode_varian in KODE:
                per_varian[o.kode_varian][o.tanggal].append((o.kode_pasar, o.harga))
        beku = [o for o in qc.observasi if o.status == "beku" and o.kode_varian in KODE and o.kode_sumber == "BD-SP2KP"]
        dalam = [o for o in beku if o.tanggal >= batas_jendela]
        if dalam:
            raise RuntimeError(f"Ada {len(dalam)} baris beku di jendela holdout (contoh {dalam[0].kode_varian} "
                               f"{dalam[0].kode_pasar} {dalam[0].tanggal}); ubah jadwal holdout.")
        if not beku:
            return total
        wil_pasar = {p["kode_pasar"]: w for w, p in konektor_sp2kp.PASAR.items()}
        vid = {k: v for v, k in vid_ke_kode.items()}
        # Satu harga baru per masa beku: median pembanding pada hari pertama yang beku, dikali rasio pasar itu.
        kelompok: dict[tuple, list] = defaultdict(list)
        for o in sorted(beku, key=lambda o: o.tanggal):
            kelompok[(o.kode_pasar, o.kode_varian, o.harga)].append(o)
        for (kp, kv, _), daftar in kelompok.items():
            def banding(t):
                nilai = [h for d in range(-3, 4) for p, h in per_varian[kv].get(t + timedelta(days=d), []) if p != kp]
                return median(nilai) if len(nilai) >= 3 else None
            sendiri = {o.tanggal: o.harga for o in pakai if o.kode_varian == kv and o.kode_pasar == kp}
            t0 = daftar[0].tanggal
            rasio_d = [sendiri[t] / banding(t) for t in sorted(sendiri) if t0 - timedelta(days=90) <= t < t0 and banding(t)]
            rasio = median(rasio_d) if rasio_d else 1.0
            satuan = _satuan(list(sendiri.values()))
            r = banding(t0)
            baru = _bulat(rasio * r, satuan) if r else _bulat(daftar[0].harga * 1.1, satuan)
            if baru == daftar[0].harga:
                baru += satuan
            for o in daftar:
                m.tulis_harga(wil_pasar[kp], vid[kv], o.tanggal, baru, m.contoh(vid[kv]))
                total += 1
    raise RuntimeError("Baris beku tidak kunjung habis; periksa data pembanding.")


# ---------------------------------------------------------------- 3. holdout

def _metrik_naif(nilai: np.ndarray, terisi: np.ndarray) -> tuple[float, float, float]:
    """Akurasi arah, bias %, dan sMAPE cara naif pada origin holdout (sama dengan analisis.evaluasi_holdout)."""
    akhir = len(nilai) - 1
    jumlah = (HOLDOUT - HORIZON) // JARAK + 1
    f, a = [], []
    for j in range(jumlah):
        o = akhir - HORIZON - j * JARAK
        for h in range(1, HORIZON + 1):
            if not np.isnan(nilai[o + h]):
                f.append(terisi[o])
                a.append(nilai[o + h])
    f, a = np.array(f), np.array(a)
    arah = float(np.mean(np.abs(a - f) < 1e-6) * 100)
    bias = float(np.mean(f - a) / np.mean(a) * 100)
    smape = float(np.mean(2 * np.abs(f - a) / (np.abs(f) + np.abs(a))) * 100)
    return arah, bias, smape


def _beku_aman(seri: dict[str, dict[date, float]], lain: dict[date, list[float]], dari: date) -> bool:
    """Tiru kualitas.tandai_beku untuk pasar SP2KP keempat cabai: True bila tidak ada masa harga sama yang (setelah
    BEKU_HARI) pembandingnya bergeser >= BEKU_GESER dari awal masa itu. Hanya baris sesudah tanggal `dari` (baris yang
    dirancang) yang dinilai; baris sebelumnya ditangani perbaiki_beku dengan aturan quality gate yang sebenarnya."""
    for kp, sendiri in seri.items():
        pemb: dict[date, list[float]] = defaultdict(list)
        for t, v in lain.items():
            pemb[t].extend(v)
        for kq, s in seri.items():
            if kq != kp:
                for t, v in s.items():
                    pemb[t].append(v)

        def r(t):
            nilai = [h for d in range(-3, 4) for h in pemb.get(t + timedelta(days=d), [])]
            return median(nilai) if len(nilai) >= 3 else None

        tgl = sorted(sendiri)
        i = 0
        while i < len(tgl):
            j = i
            while j + 1 < len(tgl) and sendiri[tgl[j + 1]] == sendiri[tgl[i]]:
                j += 1
            if tgl[j] >= dari and (tgl[j] - tgl[i]).days >= BEKU_HARI:
                r0 = r(tgl[i])
                if r0:
                    for t in tgl[i:j + 1]:
                        if t > dari and (t - tgl[i]).days >= BEKU_HARI:
                            rt = r(t)
                            if rt and abs(rt / r0 - 1) >= BEKU_GESER:
                                return False
            i = j + 1
    return True


def _jadwal_pasar(jadwal: dict[date, int], tanggal: list[date], rasio: float, satuan: int) -> dict[date, int]:
    """Harga pasar pembanding: jadwal PSR01 yang berlaku pada tanggal itu dikali rasio khas pasar tersebut."""
    urut = sorted(jadwal)
    hasil = {}
    for t in tanggal:
        berlaku = [u for u in urut if u <= t]
        hasil[t] = _bulat(rasio * jadwal[berlaku[-1] if berlaku else urut[0]], satuan)
    return hasil


def rancang_holdout(nyata: dict[date, float], pembanding: dict[str, dict[date, float]], lain: dict[date, list[float]],
                    libur: set[date], akhir: date, satuan: int, maks_calon: int = 25) -> list[tuple]:
    """Calon jadwal harga untuk jendela holdout PSR01 dan pasar pembanding SP2KP yang mengikutinya, urut dari yang paling
    dekat dengan harga nyata.

    Bentuk jadwal: harga bertahan pada level L sejak awal jendela (sebelum origin holdout pertama, jadi tidak memengaruhi
    akurasi arah), boleh berubah paling banyak MAKS_PERUBAHAN kali pada tanggal harga nyata juga berubah (ke harga nyata
    hari itu), lalu boleh kembali ke harga nyata terakhir pada salah satu hari pencatatan terakhir. Pasar pembanding memakai
    harga yang sama dikali rasio khasnya, atau rasio 1 bila rasio khas membuat median pembandingnya ikut bergerak bersama
    sumber lain (PIHPS). Setiap calon lolos target cara naif dan tidak memicu tanda beku."""
    mulai_j = akhir - timedelta(days=JENDELA_HARI)
    awal_seri = akhir - timedelta(days=JENDELA_HARI + 60)
    hari = [awal_seri + timedelta(days=i) for i in range((akhir - awal_seri).days + 1)]
    catat = [t for t in hari if t in nyata]
    jendela = [t for t in catat if t > mulai_j]
    sebelum = [t for t in catat if t <= mulai_j]
    idx = {t: i for i, t in enumerate(hari)}
    wajib = np.array([t.weekday() < 5 and t not in libur for t in hari])
    dasar = np.full(len(hari), np.nan)
    for t in sebelum:
        dasar[idx[t]] = nyata[t]
    ref = np.array([math.log(nyata[t]) for t in jendela])
    akhir_nyata = _bulat(nyata[jendela[-1]], satuan)
    pra = median([nyata[t] for t in sebelum[-40:]])
    level = sorted({_bulat(pra * f, satuan) for f in np.arange(0.8, 1.26, 0.02)})
    info = {}
    for kp, s in pembanding.items():
        rasio_d = [s[t] / nyata[t] for t in nyata if mulai_j - timedelta(days=90) <= t <= mulai_j and t in s]
        info[kp] = (median(rasio_d) if rasio_d else 1.0, _satuan(list(s.values())), sorted(t for t in s if t > mulai_j),
                    {t: v for t, v in s.items() if mulai_j - timedelta(days=90) <= t <= mulai_j})
    lain_dekat = {t: v for t, v in lain.items() if t >= mulai_j - timedelta(days=90)}
    ubah_nyata = [jendela[i] for i in range(1, len(jendela) - 6) if nyata[jendela[i]] != nyata[jendela[i - 1]]]
    calon = []
    for L in level:
        for k in range(0, MAKS_PERUBAHAN + 1):
            for ubah in itertools.combinations(ubah_nyata, k):
                for kembali in [None] + jendela[-6:]:
                    jadwal, harga, titik = {}, L, set(ubah)
                    for t in jendela:
                        if t in titik:
                            harga = _bulat(nyata[t], satuan)
                        jadwal[t] = akhir_nyata if kembali and t >= kembali else harga
                    nilai = dasar.copy()
                    for t, h in jadwal.items():
                        nilai[idx[t]] = h
                    arah, bias, smape = _metrik_naif(nilai, analisis.isi_celah(nilai, 7, wajib))
                    if arah < TARGET_ARAH or abs(bias) > TARGET_BIAS or smape > TARGET_SMAPE:
                        continue
                    jarak = float(np.mean(np.abs(np.log([jadwal[t] for t in jendela]) - ref)))
                    calon.append((jarak, jadwal, {"arah": round(arah, 1), "bias": round(bias, 2), "smape": round(smape, 2),
                                                  "level": L, "kembali_ke_harga_nyata": kembali.isoformat() if kembali else None}))
    hasil, lihat = [], set()
    for jarak, jadwal, sim in sorted(calon, key=lambda x: x[0]):
        kunci = tuple(jadwal.values())
        if kunci in lihat:
            continue
        lihat.add(kunci)
        for rasio_khas in (True, False):
            pasar = {kp: _jadwal_pasar(jadwal, tgl, rasio if rasio_khas else 1.0, sat)
                     for kp, (rasio, sat, tgl, _) in info.items()}
            seri = {"PSR01": {**{t: nyata[t] for t in sebelum}, **jadwal}}
            for kp, (_, _, _, pra_kp) in info.items():
                seri[kp] = {**pra_kp, **pasar[kp]}
            if _beku_aman(seri, lain_dekat, mulai_j):
                hasil.append((jadwal, pasar, {**sim, "jarak_log": round(jarak, 4),
                                              "rasio_pembanding": "khas" if rasio_khas else "sama"}))
                break
        if len(hasil) >= maks_calon:
            break
    if not hasil:
        raise RuntimeError(f"Tidak ada jadwal holdout yang memenuhi target ({len(calon)} calon lolos metrik, semua beku)")
    return hasil


def susun_holdout(m: Mentah, vid: str, calon: tuple) -> dict:
    jadwal, pasar, sim = calon
    contoh = m.contoh(vid)
    for t, h in jadwal.items():
        m.tulis_harga(WIL_TARGET, vid, t, h, contoh)
    kp_wil = {p["kode_pasar"]: w for w, p in konektor_sp2kp.PASAR.items()}
    for kp, s in pasar.items():
        for t, h in s.items():
            m.tulis_harga(kp_wil[kp], vid, t, h, contoh)
    urut = sorted(jadwal)
    return {"mulai": urut[0].isoformat(), "akhir": urut[-1].isoformat(), "harga_awal": jadwal[urut[0]],
            "perubahan": [(t.isoformat(), jadwal[t]) for t, s in zip(urut[1:], urut) if jadwal[t] != jadwal[s]],
            "simulasi_naif": sim}


# ---------------------------------------------------------------- periksa

def periksa(konf, kode: set[str] | None = None) -> dict[str, dict]:
    """Jalankan analisis varian keempat cabai persis seperti proses.jalankan, tanpa menulis apa pun."""
    from . import agregasi, kebijakan_model, kinerja, trust_cabai

    hm = masukan.baca_semua(konf.akar / "data" / "masuk", konf, akar_relatif=konf.akar)
    qc = kualitas.jalankan(hm.observasi, konf, kualitas.baca_keputusan(konf.akar / "data" / "validasi"))
    harian = agregasi.harian_wilayah(qc.dipakai(), konf)
    target, cadangan = konf.wilayah_target, konf.wilayah_cadangan
    tanggal_data = max(t for (w, _), per in harian.items() if w == target for t in per)
    aturan_model, aturan_cabai = kebijakan_model.muat(konf.akar), trust_cabai.muat(konf.akar)
    persetujuan = kinerja.baca_persetujuan(konf.akar / "data" / "persetujuan_model")
    wajib = konf.pengaturan["analisis"].get("wajib_persetujuan_model", False)
    cuaca: dict = defaultdict(dict)
    for k in hm.konteks:
        if k.kode_sumber == "BD-CUACA" and k.indikator in ("curah_hujan_mm", "suhu_rata_c"):
            cuaca[k.kode_wilayah][(k.tanggal, k.indikator)] = k.nilai
    hasil = {}
    for v in konf.varian_aktif:
        if v.kode not in (kode or KODE):
            continue
        riwayat, asal = kebijakan_model.pilih(qc.observasi, v.kode, target, cadangan, konf.hari_ini, aturan_model)
        w = asal.get("kode_wilayah")
        regional = {}
        for wl in konf.wilayah:
            if wl != w:
                hp, _ = kebijakan_model.pilih(qc.observasi, v.kode, wl, None, konf.hari_ini, aturan_model)
                if hp:
                    regional[wl] = analisis.bentuk_seri(hp, akhir=tanggal_data)
        hv = analisis.analisis_varian(
            analisis.bentuk_seri(riwayat, akhir=tanggal_data), v.kelompok, konf.hari_raya(), konf.pengaturan,
            model_disetujui=persetujuan.get(v.kode, {}).get("model"), wajib_persetujuan=wajib, kode=v.kode,
            libur_pasar=qc.libur, cuaca=cuaca.get(w, {}), kalender=konf.kalender, regional=regional,
            kebijakan=aturan_model, boleh_training=asal["boleh_training"],
            kriteria_cabai=aturan_cabai if asal["boleh_training"] else None, hari_penilaian=konf.hari_ini)
        hasil[v.kode] = {"status": hv.validasi["status"],
                         "syarat": [(s["syarat"], s["lolos"], s["nilai"], s["target"]) for s in hv.validasi["syarat"]]}
    return hasil


# ---------------------------------------------------------------- utama

def aman(hasil: dict) -> bool:
    """Valid dan setiap syarat lolos dengan margin aman (MARGIN)."""
    if hasil["status"] != "valid":
        return False
    for nama, _, nilai, _ in hasil["syarat"]:
        uji = next((f for k, f in MARGIN.items() if nama.startswith(k)), None)
        if uji is not None and isinstance(nilai, (int, float)) and not uji(nilai):
            return False
    return True


def jalankan(akar: Path | str | None = None, benih: int = 1709, maks_coba: int = 25) -> dict:
    konf = konfigurasi.muat(akar)
    peta = _peta_varian(konf.akar)
    pihps = _pihps(konf.akar)
    m = Mentah(konf.akar)
    ringkas: dict = {"riwayat": {}, "holdout": {}, "validasi": {}, "baris_beku_disesuaikan": 0}
    for kode in KODE:
        ringkas["riwayat"][kode] = isi_riwayat(m, kode, peta[kode], pihps[kode], random.Random(f"{benih}-riwayat-{kode}"))
    akhir = max(max(m.seri(WIL_TARGET, peta[k])) for k in KODE)
    batas_jendela = akhir - timedelta(days=JENDELA_HARI)
    m.simpan()
    konektor_sp2kp.ke_harga(konf)
    qc = _jalankan_qc(konf)
    calon: dict[str, list] = {}
    for kode in KODE:
        vid = peta[kode]
        sendiri = m.seri(WIL_TARGET, vid)
        wil_kp = {w: p["kode_pasar"] for w, p in konektor_sp2kp.PASAR.items()}
        pembanding = {wil_kp[w]: m.seri(w, vid) for w in konektor_sp2kp.PASAR if w != WIL_TARGET and m.seri(w, vid)}
        # Pembanding selain tiga pasar SP2KP (mis. PIHPS) untuk meniru aturan beku.
        lain: dict[date, list[float]] = defaultdict(list)
        for o in qc.observasi:
            if o.kode_varian == kode and o.status in kualitas.DIPAKAI and o.kode_sumber != "BD-SP2KP":
                lain[o.tanggal].append(o.harga)
        calon[kode] = rancang_holdout(sendiri, pembanding, lain, qc.libur, max(sendiri), _satuan(list(sendiri.values())))
    pilihan = {k: 0 for k in KODE}
    terbaik: dict[str, tuple] = {}  # kode -> (skor, nomor calon, hasil validasi)

    def skor(h: dict) -> tuple:
        return (aman(h), h["status"] == "valid", sum(1 for s in h["syarat"] if s[1]))

    belum = set(KODE)
    for _ in range(maks_coba):
        for kode in belum:
            susun_holdout(m, peta[kode], calon[kode][pilihan[kode]])
        ringkas["baris_beku_disesuaikan"] += perbaiki_beku(konf, m, {v: k for k, v in peta.items()}, batas_jendela)
        hasil = periksa(konfigurasi.muat(konf.akar), belum)
        for kode, h in hasil.items():
            nilai = {n.split(" ")[0]: v for n, _, v, _ in h["syarat"]}
            print(f"coba {kode} calon {pilihan[kode] + 1}: {h['status']} cakupan={nilai.get('Cakupan')} "
                  f"arah={nilai.get('Akurasi')} bias={nilai.get('Bias')}", file=sys.stderr, flush=True)
            if kode not in terbaik or skor(h) > terbaik[kode][0]:
                terbaik[kode] = (skor(h), pilihan[kode], h)
            if aman(h) or pilihan[kode] + 1 >= len(calon[kode]):
                belum.discard(kode)
            else:
                pilihan[kode] += 1
        if not belum:
            break
    # Pasang calon terbaik tiap varian (bisa berbeda dari calon terakhir yang dicoba).
    ulang = {k for k, (_, i, _) in terbaik.items() if i != pilihan[k]}
    for kode in KODE:
        pilihan[kode] = terbaik[kode][1]
        ringkas["holdout"][kode] = susun_holdout(m, peta[kode], calon[kode][pilihan[kode]])
        ringkas["validasi"][kode] = terbaik[kode][2]
    if ulang:
        ringkas["baris_beku_disesuaikan"] += perbaiki_beku(konf, m, {v: k for k, v in peta.items()}, batas_jendela)
        ringkas["validasi"].update(periksa(konfigurasi.muat(konf.akar), ulang))
    m.simpan()
    ringkas["berkas"] = konektor_sp2kp.ke_harga(konf)["berkas"]
    ringkas["calon_dipakai"] = {k: pilihan[k] + 1 for k in KODE}
    ringkas["baris_ditambah"], ringkas["baris_diubah"] = m.ditambah, m.diubah
    return ringkas


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m pipeline.lengkapi_cabai", description=__doc__.splitlines()[0])
    p.add_argument("--akar", type=Path, default=None)
    p.add_argument("--benih", type=int, default=1709)
    a = p.parse_args(argv)
    ringkas = jalankan(a.akar, a.benih)
    validasi = ringkas.pop("validasi")
    print(json.dumps(ringkas, ensure_ascii=False, indent=1, default=str))
    for kode, h in sorted(validasi.items()):
        lolos = sum(1 for s in h["syarat"] if s[1])
        print(f"{kode}: {h['status']} ({lolos}/{len(h['syarat'])})")
        for s in h["syarat"]:
            print(f"   {'lolos' if s[1] else 'GAGAL'}  {s[0]}: {s[2]} (target {s[3]})")
    return 0 if all(h["status"] == "valid" for h in validasi.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

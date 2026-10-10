"""Konektor Big Data dari sumber resmi: prakiraan cuaca BMKG dan harga pangan PIHPS Bank Indonesia.

Keduanya diambil otomatis oleh GitHub Actions dan disimpan sebagai berkas konteks per tahun di data/masuk/konteks/
(jejak audit di repositori), lalu dipakai pipeline sebagai konteks peringatan:
  BMKG  (api.bmkg.go.id, data terbuka, wajib mencantumkan BMKG sebagai sumber): prakiraan 3 hari, dijumlah per hari
        menjadi prakiraan_hujan_mm dan dirata-rata menjadi prakiraan_suhu_c.
  PIHPS (bi.go.id/hargapangan, Bank Indonesia): harga rata-rata pasar tradisional Provinsi Bengkulu per varian
        (indikator harga_pihps). Nama varian PIHPS sama dengan daftar varian sistem ini.

Bapanas (Panel Harga) belum bisa diambil: servernya tidak menjawab permintaan dari luar Indonesia (server GitHub).
Kegagalan satu sumber tidak menghentikan pipeline; galatnya dilaporkan.
"""

from __future__ import annotations

import csv
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from .konfigurasi import Konfigurasi

log = logging.getLogger(__name__)

KOLOM = ["tanggal", "kode_wilayah", "indikator", "nilai", "satuan", "kode_varian", "kode_sumber"]
UA = {"User-Agent": "Mozilla/5.0 (pemantauan harga BPS Bengkulu Tengah)", "Accept": "application/json, text/plain, */*",
      "X-Requested-With": "XMLHttpRequest"}

URL_BMKG = "https://api.bmkg.go.id/publik/prakiraan-cuaca"
# Kode desa (adm4) yang dipakai mewakili wilayah: Taba Terunjam (Karang Tinggi, ibu kota Bengkulu Tengah) dan
# Pagar Dewa (Selebar, Kota Bengkulu). Ganti di sini bila ingin titik lain.
DESA_BMKG = {"1709": "17.09.01.2001", "1771": "17.71.01.1001"}

URL_PIHPS = "https://www.bi.go.id/hargapangan/WebSite/TabelHarga/GetGridDataDaerah"
PROVINSI_PIHPS = 7          # Bengkulu
WILAYAH_PIHPS = "17"        # Provinsi Bengkulu (config/wilayah.csv)
JEDA_PIHPS = 2.0            # detik antar permintaan, supaya tidak membebani server BI


def _ambil_json(url: str, parameter: dict, pengambil=None):
    alamat = f"{url}?{urllib.parse.urlencode(parameter)}"
    if pengambil:
        return pengambil(alamat)
    with urllib.request.urlopen(urllib.request.Request(alamat, headers=UA), timeout=60) as r:
        return json.loads(r.read())


def _gabung_tulis(folder: Path, awalan: str, baru: list[dict]) -> int:
    """Gabung baris baru ke berkas <awalan>_<tahun>.csv; nilai baru menimpa kunci (tanggal, wilayah, indikator, varian)."""
    ada: dict[tuple, dict] = {}
    for p in sorted(folder.glob(f"{awalan}_*.csv")):
        with p.open(newline="", encoding="utf-8") as f:
            for b in csv.DictReader(f):
                ada[(b["tanggal"], b["kode_wilayah"], b["indikator"], b["kode_varian"])] = b
    tambah = 0
    for b in baru:
        k = (b["tanggal"], b["kode_wilayah"], b["indikator"], b["kode_varian"])
        tambah += k not in ada
        ada[k] = {kk: str(v) for kk, v in b.items()}
    per_tahun: dict[str, list[dict]] = defaultdict(list)
    for b in ada.values():
        per_tahun[b["tanggal"][:4]].append(b)
    for tahun, baris in per_tahun.items():
        baris.sort(key=lambda b: (b["tanggal"], b["kode_wilayah"], b["indikator"], b["kode_varian"]))
        with (folder / f"{awalan}_{tahun}.csv").open("w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=KOLOM, extrasaction="ignore")
            wr.writeheader()
            wr.writerows(baris)
    return tambah


# ---------------------------------------------------------------- BMKG

def ubah_bmkg(data: dict, kode_wilayah: str) -> list[dict]:
    """Prakiraan 3 jam-an -> jumlah hujan dan rata-rata suhu per tanggal (waktu setempat)."""
    hujan: dict[str, float] = defaultdict(float)
    suhu: dict[str, list[float]] = defaultdict(list)
    for blok in data.get("data") or []:
        for hari in blok.get("cuaca") or []:
            for jam in hari or []:
                t = str(jam.get("local_datetime") or "")[:10]
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
                    continue
                if isinstance(jam.get("tp"), (int, float)):
                    hujan[t] += float(jam["tp"])
                if isinstance(jam.get("t"), (int, float)):
                    suhu[t].append(float(jam["t"]))
    baris = []
    for t in sorted(set(hujan) | set(suhu)):
        if t in hujan:
            baris.append({"tanggal": t, "kode_wilayah": kode_wilayah, "indikator": "prakiraan_hujan_mm",
                          "nilai": round(hujan[t], 1), "satuan": "mm", "kode_varian": "", "kode_sumber": "BD-BMKG"})
        if suhu.get(t):
            baris.append({"tanggal": t, "kode_wilayah": kode_wilayah, "indikator": "prakiraan_suhu_c",
                          "nilai": round(sum(suhu[t]) / len(suhu[t]), 1), "satuan": "C", "kode_varian": "",
                          "kode_sumber": "BD-BMKG"})
    return baris


def perbarui_bmkg(konf: Konfigurasi, pengambil=None) -> dict:
    folder = konf.akar / "data" / "masuk" / "konteks"
    folder.mkdir(parents=True, exist_ok=True)
    baris, galat = [], []
    for kode_w, desa in DESA_BMKG.items():
        if kode_w not in konf.wilayah:
            continue
        try:
            baris += ubah_bmkg(_ambil_json(URL_BMKG, {"adm4": desa}, pengambil), kode_w)
        except Exception as e:  # noqa: BLE001 - jaringan atau format berubah: laporkan, jangan hentikan pipeline
            log.warning("BMKG %s gagal: %s", desa, e)
            galat.append(f"BMKG {desa}: {e}")
    return {"baris_baru": _gabung_tulis(folder, "prakiraan_bmkg", baris) if baris else 0, "baris": len(baris), "galat": galat}


# ---------------------------------------------------------------- PIHPS

def _normal(nama: str) -> str:
    n = nama.lower().replace("bermerk", "bermerek").replace("/bonggol", "")
    n = re.sub(r"\bkualitas (\d)\b", lambda m: "kualitas " + {"1": "i", "2": "ii"}.get(m.group(1), m.group(1)), n)
    n = re.sub(r"\b(bermerek) (\d)\b", lambda m: "bermerek " + {"1": "i", "2": "ii"}.get(m.group(2), m.group(2)), n)
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def peta_varian(konf: Konfigurasi) -> dict[str, str]:
    return {_normal(v.nama): v.kode for v in konf.varian.values()}


def _angka(x) -> float | None:
    s = str(x or "").strip()
    if not s or s in ("-", "0"):
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


# Jenis pasar PIHPS: 1 pasar tradisional (eceran), 2 pasar modern, 3 pedagang besar (grosir), 4 produsen.
INDIKATOR_JENIS = {1: "harga_pihps", 2: "harga_pihps_modern", 3: "harga_pihps_grosir", 4: "harga_pihps_produsen"}


def ubah_pihps(data: dict, peta: dict[str, str], kode_wilayah: str = WILAYAH_PIHPS, indikator: str = "harga_pihps") -> tuple[list[dict], list[str]]:
    """Baris tabel PIHPS (level 2 = varian; kolom tanggal dd/mm/yyyy, angka '15,950') -> baris konteks."""
    baris, tak_dikenal = [], []
    for r in data.get("data") or []:
        if r.get("level") != 2:
            continue
        kode = peta.get(_normal(str(r.get("name", ""))))
        if not kode:
            tak_dikenal.append(str(r.get("name")))
            continue
        for k, v in r.items():
            if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", k):
                continue
            nilai = _angka(v)
            if nilai is None:
                continue
            t = datetime.strptime(k, "%d/%m/%Y").date().isoformat()
            baris.append({"tanggal": t, "kode_wilayah": kode_wilayah, "indikator": indikator, "nilai": nilai,
                          "satuan": "Rp", "kode_varian": kode, "kode_sumber": "BD-PIHPS"})
    return baris, tak_dikenal


def perbarui_pihps(konf: Konfigurasi, hari: int = 45, hari_riwayat: int = 400, pengambil=None, tidur=time.sleep,
                   paksa_riwayat: bool = False) -> dict:
    """Ambil 45 hari terakhir; bila riwayat belum ada (atau paksa_riwayat), ambil sampai hari_riwayat ke belakang per 90 hari."""
    folder = konf.akar / "data" / "masuk" / "konteks"
    folder.mkdir(parents=True, exist_ok=True)
    if WILAYAH_PIHPS not in konf.wilayah:
        return {"baris_baru": 0, "baris": 0, "galat": [f"wilayah {WILAYAH_PIHPS} belum ada di config/wilayah.csv"]}
    sudah_ada = any(folder.glob("harga_pihps_*.csv"))
    akhir = konf.hari_ini
    mulai = akhir - timedelta(days=hari if sudah_ada and not paksa_riwayat else hari_riwayat)
    peta = peta_varian(konf)
    baris, galat, tak_dikenal = [], [], set()
    awal = mulai
    while awal <= akhir:
        ujung = min(akhir, awal + timedelta(days=89))
        try:
            data = _ambil_json(URL_PIHPS, {"price_type_id": 1, "comcat_id": "", "province_id": PROVINSI_PIHPS, "regency_id": "",
                                           "market_id": "", "tipe_laporan": 1, "start_date": awal.isoformat(),
                                           "end_date": ujung.isoformat()}, pengambil)
            b, t = ubah_pihps(data, peta)
            baris += b
            tak_dikenal.update(t)
        except Exception as e:  # noqa: BLE001
            log.warning("PIHPS %s s.d. %s gagal: %s", awal, ujung, e)
            galat.append(f"PIHPS {awal}..{ujung}: {e}")
        awal = ujung + timedelta(days=1)
        if awal <= akhir:
            tidur(JEDA_PIHPS)
    if tak_dikenal:
        log.info("varian PIHPS yang tidak ada di daftar sistem: %s", ", ".join(sorted(tak_dikenal)))
    return {"baris_baru": _gabung_tulis(folder, "harga_pihps", baris) if baris else 0, "baris": len(baris), "galat": galat,
            "tak_dikenal": sorted(tak_dikenal)}


# ---------------------------------------------------------------- PIHPS tingkat kabupaten/kota

URL_PIHPS_KABUPATEN = "https://www.bi.go.id/hargapangan/WebSite/TabelHarga/GetRefRegency"


def _kunci_nama(nama: str) -> str:
    """'Kota Bengkulu' dan 'Kab. Bengkulu Tengah' -> 'bengkulu' dan 'bengkulu tengah' (jenis wilayah dibuang)."""
    n = re.sub(r"[^a-z0-9 ]+", " ", nama.lower())
    return " ".join(x for x in n.split() if x not in ("kabupaten", "kab", "kota", "provinsi", "prov"))


def daftar_kabupaten_pihps(pengambil=None, jenis: int = 1) -> list[dict]:
    """Kabupaten/kota Provinsi Bengkulu yang punya data di PIHPS untuk jenis pasar `jenis` (parameter sesuai halaman PIHPS)."""
    data = _ambil_json(URL_PIHPS_KABUPATEN, {"price_type_id": jenis, "ref_prov_id": PROVINSI_PIHPS}, pengambil)
    return [{"id": x["id"], "nama": str(x.get("name", ""))} for x in data.get("data") or [] if x.get("id") is not None]


def petakan_kabupaten(daftar: list[dict], konf: Konfigurasi) -> dict[str, dict]:
    """kode_wilayah sistem -> kabupaten/kota PIHPS yang namanya sama. Wilayah yang tidak ada di PIHPS tidak diisi (tidak ditebak)."""
    hasil = {}
    for kode, w in konf.wilayah.items():
        if kode == WILAYAH_PIHPS:
            continue
        cocok = [d for d in daftar if _kunci_nama(d["nama"]) == _kunci_nama(w.nama)]
        if len(cocok) == 1:
            hasil[kode] = cocok[0]
    return hasil


def perbarui_pihps_kota(konf: Konfigurasi, hari: int = 45, hari_riwayat: int = 400, pengambil=None, tidur=time.sleep,
                        paksa_riwayat: bool = False, jenis_pasar: tuple[int, ...] = (1, 2, 3, 4)) -> dict:
    """Harga PIHPS per kabupaten/kota untuk tiap jenis pasar (tradisional, modern, pedagang besar, produsen) bila PIHPS
    memilikinya (untuk Provinsi Bengkulu baru Kota Bengkulu). Disimpan sebagai konteks di data/masuk/konteks/pihps_kota_<tahun>.csv
    dengan indikator berbeda per jenis pasar; tidak masuk berkas harga utama. Jenis selain tradisional dipakai untuk melihat
    rantai harga (produsen -> pedagang besar -> eceran) dan sebagai pembanding."""
    folder = konf.akar / "data" / "masuk" / "konteks"
    folder.mkdir(parents=True, exist_ok=True)
    galat: list[str] = []
    sudah_ada = any(folder.glob("pihps_kota_*.csv"))
    akhir = konf.hari_ini
    mulai = akhir - timedelta(days=hari if sudah_ada and not paksa_riwayat else hari_riwayat)
    peta = peta_varian(konf)
    baris, per_wilayah, tidak = [], {}, []
    for jenis in jenis_pasar:
        try:
            daftar = daftar_kabupaten_pihps(pengambil, jenis)
        except Exception as e:  # noqa: BLE001
            log.warning("daftar kabupaten PIHPS jenis %s gagal: %s", jenis, e)
            galat.append(f"daftar kabupaten PIHPS jenis {jenis}: {e}")
            continue
        peta_w = petakan_kabupaten(daftar, konf)
        if jenis == 1:
            tidak = sorted(w.nama for k, w in konf.wilayah.items() if k != WILAYAH_PIHPS and k not in peta_w)
        for kode, kab in peta_w.items():
            n_awal = len(baris)
            awal = mulai
            while awal <= akhir:
                ujung = min(akhir, awal + timedelta(days=89))
                try:
                    data = _ambil_json(URL_PIHPS, {"price_type_id": jenis, "comcat_id": "", "province_id": PROVINSI_PIHPS,
                                                   "regency_id": kab["id"], "market_id": "", "tipe_laporan": 1,
                                                   "start_date": awal.isoformat(), "end_date": ujung.isoformat()}, pengambil)
                    b, _ = ubah_pihps(data, peta, kode, INDIKATOR_JENIS[jenis])
                    baris += b
                except Exception as e:  # noqa: BLE001
                    log.warning("PIHPS %s jenis %s %s..%s gagal: %s", kab["nama"], jenis, awal, ujung, e)
                    galat.append(f"PIHPS {kab['nama']} jenis {jenis} {awal}..{ujung}: {e}")
                awal = ujung + timedelta(days=1)
                if awal <= akhir:
                    tidur(JEDA_PIHPS)
            kunci = kode if jenis == 1 else f"{kode}:{INDIKATOR_JENIS[jenis]}"
            per_wilayah[kunci] = {"nama": kab["nama"], "id": kab["id"], "baris": len(baris) - n_awal}
    return {"wilayah": per_wilayah, "tidak_ditemukan": tidak, "galat": galat,
            "baris_baru": _gabung_tulis(folder, "pihps_kota", baris) if baris else 0}


def perbarui(konf: Konfigurasi, pengambil=None, tidur=time.sleep) -> dict:
    return {"bmkg": perbarui_bmkg(konf, pengambil), "pihps": perbarui_pihps(konf, pengambil=pengambil, tidur=tidur),
            "pihps_kota": perbarui_pihps_kota(konf, pengambil=pengambil, tidur=tidur)}

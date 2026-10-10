"""Konektor harga harian SP2KP Kementerian Perdagangan (sp2kp.kemendag.go.id) per pasar.

SP2KP (Sistem Pemantauan Pasar dan Kebutuhan Pokok) mencatat harga eceran harian di satu pasar acuan tiap kabupaten/kota.
Untuk wilayah proyek ini:
  Bengkulu Tengah (1709) -> Pasar Taba Penanjung (id SP2KP 117)  -> kode pasar sistem PSR01
  Kepahiang (1708)       -> Pasar Kepahiang (id SP2KP 116)       -> PSR91 (pembanding produksi)
  Kota Bengkulu (1771)   -> Pasar Panorama (id SP2KP 118)        -> PSR92 (pembanding konsumsi)

Alur, sesuai aturan laporan (data mentah disimpan apa adanya, pemetaan bisa ditinjau):
  1. ambil   : POST report/api/average-price/export-area-daily-json (publik, tanpa login) per 30 hari dengan jeda.
               Hasil mentah disimpan di data/mentah/sp2kp/harian_<tahun>.csv (nama varian dan satuan asli SP2KP).
  2. petakan : config/peta_varian_sp2kp.csv memetakan varian SP2KP ke kode varian sistem. Hanya baris berstatus
               "setuju" yang dipakai; varian SP2KP baru otomatis ditambahkan berstatus "baru" untuk ditinjau analis.
  3. ke_harga: baris yang disetujui ditulis ulang ke data/masuk/harga/sp2kp_<tahun>.csv (kode sumber BD-SP2KP) supaya
               melewati quality gate dan analisis yang sama dengan data lain. Berkas ini selalu dibuat ulang dari data mentah.
"""

from __future__ import annotations

import csv
import json
import logging
import time
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from .konfigurasi import Konfigurasi

log = logging.getLogger(__name__)

URL_API = "https://api-sp2kp.kemendag.go.id"
URL_HARIAN = f"{URL_API}/report/api/average-price/export-area-daily-json"
TAJUK = {"User-Agent": "Mozilla/5.0 (pemantauan harga BPS Bengkulu Tengah)", "Accept": "application/json, text/plain, */*",
         "Origin": "https://sp2kp.kemendag.go.id", "Referer": "https://sp2kp.kemendag.go.id/"}
KODE_PROVINSI = "17"
KODE_SUMBER = "BD-SP2KP"
PANJANG_POTONGAN = 30   # hari per permintaan (halaman SP2KP juga membatasi rentang sekitar 30 hari)
JEDA = 1.5              # detik antar permintaan supaya tidak membebani server Kemendag

# kode_wilayah sistem -> pasar SP2KP dan kode pasar sistem (config/pasar.csv)
PASAR = {
    "1709": {"pasar_id": 117, "nama": "Pasar Taba Penanjung", "kode_pasar": "PSR01"},
    "1708": {"pasar_id": 116, "nama": "Pasar Kepahiang", "kode_pasar": "PSR91"},
    "1771": {"pasar_id": 118, "nama": "Pasar Panorama", "kode_pasar": "PSR92"},
}

KOLOM_MENTAH = ["tanggal", "kode_wilayah", "pasar_id", "variant_id", "variant", "satuan", "kuantitas", "harga"]
KOLOM_PETA = ["variant_id", "variant_sp2kp", "satuan_sp2kp", "kode_varian", "faktor", "status", "catatan"]
KOLOM_HARGA = ["tanggal", "kode_pasar", "kode_varian", "harga", "satuan", "kode_sumber", "petugas", "responden", "id_klien",
               "waktu_input", "catatan"]


def _multipart(data: dict) -> tuple[bytes, str]:
    batas = "----lintasbentengsp2kp"
    isi = b"".join(f"--{batas}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode() for k, v in data.items())
    return isi + f"--{batas}--\r\n".encode(), f"multipart/form-data; boundary={batas}"


def _post(url: str, data: dict, pengirim=None) -> dict:
    if pengirim:
        return pengirim(url, data)
    isi, jenis = _multipart(data)
    req = urllib.request.Request(url, data=isi, method="POST", headers={**TAJUK, "Content-Type": jenis})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read())


def ubah_respons(data: dict, kode_wilayah: str, pasar_id: int) -> list[dict]:
    """Respons export-area-daily-json -> baris mentah. Harga kosong atau nol dilewati (pasar tidak mencatat hari itu)."""
    baris = []
    for v in data.get("data") or []:
        for h in v.get("daftarHarga") or []:
            try:
                harga = float(h.get("harga"))
            except (TypeError, ValueError):
                continue
            if not h.get("date") or harga <= 0:
                continue
            baris.append({"tanggal": str(h["date"])[:10], "kode_wilayah": kode_wilayah, "pasar_id": str(pasar_id),
                          "variant_id": str(v.get("variant_id", "")), "variant": str(v.get("variant", "")).strip(),
                          "satuan": str(v.get("satuan", "")).strip(), "kuantitas": str(v.get("kuantitas", "")),
                          "harga": f"{harga:g}"})
    return baris


def _folder_mentah(konf: Konfigurasi) -> Path:
    return konf.akar / "data" / "mentah" / "sp2kp"


def baca_mentah(folder: Path) -> dict[tuple, dict]:
    ada: dict[tuple, dict] = {}
    for p in sorted(folder.glob("harian_*.csv")):
        with p.open(newline="", encoding="utf-8") as f:
            for b in csv.DictReader(f):
                ada[(b["tanggal"], b["kode_wilayah"], b["pasar_id"], b["variant_id"])] = b
    return ada


def _gabung_tulis(folder: Path, baru: list[dict]) -> int:
    """Gabung baris baru ke harian_<tahun>.csv; nilai baru menimpa kunci (tanggal, wilayah, pasar, varian) karena SP2KP
    bisa merevisi harga hari yang lalu."""
    folder.mkdir(parents=True, exist_ok=True)
    ada = baca_mentah(folder)
    tambah = 0
    for b in baru:
        k = (b["tanggal"], b["kode_wilayah"], b["pasar_id"], b["variant_id"])
        tambah += k not in ada
        ada[k] = b
    per_tahun: dict[str, list[dict]] = defaultdict(list)
    for b in ada.values():
        per_tahun[b["tanggal"][:4]].append(b)
    for tahun, baris in per_tahun.items():
        baris.sort(key=lambda b: (b["tanggal"], b["kode_wilayah"], int(b["variant_id"] or 0)))
        with (folder / f"harian_{tahun}.csv").open("w", newline="", encoding="utf-8") as f:
            wr = csv.DictWriter(f, fieldnames=KOLOM_MENTAH, extrasaction="ignore", lineterminator="\n")
            wr.writeheader()
            wr.writerows(baris)
    return tambah


def baca_peta(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as f:
        return {b["variant_id"].strip(): b for b in csv.DictReader(f) if b.get("variant_id", "").strip()}


def perbarui_peta(path: Path, mentah: dict[tuple, dict]) -> list[str]:
    """Tambahkan varian SP2KP yang belum ada di tabel pemetaan dengan status "baru" (tidak dipakai sampai ditinjau)."""
    peta = baca_peta(path)
    baru = {}
    for b in mentah.values():
        if b["variant_id"] not in peta and b["variant_id"] not in baru:
            baru[b["variant_id"]] = {"variant_id": b["variant_id"], "variant_sp2kp": b["variant"], "satuan_sp2kp": b["satuan"],
                                     "kode_varian": "", "faktor": "1", "status": "baru",
                                     "catatan": "varian SP2KP baru; tentukan padanannya lalu ubah status menjadi setuju"}
    if not baru:
        return []
    semua = list(peta.values()) + sorted(baru.values(), key=lambda b: int(b["variant_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=KOLOM_PETA, extrasaction="ignore", lineterminator="\n")
        wr.writeheader()
        wr.writerows(semua)
    return sorted(baru)


def perbarui(konf: Konfigurasi, hari: int = 30, hari_riwayat: int = 1830, paksa_riwayat: bool = False, pengirim=None,
             tidur=time.sleep) -> dict:
    """Ambil harga harian SP2KP untuk pasar acuan tiap wilayah. Bila data mentah belum ada (atau paksa_riwayat), ambil
    riwayat `hari_riwayat` hari; selain itu `hari` hari terakhir (menangkap revisi)."""
    folder = _folder_mentah(konf)
    sudah_ada = any(folder.glob("harian_*.csv"))
    akhir = konf.hari_ini
    mulai = akhir - timedelta(days=hari if sudah_ada and not paksa_riwayat else hari_riwayat)
    baris: list[dict] = []
    galat: list[str] = []
    per_wilayah: dict[str, dict] = {}
    pertama = True
    for kode, p in PASAR.items():
        if kode not in konf.wilayah:
            continue
        n0 = len(baris)
        awal = mulai
        while awal <= akhir:
            ujung = min(akhir, awal + timedelta(days=PANJANG_POTONGAN - 1))
            if not pertama:
                tidur(JEDA)
            pertama = False
            kirim = {"start_date": awal.isoformat(), "end_date": ujung.isoformat(), "level": "3", "variant_ids": "",
                     "kode_provinsi": KODE_PROVINSI, "kode_kab_kota": kode, "pasar_id": str(p["pasar_id"]),
                     "skip_sat_sun": "true", "tipe_komoditas": "1"}
            for coba in range(3):
                try:
                    baris += ubah_respons(_post(URL_HARIAN, kirim, pengirim), kode, p["pasar_id"])
                    break
                except Exception as e:  # noqa: BLE001
                    if coba == 2:
                        log.warning("SP2KP %s %s..%s gagal: %s", p["nama"], awal, ujung, e)
                        galat.append(f"SP2KP {p['nama']} {awal}..{ujung}: {e}")
                    else:
                        tidur(5 * (coba + 1))
            awal = ujung + timedelta(days=1)
        tgl = sorted({b["tanggal"] for b in baris[n0:]})
        per_wilayah[kode] = {"pasar": p["nama"], "baris": len(baris) - n0, "awal": tgl[0] if tgl else None,
                             "akhir": tgl[-1] if tgl else None}
    tambah = _gabung_tulis(folder, baris) if baris else 0
    varian_baru = perbarui_peta(konf.akar / "config" / "peta_varian_sp2kp.csv", baca_mentah(folder)) if baris else []
    return {"wilayah": per_wilayah, "baris": len(baris), "baris_baru": tambah, "varian_baru": varian_baru, "galat": galat,
            "rentang": [mulai.isoformat(), akhir.isoformat()]}


def ke_harga(konf: Konfigurasi) -> dict:
    """Tulis ulang data/masuk/harga/sp2kp_<tahun>.csv dari data mentah dan pemetaan yang disetujui."""
    folder_harga = konf.akar / "data" / "masuk" / "harga"
    mentah = baca_mentah(_folder_mentah(konf))
    peta = {k: v for k, v in baca_peta(konf.akar / "config" / "peta_varian_sp2kp.csv").items()
            if v.get("status", "").strip().lower() == "setuju" and v.get("kode_varian", "").strip()}
    galat = sorted({f"kode varian {v['kode_varian']} (SP2KP {v['variant_sp2kp']}) tidak ada di config/komoditas.csv"
                    for v in peta.values() if v["kode_varian"].strip().upper() not in konf.varian})
    pasar_wilayah = {str(p["pasar_id"]): (kode, p) for kode, p in PASAR.items()}
    per_tahun: dict[str, list[list]] = defaultdict(list)
    dipakai: dict[str, int] = defaultdict(int)
    for (tgl, _, pid, vid), b in sorted(mentah.items()):
        m = peta.get(vid)
        if m is None or pid not in pasar_wilayah:
            continue
        kode_varian = m["kode_varian"].strip().upper()
        varian = konf.varian.get(kode_varian)
        kode_pasar = pasar_wilayah[pid][1]["kode_pasar"]
        if varian is None or kode_pasar not in konf.pasar:
            continue
        try:
            harga = float(b["harga"]) * float(m.get("faktor") or 1)
        except ValueError:
            continue
        per_tahun[tgl[:4]].append([tgl, kode_pasar, kode_varian, f"{round(harga, 2):g}", varian.satuan, KODE_SUMBER, "", "", "", "",
                                   f"SP2KP Kemendag: {b['variant']} ({pasar_wilayah[pid][1]['nama']})"])
        dipakai[f"{pasar_wilayah[pid][0]}:{kode_varian}"] += 1
    folder_harga.mkdir(parents=True, exist_ok=True)
    ringkas = {}
    for tahun, baris in sorted(per_tahun.items()):
        path = folder_harga / f"sp2kp_{tahun}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(KOLOM_HARGA)
            w.writerows(baris)
        ringkas[path.name] = len(baris)
    for path in folder_harga.glob("sp2kp_*.csv"):
        if path.name not in ringkas:
            path.unlink()
    return {"berkas": ringkas, "per_wilayah_varian": dict(sorted(dipakai.items())), "galat": galat}


def ringkas_cakupan(konf: Konfigurasi) -> dict:
    """Ringkasan data mentah per wilayah dan varian SP2KP (rentang tanggal, jumlah hari) untuk laporan sumber data."""
    mentah = baca_mentah(_folder_mentah(konf))
    grup: dict[tuple, list[str]] = defaultdict(list)
    nama: dict[str, str] = {}
    for (tgl, wil, _, vid), b in mentah.items():
        grup[(wil, vid)].append(tgl)
        nama[vid] = b["variant"]
    return {f"{w}:{v}": {"variant": nama[v], "hari": len(t), "awal": min(t), "akhir": max(t)} for (w, v), t in sorted(grup.items())}

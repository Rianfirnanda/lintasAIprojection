"""Skema dan validasi config/pengaturan.json.

config/skema_pengaturan.json adalah sumber kebenaran isian yang boleh diubah lewat panel admin (site/pengaturan.html).
Panel membaca skema yang sama untuk membuat formulir dan memeriksa isian, lalu pipeline memeriksanya lagi di sini
sebelum dipakai, supaya nilai yang salah tidak sampai merusak hasil analisis.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

BERKAS_SKEMA = "skema_pengaturan.json"
TIPE_ANGKA = ("bulat", "desimal")


def muat_skema(folder_config: Path | str) -> dict | None:
    """Skema pengaturan, atau None bila berkasnya tidak ada (mis. salinan lama tanpa panel admin)."""
    path = Path(folder_config) / BERKAS_SKEMA
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def ambil(data: object, jalur: str) -> tuple[bool, object]:
    """Nilai pada jalur bertitik, mis. 'sinyal.ambang_persen.pokok' atau 'sinyal.rasio_volatilitas_batas.0'."""
    sekarang = data
    for bagian in jalur.split("."):
        if isinstance(sekarang, dict) and bagian in sekarang:
            sekarang = sekarang[bagian]
        elif isinstance(sekarang, list) and bagian.isdigit() and int(bagian) < len(sekarang):
            sekarang = sekarang[int(bagian)]
        else:
            return False, None
    return True, sekarang


def _angka(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _nilai_pilihan(kolom: dict) -> list:
    return [p["nilai"] for p in kolom.get("pilihan", [])]


def _periksa_kolom(kolom: dict, nilai: object) -> str | None:
    """Pesan masalah untuk satu isian, atau None bila isiannya sah."""
    tipe = kolom["tipe"]
    if tipe in TIPE_ANGKA:
        if not _angka(nilai):
            return "harus berupa angka"
        if tipe == "bulat" and float(nilai) != int(nilai):
            return "harus berupa bilangan bulat"
        if not (kolom["min"] <= nilai <= kolom["maks"]):
            return f"harus antara {kolom['min']} dan {kolom['maks']}"
    elif tipe == "saklar":
        if not isinstance(nilai, bool):
            return "harus berupa ya atau tidak"
    elif tipe == "pilihan":
        if nilai not in _nilai_pilihan(kolom) or isinstance(nilai, (list, dict)):
            return "bukan salah satu pilihan yang tersedia"
    elif tipe == "banyak_pilihan":
        boleh = _nilai_pilihan(kolom)
        if not isinstance(nilai, list) or any(isinstance(x, bool) or x not in boleh for x in nilai):
            return "berisi pilihan yang tidak dikenal"
        if len(set(nilai)) != len(nilai):
            return "berisi pilihan yang ganda"
        if len(nilai) < kolom.get("minimal", 0):
            return f"pilih minimal {kolom.get('minimal', 0)}"
    elif tipe == "urutan":
        boleh = {x for p in kolom.get("pilihan", []) for x in p["nilai"]}
        if not isinstance(nilai, list) or not nilai or any(not isinstance(x, str) or x not in boleh for x in nilai):
            return "harus berisi nama AI yang dikenal"
        if len(set(nilai)) != len(nilai):
            return "berisi AI yang ganda"
    elif tipe == "teks":
        if not isinstance(nilai, str):
            return "harus berupa teks"
        if len(nilai) > kolom.get("maks_panjang", 200):
            return "terlalu panjang"
        if kolom.get("pola") and not re.fullmatch(kolom["pola"], nilai):
            return kolom.get("pesan_pola") or "bentuknya tidak sesuai"
    elif tipe == "url":
        if not isinstance(nilai, str):
            return "harus berupa teks"
        if nilai == "":
            return None if kolom.get("boleh_kosong") else "tidak boleh kosong"
        if len(nilai) > 300 or not re.fullmatch(r"https?://[^\s/$.?#][^\s]*", nilai):
            return "harus berupa alamat web yang diawali https://"
    else:
        return f"jenis isian tidak dikenal: {tipe}"
    return None


def periksa(pengaturan: dict, skema: dict) -> list[tuple[str, str]]:
    """Daftar (jalur, pesan) untuk semua isian yang salah. Kosong berarti pengaturan sah."""
    masalah: list[tuple[str, str]] = []
    for kolom in skema["kolom"]:
        ada, nilai = ambil(pengaturan, kolom["jalur"])
        if not ada:
            masalah.append((kolom["jalur"], f"{kolom['label']}: belum diisi"))
            continue
        pesan = _periksa_kolom(kolom, nilai)
        if pesan:
            masalah.append((kolom["jalur"], f"{kolom['label']}: {pesan}"))
    for aturan in skema.get("aturan_silang", []):
        (ja, a), (jb, b) = (ambil(pengaturan, j) for j in aturan["jalur"])
        if not (ja and jb and _angka(a) and _angka(b)):
            continue  # masalahnya sudah dilaporkan pada isian masing-masing
        benar = a < b if aturan["jenis"] == "kurang_dari" else a <= b
        if not benar:
            masalah.append((aturan["jalur"][1], aturan["pesan"]))
    return masalah


def periksa_berkas(folder_config: Path | str) -> list[tuple[str, str]]:
    """Periksa config/pengaturan.json terhadap skemanya (kosong bila skema tidak ada)."""
    skema = muat_skema(folder_config)
    if skema is None:
        return []
    pengaturan = json.loads((Path(folder_config) / "pengaturan.json").read_text(encoding="utf-8"))
    return periksa(pengaturan, skema)


def pastikan_sah(pengaturan: dict, skema: dict | None) -> None:
    """Lempar ValueError berisi semua masalah bila pengaturan tidak sah."""
    if skema is None:
        return
    masalah = periksa(pengaturan, skema)
    if masalah:
        rincian = "; ".join(f"{j}: {p}" for j, p in masalah[:8]) + (f"; dan {len(masalah) - 8} lainnya" if len(masalah) > 8 else "")
        raise ValueError(f"config/pengaturan.json tidak sah: {rincian}")

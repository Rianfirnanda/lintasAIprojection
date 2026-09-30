"""Akun dan peran pengguna dashboard.

Situs berjalan statis (GitHub Pages / Firebase Hosting), jadi akun contoh di `config/pengguna.json` hanya
mengatur TAMPILAN per peran (menu dan beranda). Berkas ini terbit ke situs publik dan tidak mengunci data.
Pembatasan akses sungguhan memakai Firebase Authentication (`config/firebase.json`) dengan aturan Firestore.

Sandi disimpan sebagai SHA-256 dari "garam:id:sandi". Rumus yang sama dipakai di browser (assets/akses.js).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

PERAN = ("masyarakat", "petugas", "operator", "analis", "tpid", "admin")


def hash_sandi(garam: str, id_akun: str, sandi: str) -> str:
    return hashlib.sha256(f"{garam}:{id_akun.strip().lower()}:{sandi}".encode("utf-8")).hexdigest()


def entri_akun(garam: str, id_akun: str, nama: str, peran: str, sandi: str) -> dict:
    if peran not in PERAN:
        raise ValueError(f"peran harus salah satu dari {', '.join(PERAN)}")
    return {"id": id_akun.strip().lower(), "nama": nama, "peran": peran, "sandi_hash": hash_sandi(garam, id_akun, sandi)}


def periksa(data: dict) -> list[str]:
    """Kembalikan daftar masalah pada isi config/pengguna.json (kosong bila sah)."""
    masalah = []
    if not data.get("garam"):
        masalah.append("garam kosong")
    ids = set()
    for a in data.get("akun", []):
        if a.get("peran") not in PERAN:
            masalah.append(f"peran tidak dikenal untuk akun {a.get('id')}")
        if not a.get("id") or not a.get("sandi_hash"):
            masalah.append("akun tanpa id atau sandi_hash")
        if a.get("id") in ids:
            masalah.append(f"id ganda: {a.get('id')}")
        ids.add(a.get("id"))
    return masalah


def muat(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def firebase_aktif(data: dict | None) -> bool:
    k = (data or {}).get("konfigurasi") or {}
    return bool(k.get("apiKey") and k.get("projectId"))

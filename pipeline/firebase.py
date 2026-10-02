"""Penghubung ke Firebase: konfigurasi web untuk situs dan aturan Firestore siap terbit.

Konfigurasi web Firebase (apiKey, projectId, dan seterusnya) memang dipakai terbuka oleh browser, tapi tetap tidak
ditulis di repositori. Isinya diambil dari GitHub Secret FIREBASE_WEB_CONFIG saat pipeline berjalan, atau dari
config/firebase.json bila dijalankan di komputer sendiri.

Daftar admin pertama (FIREBASE_ADMIN_AWAL) disisipkan ke firestore.rules hanya saat terbit, supaya email tidak
tersimpan di repositori.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

KOLOM_WAJIB = ("apiKey", "authDomain", "projectId", "appId")
PENANDA_ADMIN = "/*ADMIN_AWAL*/[]"
_EMAIL = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")


def konfigurasi_web(akar: Path, env: dict | None = None) -> dict | None:
    """Konfigurasi web Firebase dari env FIREBASE_WEB_CONFIG (JSON) atau config/firebase.json. None bila belum diisi."""
    env = os.environ if env is None else env
    mentah = (env.get("FIREBASE_WEB_CONFIG") or "").strip()
    if mentah:
        data = _baca_objek(mentah)
        konf = data.get("konfigurasi", data) if isinstance(data, dict) else None
    else:
        path = akar / "config" / "firebase.json"
        konf = (json.loads(path.read_text(encoding="utf-8")).get("konfigurasi") if path.exists() else None)
    if not isinstance(konf, dict) or not all(konf.get(k) for k in ("apiKey", "projectId")):
        return None
    kurang = [k for k in KOLOM_WAJIB if not konf.get(k)]
    if kurang:
        raise ValueError(f"Konfigurasi Firebase belum lengkap, kurang: {', '.join(kurang)}")
    hasil = {k: str(v) for k, v in konf.items() if isinstance(v, (str, int)) and k in (
        "apiKey", "authDomain", "projectId", "appId", "storageBucket", "messagingSenderId", "measurementId")}
    if env.get("FIREBASE_EMULATOR") == "1":
        # Hanya untuk uji di komputer sendiri; situs mengabaikan ini bila tidak dibuka dari localhost.
        hasil["emulator"] = {"auth": "http://127.0.0.1:9099", "firestore": ["127.0.0.1", 8080]}
    return hasil


def _baca_objek(teks: str) -> dict:
    """JSON, atau objek JavaScript yang disalin langsung dari Firebase Console (const firebaseConfig = {...};)."""
    try:
        return json.loads(teks)
    except json.JSONDecodeError:
        pass
    awal, akhir = teks.find("{"), teks.rfind("}")
    if awal < 0 or akhir < awal:
        raise ValueError("FIREBASE_WEB_CONFIG bukan JSON yang sah: tidak ada tanda { }")
    isi = teks[awal:akhir + 1]
    isi = re.sub(r"//[^\n]*", "", isi)                               # komentar satu baris
    isi = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', isi)  # kunci tanpa tanda kutip
    isi = re.sub(r"'([^'\\]*)'", r'"\1"', isi)                       # kutip tunggal
    isi = re.sub(r",\s*}", "}", isi)                                   # koma di akhir
    try:
        return json.loads(isi)
    except json.JSONDecodeError as e:
        raise ValueError(f"FIREBASE_WEB_CONFIG bukan JSON yang sah: {e.msg}") from None


def daftar_admin_awal(teks: str | None) -> list[str]:
    """Email admin pertama dari teks dipisah koma, spasi, atau baris baru. Galat bila ada yang bukan email."""
    hasil = []
    for bagian in re.split(r"[\s,;]+", (teks or "").strip().lower()):
        if not bagian:
            continue
        if not _EMAIL.match(bagian):
            raise ValueError(f"FIREBASE_ADMIN_AWAL berisi alamat yang bukan email: {bagian!r}")
        if bagian not in hasil:
            hasil.append(bagian)
    return hasil


def aturan_dengan_admin(teks_aturan: str, emails: list[str]) -> str:
    """firestore.rules dengan daftar admin pertama terisi."""
    if PENANDA_ADMIN not in teks_aturan:
        raise ValueError(f"Penanda {PENANDA_ADMIN} tidak ditemukan di firestore.rules")
    daftar = "[" + ", ".join(f"'{e}'" for e in emails) + "]"
    return teks_aturan.replace(PENANDA_ADMIN, daftar, 1)

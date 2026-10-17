"""Jatah kuota pencarian web Tavily supaya kredit gratis bulanan tidak habis sebelum akhir bulan.

Sisa kredit dibaca langsung dari Tavily (GET https://api.tavily.com/usage), jadi pemakaian dari mana pun ikut terhitung:
AI harian, berita lokal, permintaan dari panel Pengaturan, dan AI Data Finder yang dijalankan di browser admin.

Cara membaginya:
  - Sebagian kecil kuota bulanan (bawaan 10%) disisihkan sebagai cadangan.
  - Sisanya dibagi rata ke hari yang tersisa dalam bulan ini, menjadi jatah harian.
  - Pemakaian hari ini dihitung dari angka pemakaian pada awal hari (disimpan di Firestore lbp_status/kuota_tavily), jadi
    beberapa proses dalam sehari berbagi jatah yang sama.
  - Tiap pencarian mengambil satu kredit dari ANGGARAN. Bila jatahnya habis, pencarian dilewati dengan alasan yang jelas
    dan AI tetap bekerja tanpa pencarian web (perilaku yang sama seperti saat kunci Tavily belum diisi).
Bila sisa kuota tidak bisa dibaca (jaringan, Tavily berubah), pencarian tidak dibatasi seperti sebelumnya.
"""

from __future__ import annotations

import calendar
import json
import logging
import os
import urllib.request
from datetime import date, datetime, timezone
from math import floor
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

URL_USAGE = "https://api.tavily.com/usage"
WIB = ZoneInfo("Asia/Jakarta")
CADANGAN_PERSEN = 10
KREDIT_PER_PERMINTAAN_AI = 3  # pencari_data.kueri_web: tiga pencarian per permintaan AI Data Finder


class Anggaran:
    """Sisa kredit yang boleh dipakai proses ini. None berarti tidak dibatasi."""

    def __init__(self) -> None:
        self.sisa: int | None = None
        self.alasan = ""

    def atur(self, sisa: int | None, alasan: str = "") -> None:
        self.sisa = None if sisa is None else max(0, int(sisa))
        self.alasan = alasan

    def pakai(self, n: int = 1) -> bool:
        if self.sisa is None:
            return True
        if self.sisa >= n:
            self.sisa -= n
            return True
        return False

    def pesan_habis(self) -> str:
        return self.alasan or "jatah pencarian web hari ini sudah habis (kuota bulanan Tavily dijaga sampai akhir bulan)"


ANGGARAN = Anggaran()


def _get_json(url: str, kunci: str, batas_waktu: int = 20) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {kunci}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=batas_waktu) as r:
        return json.loads(r.read())


def baca_pemakaian(kunci: str, ambil=None) -> dict | None:
    """{"terpakai", "batas"} kredit bulan ini menurut Tavily, atau None bila tidak bisa dibaca."""
    try:
        d = (ambil or _get_json)(URL_USAGE, kunci)
    except Exception as e:  # noqa: BLE001 - jaringan atau galat Tavily: jangan hentikan proses
        log.warning("sisa kuota Tavily tidak bisa dibaca: %s", e)
        return None
    akun, k = d.get("account") or {}, d.get("key") or {}
    terpakai = akun.get("plan_usage", k.get("usage"))
    batas = akun.get("plan_limit") or k.get("limit")
    try:
        terpakai, batas = int(terpakai), int(batas)
    except (TypeError, ValueError):
        return None
    return {"terpakai": terpakai, "batas": batas} if batas > 0 else None


def hari_tersisa(hari: date) -> int:
    """Jumlah hari dari `hari` sampai akhir bulan, termasuk hari ini."""
    return calendar.monthrange(hari.year, hari.month)[1] - hari.day + 1


def hitung_jatah(info: dict, terpakai_awal_hari: int, hari: date, cadangan_persen: float = CADANGAN_PERSEN) -> dict:
    batas, terpakai = info["batas"], info["terpakai"]
    cadangan = batas * cadangan_persen / 100
    sisa_awal = batas - terpakai_awal_hari
    jatah_harian = max(0, floor((sisa_awal - cadangan) / hari_tersisa(hari)))
    terpakai_hari_ini = max(0, terpakai - terpakai_awal_hari)
    return {"batas": batas, "terpakai": terpakai, "sisa_bulan": max(0, batas - terpakai), "cadangan": round(cadangan),
            "jatah_harian": jatah_harian, "terpakai_hari_ini": terpakai_hari_ini,
            "sisa_jatah": max(0, jatah_harian - terpakai_hari_ini), "hari_tersisa": hari_tersisa(hari)}


def siapkan(akar=None, sisihkan: int = 0, manual: bool = False, db=None, ambil=None, hari: date | None = None) -> dict | None:
    """Hitung jatah lalu pasang ke ANGGARAN. `sisihkan`: kredit yang disisakan untuk proses lain hari ini (mis. berita
    lokal yang belum berjalan). `manual`: permintaan yang ditekan admin; boleh melewati jatah harian, tetapi tidak
    menyentuh cadangan bulanan. Mengembalikan rincian jatah, atau None bila tidak dibatasi."""
    kunci = os.environ.get("TAVILY_API_KEY")
    if not kunci:
        ANGGARAN.atur(None)
        return None
    info = baca_pemakaian(kunci, ambil)
    if info is None:
        ANGGARAN.atur(None)
        return None
    hari = hari or datetime.now(WIB).date()
    awal = info["terpakai"]
    ref = None
    try:
        from . import firestore_sinkron

        if db is None and firestore_sinkron.aktif():
            db = firestore_sinkron.klien()
        if db is not None:
            ref = db.collection("lbp_status").document("kuota_tavily")
            snap = ref.get()
            lama = (snap.to_dict() or {}) if snap.exists else {}
            # Angka awal hari dipakai ulang hanya pada hari dan bulan kuota yang sama (setelah kuota direset, mulai lagi).
            if lama.get("tanggal") == hari.isoformat() and int(lama.get("awal_hari", -1)) <= info["terpakai"]:
                awal = int(lama["awal_hari"])
    except Exception as e:  # noqa: BLE001 - tanpa Firestore jatah dihitung untuk proses ini saja
        log.warning("status kuota Tavily tidak bisa dibaca dari Firestore: %s", e)
        ref = None
    j = hitung_jatah(info, awal, hari)
    if manual:
        boleh = max(0, j["sisa_bulan"] - j["cadangan"])
        ANGGARAN.atur(boleh, "kuota bulanan Tavily tinggal cadangan, pencarian web dilewati")
    else:
        boleh = max(0, j["sisa_jatah"] - max(0, sisihkan))
        ANGGARAN.atur(boleh)
    j["boleh_dipakai"] = boleh
    if ref is not None:
        try:
            ref.set({"tanggal": hari.isoformat(), "awal_hari": awal, **{k: v for k, v in j.items() if k != "boleh_dipakai"},
                     "diperbarui": datetime.now(timezone.utc)})
        except Exception as e:  # noqa: BLE001
            log.warning("status kuota Tavily tidak tersimpan: %s", e)
    log.info("kuota Tavily: sisa %d dari %d bulan ini, jatah hari ini %d, sudah terpakai hari ini %d, boleh dipakai %d",
             j["sisa_bulan"], j["batas"], j["jatah_harian"], j["terpakai_hari_ini"], boleh)
    return j

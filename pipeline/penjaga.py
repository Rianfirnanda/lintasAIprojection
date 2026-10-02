"""Penjaga antrean: memeriksa Firestore terus-menerus dan menjalankan pengolahan begitu ada kiriman dari situs.

Jadwal (cron) GitHub Actions bisa tertunda berjam-jam saat ramai, jadi pemeriksaan berkala tidak bisa diandalkan.
Penjaga ini berjalan sebagai satu job panjang (antrean.yml): tiap menit pada jam kerja (tiap 10 menit di luar jam
kerja) memanggil firestore_sinkron.perlu_jalan, lalu menjalankan pipeline.yml lewat workflow_dispatch. Menjelang
batas waktu job, penjaga menjalankan dirinya lagi, sehingga selalu ada satu penjaga yang aktif. Repositori publik
tidak dibatasi menit Actions, jadi tetap gratis.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import firestore_sinkron

log = logging.getLogger(__name__)

WIB = timezone(timedelta(hours=7))
JEDA_KERJA = 60          # detik antar pemeriksaan pada jam kerja
JEDA_LUAR = 600          # detik antar pemeriksaan di luar jam kerja
JEDA_SETELAH_JALAN = 240  # beri waktu pipeline mulai dan menandai dirinya "berjalan"
JEDA_BERULANG = 900       # alasan yang sama terus muncul (pengolahan gagal mengambilnya): jangan memicu terus-menerus


def jam_kerja(t: datetime) -> bool:
    w = t.astimezone(WIB)
    return w.weekday() < 5 and 7 <= w.hour < 18


def jalankan_alur(berkas: str, ref: str = "main", inputs: dict | None = None) -> None:
    """workflow_dispatch lewat GITHUB_TOKEN (dispatch termasuk yang boleh memicu run baru dari GITHUB_TOKEN)."""
    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/workflows/{berkas}/dispatches", method="POST",
        data=json.dumps({"ref": ref, **({"inputs": inputs} if inputs else {})}).encode(),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30):
        pass


def segarkan_tanda(akar: Path, ref: str = "main") -> None:
    """Tanda kiriman yang sudah diambil ditulis pipeline ke repositori; ambil versi terbarunya sebelum memeriksa."""
    try:
        subprocess.run(["git", "fetch", "-q", "--depth=1", "origin", ref], cwd=akar, check=True, timeout=60)
        isi = subprocess.run(["git", "show", f"origin/{ref}:{firestore_sinkron.BERKAS_TANDA.as_posix()}"], cwd=akar,
                             check=True, capture_output=True, timeout=30).stdout
        (akar / firestore_sinkron.BERKAS_TANDA).write_bytes(isi)
    except (subprocess.SubprocessError, OSError) as e:
        log.warning("tanda tidak bisa diperbarui: %s", e)


def jaga(akar: Path, menit: float, *, cek=None, dispatch=jalankan_alur, segarkan=segarkan_tanda,
         tidur=time.sleep, sekarang=lambda: datetime.now(timezone.utc)) -> int:
    """Periksa sampai `menit` habis. Mengembalikan jumlah pengolahan yang dijalankan."""
    cek = cek or (lambda: firestore_sinkron.perlu_jalan(akar))
    selesai = sekarang() + timedelta(minutes=menit)
    jumlah, alasan_lalu, ulang = 0, None, 0
    while sekarang() < selesai:
        segarkan(akar)
        try:
            jalan, alasan = cek()
        except Exception as e:  # noqa: BLE001 - gangguan sesaat Firestore tidak boleh menghentikan penjaga
            jalan, alasan = False, f"galat: {e}"
        if jalan:
            ulang = ulang + 1 if alasan == alasan_lalu else 1
            alasan_lalu = alasan
            try:
                dispatch("pipeline.yml")
                jumlah += 1
                print(f"{sekarang().astimezone(WIB):%H.%M} JALANKAN pengolahan: {alasan}", flush=True)
                tidur(JEDA_BERULANG if ulang >= 3 else JEDA_SETELAH_JALAN)
                continue
            except Exception as e:  # noqa: BLE001
                print(f"{sekarang().astimezone(WIB):%H.%M} pengolahan gagal dijalankan: {e}", flush=True)
        alasan_lalu, ulang = None, 0
        jeda = JEDA_KERJA if jam_kerja(sekarang()) else JEDA_LUAR
        tidur(max(0.0, min(jeda, (selesai - sekarang()).total_seconds())))
    return jumlah

"""Layanan publik: pengaduan data dan Survei Kepuasan Masyarakat (SKM) dari GitHub Issue Forms.

IKM dihitung sesuai PermenPANRB No. 14 Tahun 2017: nilai rata-rata tiap unsur (NRR) x bobot 1/9, dijumlah,
lalu dikonversi x 25. Mutu: A (88,31–100) Sangat Baik, B (76,61–88,30) Baik, C (65,00–76,60) Kurang Baik,
D (25,00–64,99) Tidak Baik.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import date, datetime
from statistics import mean, median

log = logging.getLogger(__name__)

LABEL_PENGADUAN = "pengaduan-data"
LABEL_SKM = "skm"
UNSUR = {
    "U1": "Persyaratan", "U2": "Sistem, mekanisme, dan prosedur", "U3": "Waktu penyelesaian", "U4": "Biaya/tarif",
    "U5": "Produk spesifikasi jenis pelayanan", "U6": "Kompetensi pelaksana", "U7": "Perilaku pelaksana",
    "U8": "Penanganan pengaduan, saran, dan masukan", "U9": "Sarana dan prasarana",
}
_BAGIAN = re.compile(r"^###\s+(.+?)\s*$", re.M)


def urai_formulir(isi: str) -> dict[str, str]:
    """Ubah badan issue dari Issue Forms ('### Label' diikuti jawaban) menjadi {label: jawaban}."""
    hasil = {}
    posisi = list(_BAGIAN.finditer(isi or ""))
    for i, m in enumerate(posisi):
        akhir = posisi[i + 1].start() if i + 1 < len(posisi) else len(isi)
        jawaban = isi[m.end():akhir].strip()
        hasil[m.group(1).strip()] = "" if jawaban == "_No response_" else jawaban
    return hasil


def mutu_ikm(ikm: float) -> tuple[str, str]:
    if ikm >= 88.31:
        return "A", "Sangat Baik"
    if ikm >= 76.61:
        return "B", "Baik"
    if ikm >= 65.0:
        return "C", "Kurang Baik"
    return "D", "Tidak Baik"


def hitung_ikm(issue_skm: list[dict]) -> dict:
    nilai: dict[str, list[int]] = {k: [] for k in UNSUR}
    pengguna = Counter()
    responden = 0
    for issue in issue_skm:
        jawaban = urai_formulir(issue.get("body") or "")
        skor = {}
        for label, isi in jawaban.items():
            kode = label.split(".", 1)[0].strip().upper()
            if kode in UNSUR and isi.strip() in ("1", "2", "3", "4"):
                skor[kode] = int(isi.strip())
        if len(skor) < len(UNSUR):
            continue  # tidak lengkap / bukan formulir SKM
        responden += 1
        for k, v in skor.items():
            nilai[k].append(v)
        pengguna[jawaban.get("Jenis pengguna") or "Tidak diisi"] += 1
    if not responden:
        return {"responden": 0, "ikm": None}
    nrr = {k: round(mean(v), 3) for k, v in nilai.items()}
    ikm = round(sum(v / len(UNSUR) for v in nrr.values()) * 25, 2)
    mutu, kinerja = mutu_ikm(ikm)
    return {
        "responden": responden, "ikm": ikm, "mutu": mutu, "kinerja": kinerja,
        "nrr_per_unsur": [{"kode": k, "unsur": UNSUR[k], "nrr": nrr[k]} for k in UNSUR],
        "unsur_terendah": min(nrr, key=nrr.get), "per_pengguna": dict(pengguna),
    }


def _hari(awal: str | None, akhir: str | None) -> float | None:
    if not awal or not akhir:
        return None
    a = datetime.fromisoformat(awal.replace("Z", "+00:00"))
    b = datetime.fromisoformat(akhir.replace("Z", "+00:00"))
    return (b - a).total_seconds() / 86400


def ringkas_pengaduan(issue: list[dict]) -> dict:
    total = len(issue)
    ditanggapi = [i for i in issue if i.get("state") == "closed" or (i.get("comments") or 0) > 0]
    selesai = [_hari(i.get("created_at"), i.get("closed_at")) for i in issue if i.get("state") == "closed"]
    selesai = [x for x in selesai if x is not None]
    jenis = Counter(urai_formulir(i.get("body") or "").get("Jenis pengaduan") or "Tidak diisi" for i in issue)
    return {
        "total": total, "terbuka": sum(1 for i in issue if i.get("state") == "open"),
        "ditanggapi": len(ditanggapi),
        "ditanggapi_persen": round(len(ditanggapi) / total * 100, 1) if total else None,
        "median_hari_selesai": round(median(selesai), 1) if selesai else None,
        "per_jenis": dict(jenis),
        "terbaru": [{"judul": i.get("title"), "url": i.get("html_url"), "status": i.get("state"),
                     "dibuat": i.get("created_at")} for i in sorted(issue, key=lambda i: i.get("created_at") or "", reverse=True)[:10]],
    }


def kumpulkan(klien, hari_ini: date) -> dict:
    """Baca issue pengaduan & SKM. `klien` = KlienGitHub (atau tiruan untuk uji); None = tidak tersedia."""
    if klien is None:
        return {"catatan_ikm": "Hasil survei dibaca otomatis saat pipeline berjalan di GitHub Actions.",
                "catatan_pengaduan": "Pengaduan dibaca otomatis saat pipeline berjalan di GitHub Actions."}
    try:
        skm = klien.daftar_issue(LABEL_SKM)
        pengaduan = klien.daftar_issue(LABEL_PENGADUAN)
    except Exception as e:  # jaringan/izin: jangan gagalkan pipeline
        log.warning("gagal membaca issue layanan: %s", e)
        return {"catatan_ikm": f"Gagal membaca survei: {e}", "catatan_pengaduan": f"Gagal membaca pengaduan: {e}"}
    triwulan = (hari_ini.month - 1) // 3
    awal_tw = date(hari_ini.year, triwulan * 3 + 1, 1).isoformat()
    ikm = hitung_ikm(skm)
    ikm_tw = hitung_ikm([i for i in skm if (i.get("created_at") or "") >= awal_tw])
    p = ringkas_pengaduan(pengaduan)
    return {
        "ikm": ikm.get("ikm"), "skm": ikm, "skm_triwulan_berjalan": ikm_tw,
        "catatan_ikm": "" if ikm.get("ikm") is not None else "Belum ada responden survei kepuasan.",
        "pengaduan": p, "pengaduan_ditanggapi_persen": p["ditanggapi_persen"],
        "catatan_pengaduan": "" if p["total"] else "Belum ada pengaduan masuk.",
    }

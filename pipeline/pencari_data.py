"""AI Data Finder: agen penemuan sumber data (Claude + web search) dengan keluaran terstruktur.

Prinsip (Pedoman Pemahaman Proyek, bagian 9-10):
  - AI hanya MENCARI KANDIDAT sumber; hasil wajib diverifikasi manusia sebelum dipakai.
  - Dilarang mengarang data/URL. URL kandidat dicek silang dengan URL yang benar-benar muncul di hasil pencarian.
  - Hasil disimpan di data/sumber/kandidat_ai.json berstatus "kandidat".
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from .konfigurasi import Konfigurasi

log = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
MAKS_LANJUT = 5
MAKS_RIWAYAT = 50

SISTEM = """Anda adalah AI Data Finder untuk BPS Kabupaten Bengkulu Tengah (Provinsi Bengkulu, Indonesia) \
dalam proyek pemantauan harga pangan untuk TPID.

Tugas Anda: menemukan KANDIDAT sumber data yang relevan dan dapat diverifikasi. Anda tidak mengambil keputusan \
apakah sumber dipakai — analis BPS yang memverifikasi.

Aturan wajib:
- Gunakan web search untuk menemukan sumber. Cantumkan hanya URL yang benar-benar Anda temukan di hasil pencarian.
- Jangan mengarang nama sumber, URL, angka, periode, atau frekuensi. Jika suatu atribut tidak diketahui, isi "tidak diketahui".
- Utamakan sumber resmi/publik: BPS, Badan Pangan Nasional (Panel Harga), Bank Indonesia (PIHPS), Kementerian \
Perdagangan (SP2KP), Kementerian Pertanian, BMKG, dan situs/portal data Pemerintah Provinsi Bengkulu atau Kabupaten \
Bengkulu Tengah.
- Wilayah target adalah Kabupaten Bengkulu Tengah. Data Kabupaten Kepahiang dan Kota Bengkulu hanya relevan sebagai \
konteks rantai pasok/pembanding; tandai perannya dengan jelas.
- Nilai metode akses secara jujur: "api" hanya bila ada API terdokumentasi; "file" bila tersedia unduhan CSV/Excel/PDF; \
"web" bila hanya tampilan halaman. Tandai perlu_izin = true bila ketentuan penggunaan tidak jelas atau pengambilan \
otomatis mungkin tidak diizinkan.
- Jika tidak ada sumber yang memenuhi, kembalikan daftar kandidat kosong dan jelaskan di tidak_ditemukan."""

SKEMA = {
    "type": "object",
    "properties": {
        "kandidat": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "nama_sumber": {"type": "string"},
                    "penyedia": {"type": "string"},
                    "url": {"type": "string"},
                    "wilayah": {"type": "string"},
                    "peran_wilayah": {"type": "string", "enum": ["target", "pembanding", "provinsi", "nasional", "tidak diketahui"]},
                    "periode_data": {"type": "string"},
                    "komoditas_varian": {"type": "string"},
                    "satuan": {"type": "string"},
                    "frekuensi_pembaruan": {"type": "string"},
                    "metode_akses": {"type": "string", "enum": ["api", "file", "web", "lainnya", "tidak diketahui"]},
                    "lisensi_atau_ketentuan": {"type": "string"},
                    "perlu_izin": {"type": "boolean"},
                    "relevansi": {"type": "string"},
                    "catatan_keandalan": {"type": "string"},
                },
                "required": ["nama_sumber", "penyedia", "url", "wilayah", "peran_wilayah", "periode_data",
                             "komoditas_varian", "satuan", "frekuensi_pembaruan", "metode_akses",
                             "lisensi_atau_ketentuan", "perlu_izin", "relevansi", "catatan_keandalan"],
                "additionalProperties": False,
            },
        },
        "tidak_ditemukan": {"type": "array", "items": {"type": "string"}},
        "catatan": {"type": "string"},
    },
    "required": ["kandidat", "tidak_ditemukan", "catatan"],
    "additionalProperties": False,
}


def susun_permintaan(komoditas: str, periode: str, kebutuhan: str, wilayah: str) -> str:
    return (
        f"Cari sumber data {kebutuhan} untuk komoditas: {komoditas}, wilayah: {wilayah}, periode: {periode}. "
        "Untuk setiap sumber tampilkan: nama sumber, penyedia, URL, wilayah dan perannya, periode data, "
        "komoditas/varian, satuan, frekuensi pembaruan, metode akses (API/file/web), lisensi/ketentuan, "
        "apakah perlu izin, relevansi, dan catatan keandalan. Jangan mengarang data atau URL. "
        "Jika sumber tidak tersedia, nyatakan tidak tersedia."
    )


def _url_dari_pencarian(konten) -> list[str]:
    urls = []
    for blok in konten:
        if getattr(blok, "type", None) != "web_search_tool_result":
            continue
        isi = getattr(blok, "content", None)
        if isinstance(isi, list):  # sukses: daftar hasil; galat: objek tunggal
            urls.extend(getattr(r, "url", "") for r in isi if getattr(r, "url", ""))
    return urls


def _cocok(url: str, daftar: list[str]) -> bool:
    if not url:
        return False
    if url in daftar:
        return True
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return any(urlparse(u).netloc.lower().removeprefix("www.") == host for u in daftar)


def cari(konf: Konfigurasi, komoditas: str, periode: str, kebutuhan: str = "harga eceran harian",
         wilayah: str = "Kabupaten Bengkulu Tengah, Provinsi Bengkulu", klien=None) -> dict:
    import anthropic

    klien = klien or anthropic.Anthropic()
    teks = susun_permintaan(komoditas, periode, kebutuhan, wilayah)
    pesan = [{"role": "user", "content": teks}]
    semua_konten = []
    respons = None
    for _ in range(MAKS_LANJUT + 1):
        respons = klien.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SISTEM,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": 10}],
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": SKEMA}},
            messages=pesan,
        )
        semua_konten.extend(respons.content)
        if respons.stop_reason != "pause_turn":
            break
        pesan = [{"role": "user", "content": teks}, {"role": "assistant", "content": respons.content}]

    if respons.stop_reason == "refusal":
        detail = getattr(respons, "stop_details", None)
        raise RuntimeError(f"permintaan ditolak model: {getattr(detail, 'explanation', '') if detail else ''}")
    if respons.stop_reason == "max_tokens":
        raise RuntimeError("keluaran terpotong (max_tokens); persempit permintaan")

    teks_keluaran = [b.text for b in respons.content if getattr(b, "type", None) == "text"]
    if not teks_keluaran:
        raise RuntimeError("model tidak mengembalikan keluaran teks")
    try:
        hasil = json.loads(teks_keluaran[-1])
    except json.JSONDecodeError:
        hasil = json.loads("".join(teks_keluaran))

    url_cari = _url_dari_pencarian(semua_konten)
    for k in hasil.get("kandidat", []):
        k["url_ada_di_hasil_pencarian"] = _cocok(k.get("url", ""), url_cari)
        k["status_verifikasi"] = "kandidat"

    zona = ZoneInfo(konf.pengaturan.get("zona_waktu", "Asia/Jakarta"))
    return {
        "waktu": datetime.now(zona).isoformat(timespec="seconds"),
        "permintaan": {"komoditas": komoditas, "periode": periode, "kebutuhan": kebutuhan, "wilayah": wilayah, "prompt": teks},
        "model": getattr(respons, "model", MODEL),
        "request_id": getattr(respons, "_request_id", None),
        "hasil": hasil,
        "url_hasil_pencarian": sorted(set(url_cari)),
    }


def simpan(konf: Konfigurasi, catatan: dict) -> Path:
    path = konf.akar / "data" / "sumber" / "kandidat_ai.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"pencarian": []}
    data["pencarian"] = ([catatan] + data.get("pencarian", []))[:MAKS_RIWAYAT]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

"""AI Data Finder: agen penemuan kandidat sumber data dengan beberapa penyedia AI.

Penyedia (pengaturan.json -> ai.penyedia):
  gemini        : Google Gemini API (kuota gratis) + Google Search grounding. Butuh GEMINI_API_KEY.
  groq          : Groq (kuota gratis, sangat cepat). Butuh GROQ_API_KEY. TANPA pencarian web.
  cerebras      : Cerebras (kuota gratis harian besar). Butuh CEREBRAS_API_KEY. TANPA pencarian web.
  openrouter    : OpenRouter, model gratis (":free" atau router openrouter/free). Butuh OPENROUTER_API_KEY. TANPA pencarian web.
  mistral       : Mistral (paket Experiment gratis). Butuh MISTRAL_API_KEY. TANPA pencarian web.
  github_models : GitHub Models (gratis, memakai GITHUB_TOKEN di Actions). TANPA pencarian web.
  anthropic     : Claude + web search (berbayar, opsional). Butuh ANTHROPIC_API_KEY.
  otomatis      : coba penyedia sesuai urutan ai.urutan_otomatis, lalu penyedia gratis lain yang belum disebut.
                  Lanjut ke berikutnya bila kunci belum diisi, kuota habis, atau jawabannya rusak.

Prinsip (Pedoman Pemahaman Proyek, bagian 9-10):
  - AI hanya MENCARI KANDIDAT sumber; hasil wajib diverifikasi manusia sebelum dipakai.
  - Dilarang mengarang data/URL. Setiap URL kandidat dicek: (1) apakah domainnya muncul di hasil pencarian
    (bila penyedia punya pencarian) dan (2) apakah benar-benar dapat dibuka.
  - Hasil disimpan di data/sumber/kandidat_ai.json berstatus "kandidat".
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import datetime
from functools import partial
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from .konfigurasi import Konfigurasi

log = logging.getLogger(__name__)

MAKS_LANJUT = 5
MAKS_RIWAYAT = 50
URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
URL_GITHUB_MODELS = "https://models.github.ai/inference/chat/completions"
# Penyedia dengan antarmuka chat completions ala OpenAI. Semuanya punya kuota gratis, tetapi tanpa pencarian web.
SEJENIS_OPENAI = {
    "groq": {"nama": "Groq", "url": "https://api.groq.com/openai/v1/chat/completions", "kunci": "GROQ_API_KEY",
             "model": "model_groq"},
    "cerebras": {"nama": "Cerebras", "url": "https://api.cerebras.ai/v1/chat/completions", "kunci": "CEREBRAS_API_KEY",
                 "model": "model_cerebras"},
    "openrouter": {"nama": "OpenRouter", "url": "https://openrouter.ai/api/v1/chat/completions",
                   "kunci": "OPENROUTER_API_KEY", "model": "model_openrouter"},
    "mistral": {"nama": "Mistral", "url": "https://api.mistral.ai/v1/chat/completions", "kunci": "MISTRAL_API_KEY",
                "model": "model_mistral"},
    "github_models": {"nama": "GitHub Models", "url": URL_GITHUB_MODELS, "kunci": "GITHUB_TOKEN", "model": "model_github",
                      "header": {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
                      "tanpa_kunci": "GITHUB_TOKEN tidak tersedia (jalankan dari GitHub Actions dengan izin models: read)"},
}
# Penyedia gratis. Pada mode otomatis, yang tidak disebut di ai.urutan_otomatis tetap dicoba paling akhir sebagai cadangan.
GRATIS = ["gemini", "groq", "cerebras", "openrouter", "mistral", "github_models"]
BAWAAN = {
    "penyedia": "otomatis",
    "urutan_otomatis": list(GRATIS),
    "model_gemini": "gemini-flash-latest",
    "model_groq": "openai/gpt-oss-120b",
    "model_cerebras": "gpt-oss-120b",
    "model_openrouter": "openrouter/free",
    "model_mistral": "mistral-small-latest",
    "model_github": "openai/gpt-4.1-mini",
    "model_anthropic": "claude-opus-5-5",
}
ARTI_KODE = {400: "permintaan ditolak", 401: "kunci ditolak", 402: "saldo atau kuota habis", 403: "akses ditolak",
             404: "model tidak ditemukan", 413: "permintaan terlalu besar", 429: "batas pemakaian gratis tercapai"}

KOLOM_KANDIDAT = ["nama_sumber", "penyedia", "url", "wilayah", "peran_wilayah", "periode_data", "komoditas_varian",
                  "satuan", "frekuensi_pembaruan", "metode_akses", "lisensi_atau_ketentuan", "perlu_izin",
                  "relevansi", "catatan_keandalan"]

SISTEM = """Anda adalah AI Data Finder untuk BPS Kabupaten Bengkulu Tengah (Provinsi Bengkulu, Indonesia) \
dalam proyek pemantauan harga pangan untuk TPID.

Tugas Anda: menemukan KANDIDAT sumber data yang relevan dan dapat diverifikasi. Anda tidak mengambil keputusan \
apakah sumber dipakai; analis BPS yang memverifikasi.

Aturan wajib:
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

TAMBAHAN_PENCARIAN = "\n- Gunakan pencarian web. Cantumkan hanya URL yang benar-benar Anda temukan di hasil pencarian."
TAMBAHAN_TANPA_PENCARIAN = """
- Anda TIDAK memiliki akses internet. Sebutkan hanya lembaga/portal resmi yang Anda yakini ada, gunakan URL halaman \
utama portal (bukan halaman spesifik yang mungkin tidak ada), dan tulis di catatan_keandalan bahwa URL perlu dicek \
manual. Lebih baik sedikit kandidat yang pasti daripada banyak yang meragukan."""

FORMAT_JSON = """

Balas HANYA dengan satu objek JSON (tanpa teks lain) berbentuk:
{"kandidat": [{"nama_sumber": "", "penyedia": "", "url": "", "wilayah": "",
  "peran_wilayah": "target|pembanding|provinsi|nasional|tidak diketahui", "periode_data": "", "komoditas_varian": "",
  "satuan": "", "frekuensi_pembaruan": "", "metode_akses": "api|file|web|lainnya|tidak diketahui",
  "lisensi_atau_ketentuan": "", "perlu_izin": true, "relevansi": "", "catatan_keandalan": ""}],
 "tidak_ditemukan": [""], "catatan": ""}"""

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
                "required": KOLOM_KANDIDAT,
                "additionalProperties": False,
            },
        },
        "tidak_ditemukan": {"type": "array", "items": {"type": "string"}},
        "catatan": {"type": "string"},
    },
    "required": ["kandidat", "tidak_ditemukan", "catatan"],
    "additionalProperties": False,
}


class PenyediaTidakTersedia(RuntimeError):
    """Penyedia tidak dapat dipakai (kunci belum diatur, kuota habis, layanan galat)."""


def susun_permintaan(komoditas: str, periode: str, kebutuhan: str, wilayah: str) -> str:
    return (
        f"Cari sumber data {kebutuhan} untuk komoditas: {komoditas}, wilayah: {wilayah}, periode: {periode}. "
        "Untuk setiap sumber tampilkan: nama sumber, penyedia, URL, wilayah dan perannya, periode data, "
        "komoditas/varian, satuan, frekuensi pembaruan, metode akses (API/file/web), lisensi/ketentuan, "
        "apakah perlu izin, relevansi, dan catatan keandalan. Jangan mengarang data atau URL. "
        "Jika sumber tidak tersedia, nyatakan tidak tersedia."
    )


def pengaturan_ai(konf: Konfigurasi) -> dict:
    return {**BAWAAN, **konf.pengaturan.get("ai", {})}


def urutan_penyedia(konf: Konfigurasi, pilihan: str | None = None) -> list[str]:
    cfg = pengaturan_ai(konf)
    pilihan = (pilihan or cfg["penyedia"]).lower()
    if pilihan == "otomatis":
        # Urutan pilihan admin dulu, lalu semua AI gratis lain sebagai cadangan supaya batas kuota satu AI tidak
        # menggagalkan pencarian.
        return list(dict.fromkeys([p for p in cfg["urutan_otomatis"] if p in PENYEDIA] + GRATIS))
    if pilihan not in PENYEDIA:
        raise ValueError(f"penyedia AI tidak dikenal: {pilihan}")
    return [pilihan]


# ---------------------------------------------------------------- utilitas

def _post_json(url: str, header: dict, isi: dict, batas_waktu: int = 180) -> dict:
    req = urllib.request.Request(url, method="POST", data=json.dumps(isi).encode(),
                                 headers={"Content-Type": "application/json", **header})
    # Semua kegagalan dianggap "penyedia tidak tersedia" supaya mode otomatis lanjut ke AI berikutnya. Gemini misalnya
    # menjawab HTTP 400 untuk kunci yang salah.
    try:
        with urllib.request.urlopen(req, timeout=batas_waktu) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        badan = " ".join(e.read().decode(errors="replace").split())[:300]
        arti = ARTI_KODE.get(e.code) or ("layanan sedang bermasalah" if e.code >= 500 else "")
        raise PenyediaTidakTersedia(f"HTTP {e.code}{f' ({arti})' if arti else ''}: {badan}") from e
    except urllib.error.URLError as e:
        raise PenyediaTidakTersedia(f"jaringan: {e.reason}") from e
    except OSError as e:  # batas waktu habis saat membaca jawaban
        raise PenyediaTidakTersedia(f"jaringan: {e.__class__.__name__}") from e
    except ValueError as e:
        raise PenyediaTidakTersedia("jawaban layanan bukan JSON") from e


def ambil_json_dari_teks(teks: str) -> dict:
    """Ambil objek JSON dari keluaran model (boleh dibungkus ```json ... ``` atau diberi teks pengantar)."""
    teks = teks.strip()
    pagar = re.search(r"```(?:json)?\s*(\{.*\})\s*```", teks, re.S)
    if pagar:
        teks = pagar.group(1)
    else:
        awal, akhir = teks.find("{"), teks.rfind("}")
        if awal < 0 or akhir <= awal:
            raise RuntimeError("model tidak mengembalikan JSON")
        teks = teks[awal:akhir + 1]
    try:
        return json.loads(teks)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON dari model tidak valid: {e}") from e


def normalisasi_hasil(hasil: dict) -> dict:
    """Pastikan struktur hasil sesuai skema walau model tidak mendukung keluaran terstruktur."""
    kandidat = []
    for k in hasil.get("kandidat") or []:
        if not isinstance(k, dict):
            continue
        baru = {kol: k.get(kol, "tidak diketahui") for kol in KOLOM_KANDIDAT}
        baru["perlu_izin"] = bool(k.get("perlu_izin", True))
        baru = {kol: (str(v) if kol != "perlu_izin" and v is not None else v) for kol, v in baru.items()}
        if baru["nama_sumber"] and baru["nama_sumber"] != "tidak diketahui":
            kandidat.append(baru)
    tidak = hasil.get("tidak_ditemukan") or []
    return {"kandidat": kandidat, "tidak_ditemukan": [str(x) for x in tidak] if isinstance(tidak, list) else [str(tidak)],
            "catatan": str(hasil.get("catatan") or "")}


def _host(url: str) -> str:
    return urlparse(url if "://" in url else f"https://{url}").netloc.lower().removeprefix("www.")


def _cocok(url: str, daftar: list[str]) -> bool:
    """URL cocok bila persis sama, atau host-nya sama/subdomain dari host yang muncul di hasil pencarian."""
    if not url:
        return False
    if url in daftar:
        return True
    host = _host(url)
    for u in daftar:
        h = _host(u)
        if h and (host == h or host.endswith("." + h) or h.endswith("." + host)):
            return True
    return False


def cek_url(url: str, batas_waktu: int = 15) -> tuple[bool | None, str]:
    """Apakah URL dapat dibuka. Kembalikan (status, keterangan); None bila tidak dapat dipastikan."""
    if not url or not url.startswith(("http://", "https://")):
        return False, "URL tidak valid"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (pemantauan-harga-benteng)", "Range": "bytes=0-2048"})
    try:
        with urllib.request.urlopen(req, timeout=batas_waktu) as r:
            return True, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 405, 406, 429):  # situs ada tetapi menolak robot
            return None, f"HTTP {e.code} (situs menolak akses otomatis)"
        return False, f"HTTP {e.code}"
    except Exception as e:  # DNS, TLS, timeout
        return False, f"tidak dapat dibuka: {e.__class__.__name__}"


# ---------------------------------------------------------------- penyedia

def _cari_gemini(teks: str, cfg: dict, klien=None) -> dict:
    kunci = os.environ.get("GEMINI_API_KEY")
    if not kunci and klien is None:
        raise PenyediaTidakTersedia("kunci GEMINI_API_KEY belum diisi")
    kirim = klien or _post_json
    model = cfg["model_gemini"]
    data = kirim(
        URL_GEMINI.format(model=model),
        {"x-goog-api-key": kunci or ""},
        {
            "system_instruction": {"parts": [{"text": SISTEM + TAMBAHAN_PENCARIAN}]},
            "contents": [{"role": "user", "parts": [{"text": teks + FORMAT_JSON}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0.2},
        },
    )
    if data.get("promptFeedback", {}).get("blockReason"):
        raise RuntimeError(f"permintaan diblokir Gemini: {data['promptFeedback']['blockReason']}")
    kandidat = data.get("candidates") or []
    if not kandidat:
        raise PenyediaTidakTersedia("Gemini tidak mengembalikan jawaban")
    c = kandidat[0]
    keluaran = "".join(p.get("text", "") for p in (c.get("content") or {}).get("parts", []))
    rujukan = []
    for ch in (c.get("groundingMetadata") or {}).get("groundingChunks", []):
        web = ch.get("web") or {}
        # uri Gemini berupa tautan pengalih; title berisi domain sumber asli
        rujukan += [x for x in (web.get("title"), web.get("uri")) if x]
    return {"hasil": ambil_json_dari_teks(keluaran), "url_pencarian": rujukan, "punya_pencarian": True,
            "model": data.get("modelVersion") or model, "request_id": data.get("responseId")}


def _teks_pesan(isi) -> str:
    """Isi pesan bisa berupa teks biasa atau daftar potongan (Mistral dan sebagian model di OpenRouter)."""
    if isinstance(isi, str):
        return isi
    if isinstance(isi, list):
        return "".join(p.get("text") or "" for p in isi if isinstance(p, dict) and p.get("type", "text") == "text")
    return ""


def _cari_sejenis_openai(nama: str, teks: str, cfg: dict, klien=None) -> dict:
    p = SEJENIS_OPENAI[nama]
    kunci = os.environ.get(p["kunci"])
    if not kunci and klien is None:
        raise PenyediaTidakTersedia(p.get("tanpa_kunci") or f"kunci {p['kunci']} belum diisi")
    kirim = klien or _post_json
    model = cfg[p["model"]]
    data = kirim(
        p["url"],
        {"Authorization": f"Bearer {kunci or ''}", **p.get("header", {})},
        {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": SISTEM + TAMBAHAN_TANPA_PENCARIAN},
                {"role": "user", "content": teks + FORMAT_JSON},
            ],
        },
    )
    if data.get("error"):  # OpenRouter kadang menjawab HTTP 200 berisi galat dari penyedia di belakangnya
        galat = data["error"]
        raise PenyediaTidakTersedia(f"{p['nama']}: {galat.get('message') if isinstance(galat, dict) else galat}"[:300])
    pilihan = data.get("choices") or []
    keluaran = _teks_pesan((pilihan[0].get("message") or {}).get("content")) if pilihan else ""
    if not keluaran.strip():
        raise PenyediaTidakTersedia(f"{p['nama']} tidak mengembalikan jawaban")
    return {"hasil": ambil_json_dari_teks(keluaran), "url_pencarian": [], "punya_pencarian": False,
            "model": data.get("model") or model, "request_id": data.get("id")}


def _url_dari_pencarian_claude(konten) -> list[str]:
    urls = []
    for blok in konten:
        if getattr(blok, "type", None) != "web_search_tool_result":
            continue
        isi = getattr(blok, "content", None)
        if isinstance(isi, list):  # sukses: daftar hasil; galat: objek tunggal
            urls.extend(getattr(r, "url", "") for r in isi if getattr(r, "url", ""))
    return urls


def _cari_anthropic(teks: str, cfg: dict, klien=None) -> dict:
    if klien is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise PenyediaTidakTersedia("kunci ANTHROPIC_API_KEY belum diisi")
        import anthropic  # hanya dibutuhkan bila memilih penyedia berbayar ini (requirements-ai.txt)

        klien = anthropic.Anthropic()
    pesan = [{"role": "user", "content": teks}]
    semua_konten = []
    respons = None
    for _ in range(MAKS_LANJUT + 1):
        respons = klien.beta.messages.create(
            model=cfg["model_anthropic"],
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=SISTEM + TAMBAHAN_PENCARIAN,
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
        hasil = ambil_json_dari_teks("".join(teks_keluaran))
    return {"hasil": hasil, "url_pencarian": _url_dari_pencarian_claude(semua_konten), "punya_pencarian": True,
            "model": getattr(respons, "model", cfg["model_anthropic"]), "request_id": getattr(respons, "_request_id", None)}


PENYEDIA = {"gemini": _cari_gemini, **{n: partial(_cari_sejenis_openai, n) for n in SEJENIS_OPENAI}, "anthropic": _cari_anthropic}


def cari(konf: Konfigurasi, komoditas: str, periode: str, kebutuhan: str = "harga eceran harian",
         wilayah: str = "Kabupaten Bengkulu Tengah, Provinsi Bengkulu", penyedia: str | None = None,
         klien: dict | None = None, pemeriksa_url=cek_url) -> dict:
    """Jalankan pencarian. `klien` (untuk uji) memetakan nama penyedia -> pengganti fungsi kirim/klien SDK."""
    cfg = pengaturan_ai(konf)
    teks = susun_permintaan(komoditas, periode, kebutuhan, wilayah)
    klien = klien or {}
    galat: list[str] = []
    jawab = dipakai = None
    for nama in urutan_penyedia(konf, penyedia):
        try:
            jawab = PENYEDIA[nama](teks, cfg, klien.get(nama))
            dipakai = nama
            break
        except Exception as e:  # noqa: BLE001 - kuota habis, kunci salah, jawaban rusak: coba AI berikutnya
            pesan = str(e) if isinstance(e, RuntimeError) else f"{e.__class__.__name__}: {e}"
            log.warning("penyedia %s dilewati: %s", nama, pesan)
            galat.append(f"{nama}: {pesan}"[:400])
    if jawab is None:
        raise RuntimeError("tidak ada penyedia AI yang dapat dipakai: " + "; ".join(galat))

    hasil = normalisasi_hasil(jawab["hasil"])
    for k in hasil["kandidat"]:
        k["url_ada_di_hasil_pencarian"] = _cocok(k["url"], jawab["url_pencarian"]) if jawab["punya_pencarian"] else None
        k["url_dapat_diakses"], k["keterangan_url"] = pemeriksa_url(k["url"]) if pemeriksa_url else (None, "tidak dicek")
        k["status_verifikasi"] = "kandidat"

    zona = ZoneInfo(konf.pengaturan.get("zona_waktu", "Asia/Jakarta"))
    return {
        "waktu": datetime.now(zona).isoformat(timespec="seconds"),
        "permintaan": {"komoditas": komoditas, "periode": periode, "kebutuhan": kebutuhan, "wilayah": wilayah, "prompt": teks},
        "penyedia": dipakai,
        "punya_pencarian_web": jawab["punya_pencarian"],
        "penyedia_dilewati": galat,
        "model": jawab["model"],
        "request_id": jawab["request_id"],
        "hasil": hasil,
        "url_hasil_pencarian": sorted(set(jawab["url_pencarian"])),
    }


def simpan(konf: Konfigurasi, catatan: dict) -> Path:
    path = konf.akar / "data" / "sumber" / "kandidat_ai.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"pencarian": []}
    data["pencarian"] = ([catatan] + data.get("pencarian", []))[:MAKS_RIWAYAT]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path

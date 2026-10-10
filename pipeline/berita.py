"""Berita lokal harian: cari, baca, ambil harga dari isinya, dan simpulkan.

Alur satu kali jalan (otomatis sekali sehari, lihat firestore_sinkron.berita_jatuh_tempo):
  1. Temukan berita terbaru: pencarian berita Tavily (hasilnya sudah memuat isi artikel), umpan RSS Google Berita
     per kueri, dan umpan RSS portal yang diisi admin.
  2. Buang duplikat, berita yang terlalu lama, dan yang tidak menyebut wilayah Bengkulu beserta topik pangan.
  3. Baca isi halaman yang belum punya isi. Setiap halaman dicek robots.txt dulu, diberi jeda, dan dibatasi ukurannya.
  4. Nilai relevansi, tandai kejadian (harga naik, pasokan terganggu, cuaca ekstrem, intervensi), dan ambil harga dari
     kalimat berita dengan aturan biasa. Angka harga selalu disertai kalimat bukti dan dicek terhadap batas wajar
     tiap varian. Hasilnya KANDIDAT yang wajib diverifikasi analis, tidak pernah masuk deret harga resmi.
  5. Ringkas dengan AI gratis (rotasi penyedia yang sama dengan AI Data Finder). Angka di ringkasan dicek terhadap isi
     berita, dan bila AI tidak tersedia dipakai ringkasan ekstraktif. Terakhir disusun kesimpulan harian.

Yang disimpan hanya tautan, judul, ringkasan, kutipan pendek, kalimat bukti harga, dan sidik SHA-256 isi artikel.
Isi lengkap artikel tidak disimpan karena hak ciptanya milik penerbit. Hasil ada di data/berita/berita.json.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

from . import pencari_data
from .konfigurasi import Konfigurasi

log = logging.getLogger(__name__)

WIB = ZoneInfo("Asia/Jakarta")
TOKEN_ROBOTS = "LintasBentengBot"
UA_BOT = (f"{TOKEN_ROBOTS}/1.0 (pemantauan harga pangan BPS Kabupaten Bengkulu Tengah; "
          "+https://lintas-benteng-projection.web.app/tentang.html)")
MAKS_BYTE_HALAMAN = 2 * 1024 * 1024
MAKS_BYTE_ROBOTS = 200 * 1024
MAKS_TEKS = 30_000
MIN_TEKS_TERBACA = 200
AWAL_TEKS = 1500
MAKS_ARSIP = 300
MAKS_KESIMPULAN = 30
MAKS_HARGA_PER_BERITA = 12
UKURAN_GELOMBANG_AI = 6
POTONG_TEKS_AI = 1500
URL_GOOGLE_BERITA = "https://news.google.com/rss/search?q={q}&hl=id&gl=ID&ceid=ID:id"

BAWAAN = {
    "aktif": True,
    "jam_mulai": 7,
    "umur_maks_hari": 14,
    "simpan_hari": 60,
    "maks_berita": 40,
    "maks_diringkas": 12,
    "pakai_ai": True,
    "hormati_robots": True,
    "jeda_detik": 2.0,
    "maks_menit": 8,  # batas waktu mengunduh halaman supaya pembaruan harian tidak tertahan
    "kueri": [
        "harga pangan Bengkulu Tengah",
        "harga cabai bawang Bengkulu",
        "harga beras telur daging ayam Bengkulu",
        "harga minyak goreng gula pasir Bengkulu",
        "operasi pasar pasar murah TPID Bengkulu Tengah",
        "banjir gagal panen distribusi pangan Bengkulu",
    ],
    # Kueri tambahan hanya dicari lewat Google Berita (gratis, tidak memakai kredit Tavily): komoditas di luar 21 varian, nama pasar,
    # dan pencarian per portal berita Bengkulu (operator site: milik Google Berita, jadi tidak perlu menebak alamat RSS tiap portal).
    "kueri_tambahan": [
        "harga LPG 3 kg Bengkulu Tengah",
        "harga susu kental manis garam Bengkulu",
        "harga pasar Taba Penanjung",
        "harga pasar Karang Tinggi Bengkulu Tengah",
        "harga sembako Lebaran Bengkulu Tengah",
        "harga bahan pokok site:bengkulu.antaranews.com",
        "harga pangan site:bengkulu.tribunnews.com",
        "harga pangan site:radarbengkulu.bacakoran.co",
        "harga pangan site:rakyatbengkulu.bacakoran.co",
        "harga pangan site:bengkuluekspress.disway.id",
        "harga pangan site:bengkulutengahkab.go.id",
    ],
    "umpan_rss": [],  # [{"nama": "...", "url": "https://.../rss.xml", "aktif": true}]
    "domain_diabaikan": ["facebook.com", "instagram.com", "tiktok.com", "youtube.com", "youtu.be", "x.com", "twitter.com"],
}

# ---------------------------------------------------------------- kata kunci

TAG = {
    "harga_naik": ("Harga naik", r"\b(naik|menaik|melonjak|meroket|merangkak|mahal|kenaikan|melambung|tembus)\b"),
    "harga_turun": ("Harga turun", r"\b(turun|menurun|anjlok|murah|penurunan|merosot|melandai)\b"),
    "pasokan": ("Pasokan terganggu", r"\b(langka|kelangkaan|stok menipis|stok terbatas|pasokan (?:berkurang|terbatas|terganggu|seret)|"
                r"distribusi terganggu|kekurangan stok|kosong)\b"),
    "cuaca": ("Cuaca atau bencana", r"\b(banjir|longsor|kemarau|kekeringan|hujan deras|gagal panen|puting beliung|cuaca ekstrem|"
                                    r"bencana|gelombang tinggi)\b"),
    "intervensi": ("Intervensi pemerintah", r"\b(operasi pasar|pasar murah|tpid|subsidi|bantuan pangan|cadangan pangan|gerakan pangan murah|"
                                            r"inflasi daerah|rakor)\b"),
}
KATA_HARGA = re.compile(r"\b(harga|inflasi|pasar|pangan|sembako|bapok|kebutuhan pokok|komoditas|stok|pasokan)\b", re.I)
SINONIM_KOMODITAS = {
    "BRS": ["beras"],
    "DAY": ["daging ayam", "ayam ras", "ayam potong", "ayam broiler"],
    "TLR": ["telur ayam", "telur ayam ras", "telur"],
    "DSP": ["daging sapi"],
    "BWM": ["bawang merah"],
    "BWP": ["bawang putih"],
    "CMR": ["cabai merah", "cabai keriting", "cabai"],
    "CRW": ["cabai rawit"],
    "MGR": ["minyak goreng", "migor", "minyakita"],
    "GLP": ["gula pasir", "gula"],
    "IKN": ["ikan"],
}
SINONIM_VARIAN = {
    "cabai merah keriting": "CMR02", "cabai keriting": "CMR02", "cabai merah besar": "CMR01",
    "cabai rawit merah": "CRW02", "cabai rawit hijau": "CRW01", "minyak goreng curah": "MGR01",
    "gula pasir lokal": "GLP01", "gula pasir premium": "GLP02", "ikan kembung": "IKN01", "ikan tongkol": "IKN02",
}
SATUAN_SAH = {"kg": "kg", "kilo": "kg", "kilogram": "kg", "liter": "liter", "ltr": "liter", "l": "liter"}
SATUAN_LAIN = {"butir", "ikat", "biji", "bungkus", "sak", "karung", "pak", "ekor", "buah", "pcs", "kaleng", "botol", "tabung", "karpet"}
# Bahan pokok yang disebut di laporan tetapi tidak termasuk 21 varian: harganya per tabung, kaleng, atau bungkus. Hanya menjadi kandidat berita.
KOMODITAS_TAMBAHAN = {
    "LPG": {"nama": "Gas LPG 3 kg", "alias": ["lpg 3 kg", "gas lpg 3 kg", "gas elpiji 3 kg", "elpiji 3 kg", "gas melon", "gas lpg", "gas elpiji", "elpiji", "lpg"],
            "satuan": {"tabung"}, "batas": (15_000, 60_000)},
    "SKM": {"nama": "Susu Kental Manis", "alias": ["susu kental manis", "kental manis"], "satuan": {"kaleng"}, "batas": (7_000, 25_000)},
    "GRM": {"nama": "Garam Beryodium", "alias": ["garam beryodium", "garam"], "satuan": {"bungkus", "pak"}, "batas": (1_500, 10_000)},
}
BATAS_TELUR_KARPET = (35_000, 100_000)  # telur ayam ras dijual per karpet (30 butir); bukan harga per kg, jadi tidak dibanding dengan data utama
PERUBAHAN = re.compile(r"(naik|turun|kenaikan|penurunan|selisih|bertambah|berkurang)\s+(sebesar|senilai)\s*$", re.I)
RE_HARGA = re.compile(
    r"Rp\.?\s?(?:(?P<titik>\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?|(?P<desimal>\d+(?:,\d{1,2})?)\s*(?P<skala>ribu|rb|juta)\b|(?P<polos>\d+))",
    re.I,
)
RE_SATUAN = re.compile(r"^\s*(?:/|per\s+|setiap\s+)\s*(?P<s>[a-z]+)", re.I)
RE_RENTANG = re.compile(r"^\s*(?:-|\u2013|hingga|sampai(?:\s+dengan)?|s\.?d\.?)\s*(?=Rp)", re.I)


def _bersih(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _norm(s: str) -> str:
    return _bersih(s).lower().replace("cabe", "cabai")


def pengaturan_berita(konf: Konfigurasi) -> dict:
    return {**BAWAAN, **(konf.pengaturan.get("berita") or {})}


# ---------------------------------------------------------------- pengambilan halaman

def ambil_http(url: str, batas_waktu: int = 20, maks_byte: int = MAKS_BYTE_HALAMAN) -> tuple[str, bytes, str]:
    """GET sederhana. Mengembalikan (url akhir setelah pengalihan, isi, jenis isi). Galat HTTP dilempar apa adanya."""
    req = urllib.request.Request(url, headers={"User-Agent": UA_BOT, "Accept": "text/html,application/xhtml+xml,application/xml,"
                                               "application/rss+xml;q=0.9,*/*;q=0.5", "Accept-Language": "id,en;q=0.5",
                                               "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=batas_waktu) as r:
        isi = r.read(maks_byte + 1)
        return r.geturl(), isi[:maks_byte], r.headers.get("Content-Type", "")


class Robots:
    """Pemeriksa robots.txt per situs (aturan RFC 9309): 200 diikuti, 4xx berarti boleh, 5xx atau jaringan putus berarti dilarang."""

    def __init__(self, ambil=ambil_http, aktif: bool = True):
        self.ambil = ambil
        self.aktif = aktif
        self.cache: dict[str, urllib.robotparser.RobotFileParser | bool] = {}

    def boleh(self, url: str) -> bool:
        if not self.aktif:
            return True
        u = urllib.parse.urlparse(url)
        asal = f"{u.scheme}://{u.netloc}"
        if asal not in self.cache:
            self.cache[asal] = self._muat(asal)
        aturan = self.cache[asal]
        if isinstance(aturan, bool):
            return aturan
        return aturan.can_fetch(TOKEN_ROBOTS, url)

    def _muat(self, asal: str):
        try:
            _, isi, _ = self.ambil(f"{asal}/robots.txt", 10, MAKS_BYTE_ROBOTS)
        except urllib.error.HTTPError as e:
            return e.code < 500  # 4xx: tidak ada aturan, 5xx: anggap dilarang
        except Exception:  # noqa: BLE001 - jaringan putus
            return False
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(isi.decode("utf-8", "replace").splitlines())
        return rp


# ---------------------------------------------------------------- tanggal dan URL

def parse_tanggal(teks) -> date | None:
    """Tanggal (WIB) dari RFC 822, ISO 8601, atau teks yang memuat yyyy-mm-dd. None bila tidak terbaca."""
    if not teks:
        return None
    teks = str(teks).strip()
    try:
        d = parsedate_to_datetime(teks)
        return (d.astimezone(WIB) if d.tzinfo else d).date()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        d = datetime.fromisoformat(teks.replace("Z", "+00:00"))
        return (d.astimezone(WIB) if d.tzinfo else d).date()
    except ValueError:
        pass
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", teks)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


PARAMETER_PELACAK = ("utm_", "fbclid", "gclid", "ref", "source", "campaign", "amp", "oc")


def kanonik(url: str) -> str:
    """URL tanpa pelacak, fragmen, dan garis miring penutup, supaya satu berita tidak terhitung dua kali."""
    u = urllib.parse.urlparse(url.strip())
    host = u.netloc.lower().removeprefix("www.")
    if host == "news.google.com":
        return f"{u.scheme}://{host}{u.path}"
    query = [(k, v) for k, v in urllib.parse.parse_qsl(u.query) if not k.lower().startswith(PARAMETER_PELACAK)]
    path = u.path.rstrip("/") or "/"
    return urllib.parse.urlunparse((u.scheme or "https", host, path, "", urllib.parse.urlencode(query), ""))


def host_dari(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def id_berita(url: str) -> str:
    return hashlib.sha1(kanonik(url).encode()).hexdigest()[:12]


def _kunci_judul(judul: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _norm(judul))[:70]


# ---------------------------------------------------------------- penemuan

def url_google_berita(kueri: str, umur: int) -> str:
    return URL_GOOGLE_BERITA.format(q=urllib.parse.quote_plus(f"{kueri} when:{max(1, umur)}d"))


def baca_rss(isi: bytes, sumber_umpan: str = "") -> list[dict]:
    """Baca RSS 2.0 atau Atom. Berkas dengan DOCTYPE/ENTITY ditolak untuk mencegah serangan XML."""
    kepala = isi[:4000].lower()
    if b"<!doctype" in kepala or b"<!entity" in kepala:
        raise ValueError("umpan ditolak: memuat DOCTYPE atau ENTITY")
    akar = ET.fromstring(isi)
    hasil = []
    for it in akar.iter():
        nama = it.tag.rsplit("}", 1)[-1]
        if nama not in ("item", "entry"):
            continue
        anak = {c.tag.rsplit("}", 1)[-1]: c for c in it}
        judul = _bersih("".join(anak["title"].itertext())) if "title" in anak else ""
        tautan = ""
        if "link" in anak:
            tautan = (anak["link"].get("href") or "".join(anak["link"].itertext())).strip()
        tgl = next((anak[k].text for k in ("pubDate", "published", "updated", "date") if k in anak and anak[k].text), "")
        sumber = _bersih(anak["source"].text or "") if "source" in anak else ""
        desk = ""
        for k in ("description", "summary", "content"):
            if k in anak:
                desk = _bersih(re.sub(r"<[^>]+>", " ", "".join(anak[k].itertext())))
                break
        if sumber and judul.endswith(f" - {sumber}"):
            judul = judul[: -len(sumber) - 3].strip()
        elif not sumber and " - " in judul and sumber_umpan.startswith("google"):
            judul, _, sumber = judul.rpartition(" - ")
        if desk and desk.startswith(judul[:40]):
            desk = ""  # Google Berita mengulang judul dan nama media di deskripsi
        if judul and tautan.startswith("http"):
            hasil.append({"judul": judul[:300], "url": tautan, "sumber": sumber, "tanggal": parse_tanggal(tgl),
                          "cuplikan": desk[:500], "teks": "", "via": sumber_umpan})
    return hasil


def cari_tavily(kueri: list[str], umur: int, kirim=None) -> tuple[list[dict], list[str]]:
    """Pencarian berita Tavily (topik news). Hasilnya memuat isi artikel, jadi tidak perlu mengunduh halamannya."""
    kunci = os.environ.get("TAVILY_API_KEY")
    if not kunci and kirim is None:
        return [], ["Tavily dilewati: kunci belum diisi."]
    kirim = kirim or pencari_data._post_json
    hasil, galat = [], []
    for q in kueri:
        isi = {"query": q, "topic": "news", "days": max(1, umur), "search_depth": "basic", "max_results": 6,
               "include_answer": False, "include_raw_content": True}
        try:
            data = kirim(pencari_data.URL_TAVILY, {"Authorization": f"Bearer {kunci or ''}"}, isi)
        except Exception as e:  # noqa: BLE001 - kuota habis atau gangguan
            galat.append(f"Tavily '{q}': {e}"[:300])
            if any(k in str(e) for k in ("401", "432", "433")):
                break
            continue
        for r in data.get("results") or []:
            url = str(r.get("url") or "").strip()
            if not url.startswith("http"):
                continue
            teks = str(r.get("raw_content") or "")
            hasil.append({"judul": _bersih(str(r.get("title") or ""))[:300], "url": url, "sumber": host_dari(url),
                          "tanggal": parse_tanggal(r.get("published_date")), "cuplikan": _bersih(str(r.get("content") or ""))[:500],
                          "teks": teks[:MAKS_TEKS], "via": "tavily"})
    return hasil, galat


def temukan(cfg: dict, umur: int, ambil=ambil_http, kirim_tavily=None) -> tuple[list[dict], list[str]]:
    kandidat, galat = [], []
    h, g = cari_tavily(cfg["kueri"], umur, kirim_tavily)
    kandidat += h
    galat += g
    semua_kueri = list(dict.fromkeys([*cfg["kueri"], *cfg.get("kueri_tambahan", [])]))
    umpan = [{"nama": f"Google Berita: {q}", "url": url_google_berita(q, umur), "via": "google_berita"} for q in semua_kueri]
    umpan += [{"nama": u.get("nama") or u["url"], "url": u["url"], "via": "rss"} for u in cfg.get("umpan_rss", [])
              if isinstance(u, dict) and u.get("aktif", True) and str(u.get("url", "")).startswith("http")]
    for u in umpan:
        try:
            _, isi, _ = ambil(u["url"], 20, MAKS_BYTE_HALAMAN)
            kandidat += baca_rss(isi, u["via"])
        except Exception as e:  # noqa: BLE001 - satu umpan gagal tidak menghentikan yang lain
            galat.append(f"{u['nama']}: {e.__class__.__name__}: {e}"[:300])
    return kandidat, galat


def gabung_unik(daftar: list[dict]) -> list[dict]:
    """Satu berita satu entri. Berkas yang sudah punya isi (dari Tavily) dipertahankan dan semua jalur penemuan dicatat."""
    per_url: dict[str, dict] = {}
    per_judul: dict[str, str] = {}
    for b in daftar:
        k = kanonik(b["url"])
        kj = _kunci_judul(b["judul"])
        if k in per_url or (kj and kj in per_judul):
            ada = per_url[k if k in per_url else per_judul[kj]]
            ada["via"] = sorted(set(ada["via"]) | {b["via"]})
            if not ada["teks"] and b["teks"]:
                ada["teks"] = b["teks"]
            ada["tanggal"] = ada["tanggal"] or b["tanggal"]
            continue
        b = {**b, "via": [b["via"]]}
        per_url[k] = b
        if kj:
            per_judul[kj] = k
    return list(per_url.values())


# ---------------------------------------------------------------- isi halaman

class _PenarikTeks(HTMLParser):
    SKIP = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "iframe", "svg", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.dalam_skip = 0
        self.dalam_artikel = 0
        self.dalam_p = False
        self.p_sekarang: list[str] = []
        self.p_artikel: list[str] = []
        self.p_semua: list[str] = []
        self.judul = ""
        self.dalam_judul = False
        self.og_judul = ""
        self.tanggal = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self.dalam_skip += 1
        elif tag == "article":
            self.dalam_artikel += 1
        elif tag == "p" and not self.dalam_skip:
            self.dalam_p = True
            self.p_sekarang = []
        elif tag == "title":
            self.dalam_judul = True
        elif tag == "meta":
            kunci = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            isi = a.get("content") or ""
            if kunci == "og:title" and isi:
                self.og_judul = isi
            elif kunci in ("article:published_time", "datepublished", "og:updated_time", "pubdate", "date") and isi and not self.tanggal:
                self.tanggal = isi
        elif tag == "time" and a.get("datetime") and not self.tanggal:
            self.tanggal = a["datetime"]

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.dalam_skip:
            self.dalam_skip -= 1
        elif tag == "article" and self.dalam_artikel:
            self.dalam_artikel -= 1
        elif tag == "title":
            self.dalam_judul = False
        elif tag == "p" and self.dalam_p:
            self.dalam_p = False
            t = _bersih("".join(self.p_sekarang))
            if len(t) >= 40:
                self.p_semua.append(t)
                if self.dalam_artikel:
                    self.p_artikel.append(t)

    def handle_data(self, data):
        if self.dalam_judul:
            self.judul += data
        if self.dalam_p and not self.dalam_skip:
            self.p_sekarang.append(data)


def ekstrak_halaman(isi: bytes, jenis: str = "") -> dict:
    """Judul, tanggal terbit, dan teks utama dari halaman HTML dengan pustaka standar (paragraf di dalam <article> bila ada)."""
    m = re.search(r"charset=([\w-]+)", jenis or "", re.I) or re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", isi[:4000], re.I)
    sandi = (m.group(1).decode() if m and isinstance(m.group(1), bytes) else (m.group(1) if m else "utf-8"))
    try:
        teks_html = isi.decode(sandi, "replace")
    except LookupError:
        teks_html = isi.decode("utf-8", "replace")
    p = _PenarikTeks()
    try:
        p.feed(teks_html)
    except Exception:  # noqa: BLE001 - HTML rusak: pakai apa yang sudah terkumpul
        pass
    paragraf = p.p_artikel if sum(len(x) for x in p.p_artikel) >= MIN_TEKS_TERBACA else p.p_semua
    judul = _bersih(p.og_judul or p.judul)
    judul = re.split(r"\s+[|–—]\s+", judul)[0] if " | " in judul else judul
    return {"judul": judul, "tanggal": parse_tanggal(p.tanggal), "teks": "\n".join(paragraf)[:MAKS_TEKS]}


def baca_halaman(b: dict, robots: Robots, ambil=ambil_http) -> str:
    """Lengkapi isi berita dengan mengunduh halamannya. Mengembalikan catatan (kosong bila berhasil)."""
    if b["teks"] and len(b["teks"]) >= MIN_TEKS_TERBACA:
        return ""
    if not robots.boleh(b["url"]):
        return "robots.txt melarang"
    try:
        url_akhir, isi, jenis = ambil(b["url"], 20, MAKS_BYTE_HALAMAN)
    except Exception as e:  # noqa: BLE001
        return f"gagal diunduh: {e.__class__.__name__}"
    host = host_dari(url_akhir)
    if host == "news.google.com" or host.endswith("consent.google.com"):
        return "tautan Google Berita tidak mengarah ke halaman artikel"
    if "html" not in (jenis or "").lower() and "xml" not in (jenis or "").lower():
        return f"bukan halaman HTML ({jenis or 'tanpa jenis'})"
    if url_akhir != b["url"] and not robots.boleh(url_akhir):
        return "robots.txt melarang halaman tujuan"
    h = ekstrak_halaman(isi, jenis)
    if len(h["teks"]) < MIN_TEKS_TERBACA:
        return "isi artikel tidak terbaca (halaman kosong, berbayar, atau memakai JavaScript)"
    b["teks"] = h["teks"]
    b["judul"] = b["judul"] or h["judul"]
    b["tanggal"] = b["tanggal"] or h["tanggal"]
    b["sumber"] = b["sumber"] or host
    b["url_akhir"] = url_akhir
    return ""


# ---------------------------------------------------------------- relevansi, tag, harga

def kata_wilayah(konf: Konfigurasi) -> dict[str, list[str]]:
    def inti(nama: str) -> str:
        return re.sub(r"^(kabupaten|provinsi)\s+", "", nama.strip(), flags=re.I).lower()
    hasil = {"target": [], "pembanding": []}
    for w in konf.wilayah.values():
        if w.peran == "target":
            hasil["target"].append(inti(w.nama))
        elif w.peran.startswith("pembanding") and w.peran != "pembanding_provinsi":
            hasil["pembanding"].append(inti(w.nama))
    hasil["target"] = hasil["target"] or ["bengkulu tengah"]
    return hasil


def _kata_komoditas(konf: Konfigurasi) -> dict[str, list[str]]:
    """Nama komoditas -> kata penanda (nama komoditas dan sinonim)."""
    hasil: dict[str, list[str]] = {}
    for v in konf.varian.values():
        kata = hasil.setdefault(v.komoditas, [v.komoditas.lower()])
        kata += [k for k in SINONIM_KOMODITAS.get(v.kode_komoditas, []) if k not in kata]
    for info in KOMODITAS_TAMBAHAN.values():
        hasil.setdefault(info["nama"], list(info["alias"]))
    return hasil


def _punya(pola: str, teks: str) -> bool:
    return bool(re.search(rf"(?<![a-z]){re.escape(pola)}(?![a-z])", teks))


def analisis_isi(judul: str, teks: str, konf: Konfigurasi) -> dict:
    """Relevansi (tinggi, sedang, rendah, atau tidak relevan), wilayah, komoditas, dan tag kejadian."""
    j, t = _norm(judul), _norm(teks)
    w = kata_wilayah(konf)
    target_j = any(_punya(k, j) for k in w["target"])
    target_t = any(_punya(k, t) for k in w["target"])
    pembanding = sorted({k for k in w["pembanding"] if _punya(k, j) or _punya(k, t)})
    # Kata "Bengkulu" saja (tanpa nama kabupaten) hanya dihitung di judul dan awal teks. Di bagian bawah halaman ia sering
    # muncul dalam daftar provinsi atau menu, padahal beritanya tentang daerah lain.
    bengkulu = _punya("bengkulu", j) or _punya("bengkulu", t[:AWAL_TEKS])
    komoditas_j, komoditas_t = [], []
    for nama, kata in _kata_komoditas(konf).items():
        if any(_punya(k, j) for k in kata):
            komoditas_j.append(nama)
        elif any(_punya(k, t) for k in kata):
            komoditas_t.append(nama)
    harga_j, harga_t = bool(KATA_HARGA.search(j)), bool(KATA_HARGA.search(t))
    skor = (3 * target_j + 2 * (target_t and not target_j) + len(pembanding) + (1 if bengkulu and not (target_j or target_t) else 0)
            + 2 * min(len(komoditas_j), 2) + min(len(komoditas_t), 3) + (2 if harga_j else 1 if harga_t else 0))
    punya_wilayah = target_j or target_t or bool(pembanding) or bengkulu
    punya_topik = bool(komoditas_j or komoditas_t) or harga_j or harga_t
    if not (punya_wilayah and punya_topik) or skor < 4:
        relevansi = "tidak"
    elif (target_j or target_t) and (komoditas_j or komoditas_t) and skor >= 7:
        relevansi = "tinggi"
    elif skor >= 5:
        relevansi = "sedang"
    else:
        relevansi = "rendah"
    tag = [kode for kode, (_, pola) in TAG.items() if re.search(pola, f"{j} {t[:6000]}")]
    return {"relevansi": relevansi, "skor": skor, "wilayah": {"target": target_j or target_t, "pembanding": pembanding, "provinsi": bengkulu},
            "komoditas": komoditas_j + komoditas_t, "tag": tag}


def _alias_harga(konf: Konfigurasi) -> list[tuple[str, str | None, str]]:
    """(alias, kode varian atau None, kode komoditas), terpanjang dulu supaya 'cabai rawit merah' menang atas 'cabai'."""
    alias: dict[str, tuple[str | None, str]] = {}
    for kode_k, daftar in SINONIM_KOMODITAS.items():
        for a in daftar:
            alias[a] = (None, kode_k)
    for v in konf.varian.values():
        alias[_norm(v.nama)] = (v.kode, v.kode_komoditas)
        alias.setdefault(_norm(v.komoditas), (None, v.kode_komoditas))
    for a, kode in SINONIM_VARIAN.items():
        if kode in konf.varian:
            alias[a] = (kode, konf.varian[kode].kode_komoditas)
    for kode_k, info in KOMODITAS_TAMBAHAN.items():
        for a in info["alias"]:
            alias[a] = (None, kode_k)
    return sorted(((a, v, k) for a, (v, k) in alias.items()), key=lambda x: -len(x[0]))


def _batas(konf: Konfigurasi, varian: str | None, komoditas: str) -> tuple[float, float] | None:
    if varian and varian in konf.varian:
        v = konf.varian[varian]
        return v.batas_bawah, v.batas_atas
    sama = [v for v in konf.varian.values() if v.kode_komoditas == komoditas]
    return (min(v.batas_bawah for v in sama), max(v.batas_atas for v in sama)) if sama else None


def _posisi(alias: str, teks: str) -> list[tuple[int, int]]:
    """Semua (awal, akhir) kemunculan alias sebagai kata utuh."""
    return [(m.start(), m.end()) for m in re.finditer(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", teks)]


def _alias_dekat(kalimat: str, awal_harga: int, akhir_harga: int, alias) -> tuple[str | None, str] | None:
    """Alias komoditas terdekat sebelum harga (akhirnya paling dekat, yang terpanjang menang bila sama), atau bila tidak ada,
    yang terdekat sesudahnya. Mengembalikan (kode varian atau None, kode komoditas)."""
    sebelum = _norm(kalimat[:awal_harga])
    cocok = [(akhir, len(a), v, k) for a, v, k in alias for _, akhir in _posisi(a, sebelum)]
    if cocok:
        _, _, v, k = max(cocok, key=lambda x: (x[0], x[1]))
        return v, k
    sesudah = _norm(kalimat[akhir_harga:])
    cocok = [(mulai, -len(a), v, k) for a, v, k in alias for mulai, _ in _posisi(a, sesudah)]
    if cocok:
        _, _, v, k = min(cocok, key=lambda x: (x[0], x[1]))
        return v, k
    return None


def _nilai_rupiah(m: re.Match) -> float:
    if m.group("titik"):
        return float(m.group("titik").replace(".", ""))
    if m.group("skala"):
        angka = float(m.group("desimal").replace(",", "."))
        return angka * (1_000_000 if m.group("skala").lower() == "juta" else 1000)
    return float(m.group("polos"))


def _satuan_setelah(kalimat: str, posisi: int) -> str | None:
    m = RE_SATUAN.match(kalimat[posisi:posisi + 30])
    if not m:
        return None
    s = m.group("s").lower()
    return SATUAN_SAH.get(s) or (s if s in SATUAN_LAIN else None)


def _peran_kalimat(kalimat: str, w: dict[str, list[str]]) -> str:
    k = _norm(kalimat)
    if any(_punya(x, k) for x in w["target"]):
        return "target"
    if any(_punya(x, k) for x in w["pembanding"]):
        return "pembanding"
    if _punya("bengkulu", k):
        return "provinsi"
    if re.search(r"\bnasional\b|\bindonesia\b|\brata-rata nasional\b", k):
        return "nasional"
    return "tidak jelas"


def _pasar_dalam(kalimat: str, konf: Konfigurasi) -> str | None:
    """Nama pasar yang dikenal sistem bila disebut di kalimat (mis. Pasar Taba Penanjung)."""
    k = _norm(kalimat)
    for p in konf.pasar.values():
        inti = re.sub(r"\(.*?\)", "", p.nama).lower().replace("pasar", "").strip()
        if inti and _punya(inti, k):
            return re.sub(r"\s*\(.*?\)", "", p.nama).strip()
    return None


def _arah_kalimat(kalimat: str) -> str:
    """'naik', 'turun', atau '' (tidak ada atau bertentangan) menurut kata di kalimat bukti."""
    k = _norm(kalimat)
    naik, turun = bool(re.search(TAG["harga_naik"][1], k)), bool(re.search(TAG["harga_turun"][1], k))
    return "naik" if naik and not turun else "turun" if turun and not naik else ""


def ekstrak_harga(teks: str, konf: Konfigurasi, alias=None) -> list[dict]:
    """Harga per kg atau liter (dan per tabung, kaleng, bungkus, atau karpet untuk komoditas tambahan) dari kalimat berita. Tiap hasil membawa kalimat bukti dan status; yang di luar batas wajar ditolak."""
    alias = alias or _alias_harga(konf)
    w = kata_wilayah(konf)
    hasil, lihat = [], set()
    for kalimat in re.split(r"(?<=[.!?;])\s+|\n+", _bersih_baris(teks)):
        if "Rp" not in kalimat and "rp" not in kalimat:
            continue
        for m in RE_HARGA.finditer(kalimat):
            harga = [(_nilai_rupiah(m), m.end())]
            sisa = kalimat[m.end():]
            rentang = RE_RENTANG.match(sisa)
            if rentang:
                m2 = RE_HARGA.match(kalimat, m.end() + rentang.end())
                if m2:
                    harga.append((_nilai_rupiah(m2), m2.end()))
            satuan = _satuan_setelah(kalimat, harga[-1][1])
            if satuan is None:
                continue
            if PERUBAHAN.search(kalimat[max(0, m.start() - 30):m.start()]):
                continue  # selisih kenaikan atau penurunan, bukan harga
            ketemu = _alias_dekat(kalimat, m.start(), harga[-1][1], alias)
            if not ketemu:
                continue
            varian, kode_k = ketemu
            tambahan = KOMODITAS_TAMBAHAN.get(kode_k)
            if tambahan:
                if satuan not in tambahan["satuan"]:
                    continue
                batas, nama_k = tambahan["batas"], tambahan["nama"]
            elif satuan == "karpet" and kode_k == "TLR":
                varian, batas, nama_k = None, BATAS_TELUR_KARPET, "Telur Ayam"
            elif satuan in ("kg", "liter"):
                batas = _batas(konf, varian, kode_k)
                nama_k = next((v.komoditas for v in konf.varian.values() if v.kode_komoditas == kode_k), kode_k)
            else:
                continue
            for nilai, _ in harga:
                kunci = (kode_k, varian, nilai, satuan)
                if kunci in lihat:
                    continue
                lihat.add(kunci)
                wajar = batas is not None and batas[0] <= nilai <= batas[1]
                hasil.append({
                    "komoditas": nama_k, "kode_komoditas": kode_k, "kode_varian": varian, "nilai": round(nilai), "satuan": satuan,
                    "peran_wilayah": _peran_kalimat(kalimat, w), "pasar": _pasar_dalam(kalimat, konf), "arah": _arah_kalimat(kalimat),
                    "bukti": kalimat.strip()[:300], "status": "kandidat" if wajar else "ditolak: di luar batas wajar",
                })
                if len(hasil) >= MAKS_HARGA_PER_BERITA:
                    return hasil
    return hasil


def _bersih_baris(teks: str) -> str:
    return "\n".join(_bersih(b) for b in teks.splitlines())


# ---------------------------------------------------------------- ringkasan

SISTEM_BERITA = """Anda adalah analis berita untuk BPS Kabupaten Bengkulu Tengah (Provinsi Bengkulu, Indonesia) dalam proyek \
pemantauan harga pangan untuk TPID. Anda meringkas berita lokal tentang harga pangan dan kejadian yang memengaruhinya.

Aturan wajib:
- Gunakan HANYA fakta yang tertulis di teks berita. Jangan menambah angka, nama, tanggal, atau sebab yang tidak ada di teks.
- Tulis dalam bahasa Indonesia sederhana yang mudah dipahami orang awam. Ringkasan 1 sampai 3 kalimat.
- Sebut wilayah persis seperti di berita. Bila berita bukan tentang Bengkulu Tengah, jangan menyimpulkan bahwa harganya \
berlaku di Bengkulu Tengah.
- dampak_harga diisi naik, turun, stabil, atau tidak jelas, sesuai teks.
- tindak_lanjut true hanya bila berita menyebut lonjakan harga, gangguan pasokan atau distribusi, bencana yang mengganggu \
produksi, atau langkah intervensi pemerintah."""

FORMAT_BERITA = """

Balas HANYA dengan satu objek JSON (tanpa teks lain) berbentuk:
{"berita": [{"id": "", "ringkasan": "", "dampak_harga": "naik|turun|stabil|tidak jelas", "komoditas": [""], \
"wilayah_disebut": "", "tindak_lanjut": false}]}"""

SISTEM_KESIMPULAN = """Anda adalah analis untuk BPS Kabupaten Bengkulu Tengah. Dari ringkasan berita lokal berikut, susun kesimpulan harian \
untuk anggota TPID.

Aturan wajib:
- Gunakan HANYA isi ringkasan yang diberikan. Jangan menambah angka, nama, atau sebab baru.
- Bahasa Indonesia sederhana. ringkas 3 sampai 5 kalimat: apa yang terjadi pada harga dan pasokan, di wilayah mana, dan \
apa yang perlu dipantau.
- Bedakan berita yang menyebut Bengkulu Tengah dari berita wilayah lain atau nasional.
- Bila bahan sedikit atau tidak jelas, katakan apa adanya."""

FORMAT_KESIMPULAN = """

Balas HANYA dengan satu objek JSON (tanpa teks lain) berbentuk:
{"ringkas": "", "poin": [""], "perlu_dipantau": [""]}"""


def angka_dalam(teks: str) -> set[str]:
    """Himpunan angka (tanpa pemisah ribuan atau desimal) yang muncul di teks."""
    return {re.sub(r"[.,]", "", x) for x in re.findall(r"\d[\d.,]*", teks or "")}


def bersihkan_angka(ringkasan: str, sumber: str) -> tuple[str, int]:
    """Buang kalimat ringkasan yang memuat angka yang tidak ada di sumbernya. Mengembalikan (teks, jumlah dibuang)."""
    sah = angka_dalam(sumber)
    kalimat = [k for k in re.split(r"(?<=[.!?])\s+", _bersih(ringkasan)) if k]
    baik = [k for k in kalimat if angka_dalam(k) <= sah]
    return " ".join(baik), len(kalimat) - len(baik)


def ringkas_ekstraktif(judul: str, teks: str, konf: Konfigurasi, maks: int = 2) -> str:
    """Cadangan tanpa AI: dua kalimat yang paling banyak memuat kata wilayah, komoditas, dan harga."""
    kata = [k for daftar in _kata_komoditas(konf).values() for k in daftar] + [x for d in kata_wilayah(konf).values() for x in d] + ["bengkulu"]
    kalimat = [k for k in dict.fromkeys(_bersih(x) for x in re.split(r"(?<=[.!?])\s+|\n+", teks)) if 40 <= len(k) <= 400]
    nilai = []
    for i, k in enumerate(kalimat):
        n = _norm(k)
        nilai.append((-(sum(_punya(x, n) for x in kata) + (2 if KATA_HARGA.search(n) else 0) + (1 if re.search(r"\d", n) else 0)), i, k))
    terpilih = sorted(sorted(nilai)[:maks], key=lambda x: x[1])
    return " ".join(_bersih(k) for _, _, k in terpilih) or judul


def tanya_ai(konf: Konfigurasi, sistem: str, pesan: str, format_json: str, klien: dict | None = None) -> tuple[dict, dict]:
    """Tanya AI gratis dengan rotasi penyedia yang sama seperti AI Data Finder (Claude berbayar tidak dipakai di sini)."""
    cfg = {**pencari_data.pengaturan_ai(konf), "_sistem": sistem, "_format_json": format_json}
    urutan = [p for p in pencari_data.urutan_penyedia(konf) if p != "anthropic"] or list(pencari_data.GRATIS)
    galat = []
    for nama in urutan:
        try:
            jawab = pencari_data.PENYEDIA[nama](pesan, cfg, (klien or {}).get(nama))
            return jawab["hasil"], {"penyedia": nama, "model": jawab["model"]}
        except Exception as e:  # noqa: BLE001 - kuota habis, kunci belum ada, jawaban rusak: AI berikutnya
            galat.append(f"{nama}: {e}"[:200])
            log.warning("penyedia %s dilewati untuk berita: %s", nama, e)
    raise RuntimeError("tidak ada AI yang bisa dipakai: " + "; ".join(galat))


def _pesan_berita(daftar: list[dict]) -> str:
    bagian = []
    for b in daftar:
        bagian.append(f"[{b['id']}] Judul: {b['judul']}\nSumber: {b['sumber'] or '-'}\nTanggal: {b['tanggal'] or '-'}\n"
                      f"Teks: {_bersih(b['_teks'])[:POTONG_TEKS_AI]}")
    return "BERITA YANG PERLU DIRINGKAS:\n\n" + "\n\n".join(bagian)


def ringkas_dengan_ai(konf: Konfigurasi, daftar: list[dict], klien: dict | None, tulis) -> tuple[dict[str, dict], dict]:
    """Ringkas berita bergelombang. Mengembalikan ({id: entri}, info penyedia terakhir yang berhasil)."""
    hasil: dict[str, dict] = {}
    info: dict = {}
    for i in range(0, len(daftar), UKURAN_GELOMBANG_AI):
        gelombang = daftar[i:i + UKURAN_GELOMBANG_AI]
        try:
            jawab, info = tanya_ai(konf, SISTEM_BERITA, _pesan_berita(gelombang), FORMAT_BERITA, klien)
        except Exception as e:  # noqa: BLE001
            tulis(f"Ringkasan AI untuk {len(gelombang)} berita gagal: {e}", "peringatan")
            break
        sumber = {b["id"]: b for b in gelombang}
        for r in jawab.get("berita") or []:
            b = sumber.get(str(r.get("id", "")))
            if not b or not isinstance(r, dict):
                continue
            teks, dibuang = bersihkan_angka(str(r.get("ringkasan") or ""), b["_teks"] + " " + b["judul"])
            if not teks:
                continue
            dampak = str(r.get("dampak_harga") or "tidak jelas").lower()
            hasil[b["id"]] = {"ringkasan": teks[:600], "dampak_harga": dampak if dampak in ("naik", "turun", "stabil") else "tidak jelas",
                              "tindak_lanjut": bool(r.get("tindak_lanjut")), "kalimat_dibuang": dibuang}
        tulis(f"{info['penyedia']} ({info['model']}) meringkas {len(gelombang)} berita.")
    return hasil, info


def dampak_dari_tag(tag: list[str]) -> str:
    naik, turun = "harga_naik" in tag, "harga_turun" in tag
    return "naik" if naik and not turun else "turun" if turun and not naik else "tidak jelas"


def kesimpulan_ekstraktif(baru: list[dict], arsip: list[dict], umur: int, tanggal: date) -> dict:
    """Kesimpulan harian tanpa AI, disusun dari jumlah dan tag berita."""
    tag_label = {k: v[0].lower() for k, v in TAG.items()}
    hitung = Counter(t for b in baru for t in b["tag"])
    baris = [f"{len(baru)} berita baru dan {len(arsip)} berita dalam {umur} hari terakhir yang relevan dengan harga pangan Bengkulu."]
    target = [b for b in baru if b["wilayah"]["target"]]
    if target:
        baris.append(f"{len(target)} di antaranya menyebut Bengkulu Tengah.")
    for kode in ("harga_naik", "harga_turun", "pasokan", "cuaca", "intervensi"):
        if hitung.get(kode):
            kom = Counter(k for b in baru if kode in b["tag"] for k in b["komoditas"]).most_common(2)
            tambah = f" ({', '.join(k for k, _ in kom)})" if kom else ""
            baris.append(f"{hitung[kode]} berita menyebut {tag_label[kode]}{tambah}.")
    kandidat = sum(1 for b in baru for h in b["harga"] if h["status"] == "kandidat")
    if kandidat:
        baris.append(f"{kandidat} kandidat harga dari berita menunggu verifikasi analis.")
    if not baru:
        baris = ["Tidak ada berita baru yang relevan hari ini."]
    poin = [f"{b['judul']} ({b['sumber'] or 'sumber tidak diketahui'})" for b in sorted(baru, key=lambda x: -x["skor"])[:3]]
    return {"tanggal": tanggal.isoformat(), "metode": "ekstraktif", "penyedia": "", "ringkas": " ".join(baris), "poin": poin,
            "perlu_dipantau": []}


def kesimpulan_dengan_ai(konf: Konfigurasi, baru: list[dict], arsip: list[dict], umur: int, tanggal: date, klien: dict | None,
                         tulis) -> dict:
    dasar = kesimpulan_ekstraktif(baru, arsip, umur, tanggal)
    if not baru:
        return dasar
    pilih = sorted(baru, key=lambda x: (x["relevansi"] != "tinggi", -x["skor"]))[:15]
    bahan = "\n".join(f"- [{b['tanggal'] or '-'}] {b['judul']} ({b['sumber'] or '-'}). Wilayah target disebut: "
                      f"{'ya' if b['wilayah']['target'] else 'tidak'}. Dampak harga: {b['dampak_harga']}. {b['ringkasan']}" for b in pilih)
    try:
        jawab, info = tanya_ai(konf, SISTEM_KESIMPULAN, f"Tanggal: {tanggal.isoformat()}\n\nRINGKASAN BERITA:\n{bahan}", FORMAT_KESIMPULAN, klien)
    except Exception as e:  # noqa: BLE001
        tulis(f"Kesimpulan AI gagal, dipakai kesimpulan otomatis tanpa AI: {e}", "peringatan")
        return dasar
    sumber = " ".join(b["ringkasan"] + " " + b["judul"] for b in pilih)
    ringkas, dibuang = bersihkan_angka(str(jawab.get("ringkas") or ""), sumber)
    if not ringkas:
        tulis("Kesimpulan AI dibuang karena memuat angka yang tidak ada di ringkasan berita.", "peringatan")
        return dasar
    def bersih_daftar(x):
        return [t for t in (bersihkan_angka(str(i), sumber)[0] for i in (x if isinstance(x, list) else [])) if t][:6]
    tulis(f"{info['penyedia']} ({info['model']}) menyusun kesimpulan harian.")
    return {"tanggal": tanggal.isoformat(), "metode": "ai", "penyedia": info["penyedia"], "ringkas": ringkas[:1200],
            "poin": bersih_daftar(jawab.get("poin")) or dasar["poin"], "perlu_dipantau": bersih_daftar(jawab.get("perlu_dipantau")),
            "kalimat_dibuang": dibuang}


# ---------------------------------------------------------------- jalankan

def _huruf_dominan(s: str) -> bool:
    """Kalimat biasa: sebagian besar huruf, bukan tabel angka atau kurs."""
    return bool(s) and sum(c.isalpha() for c in s) / len(s) >= 0.6 and sum(c.isdigit() for c in s) / len(s) <= 0.2


def kutipan_dari(cuplikan: str, teks: str) -> str:
    """Kutipan pendek untuk daftar berita: cuplikan penerbit bila berupa kalimat, kalau tidak kalimat pertama isi yang wajar."""
    c = _bersih(cuplikan)
    if len(c) >= 40 and _huruf_dominan(c):
        return c[:220]
    for k in re.split(r"(?<=[.!?])\s+|\n+", teks):
        k = _bersih(k)
        if 40 <= len(k) <= 400 and _huruf_dominan(k):
            return k[:220]
    return ""


def _entri(b: dict, analisis: dict, harga: list[dict], waktu: datetime) -> dict:
    teks = b["teks"]
    return {
        "id": id_berita(b["url"]), "url": b.get("url_akhir") or b["url"], "judul": b["judul"], "sumber": b["sumber"] or host_dari(b["url"]),
        "tanggal": b["tanggal"].isoformat() if b["tanggal"] else "", "diakses": waktu.isoformat(timespec="seconds"),
        "via": sorted(b["via"]), "relevansi": analisis["relevansi"], "skor": analisis["skor"], "wilayah": analisis["wilayah"],
        "komoditas": analisis["komoditas"], "tag": analisis["tag"], "isi_terbaca": bool(teks and len(teks) >= MIN_TEKS_TERBACA),
        "catatan_baca": b.get("catatan_baca", ""), "panjang_teks": len(teks),
        "sidik_sha256": hashlib.sha256(teks.encode()).hexdigest() if teks else "",
        "kutipan": kutipan_dari(b["cuplikan"], teks), "ringkasan": "", "metode_ringkas": "", "dampak_harga": "tidak jelas",
        "tindak_lanjut": False, "harga": harga, "baru": True,
    }


def jalankan(konf: Konfigurasi, *, klien: dict | None = None, tanpa_ai: bool = False, sekarang: datetime | None = None,
             catat=None, pengambil=None, arsip: dict | None = None) -> dict:
    """Satu kali jalan penuh. `klien` (untuk uji) bisa memuat "tavily", "ai" (nama penyedia -> fungsi pengganti). `pengambil`
    menggantikan ambil_http. Mengembalikan struktur yang siap ditulis oleh simpan()."""
    cfg = pengaturan_berita(konf)
    klien = klien or {}
    ambil = pengambil or ambil_http
    sekarang = sekarang or datetime.now(WIB)
    hari = sekarang.astimezone(WIB).date()
    langkah: list[dict] = []

    def tulis(teks: str, jenis: str = "info") -> None:
        langkah.append({"waktu": datetime.now(WIB).strftime("%H.%M.%S"), "teks": teks[:400], "jenis": jenis})
        if catat:
            catat(teks, jenis)

    umur = int(cfg["umur_maks_hari"])
    tulis(f"Mulai mencari berita lokal ({len(cfg['kueri'])} kueri Tavily dan Google Berita, {len(cfg.get('kueri_tambahan', []))} kueri tambahan Google Berita, {umur} hari terakhir).")
    mentah, galat = temukan(cfg, umur, ambil, klien.get("tavily"))
    for g in galat:
        tulis(g, "peringatan")
    unik = gabung_unik(mentah)
    tulis(f"{len(mentah)} hasil pencarian, {len(unik)} setelah duplikat dibuang.")
    batas_tgl = hari - timedelta(days=umur)
    diabaikan = tuple(cfg["domain_diabaikan"])
    layak = [b for b in unik if not host_dari(b["url"]).endswith(diabaikan) and (b["tanggal"] is None or b["tanggal"] >= batas_tgl)]
    if len(layak) < len(unik):
        tulis(f"{len(unik) - len(layak)} berita dibuang (terlalu lama atau dari media sosial dan video).")
    # Dahulukan yang tanggalnya diketahui dan terbaru; batasi jumlah yang dibaca isinya.
    layak.sort(key=lambda b: (b["tanggal"] or date.min), reverse=True)
    layak = layak[: int(cfg["maks_berita"])]

    arsip_lama = arsip if arsip is not None else muat(konf)
    sudah = {b["id"] for b in arsip_lama.get("berita", [])}
    robots = Robots(ambil, bool(cfg["hormati_robots"]))
    alias = _alias_harga(konf)
    baru: list[dict] = []
    tak_relevan = tak_terbaca = 0
    mulai = time.monotonic()
    waktu_habis = False
    for b in layak:
        if id_berita(b["url"]) in sudah:
            continue
        if not (b["teks"] and len(b["teks"]) >= MIN_TEKS_TERBACA):
            # Berita yang judulnya jelas tidak relevan tidak perlu diunduh.
            awal = analisis_isi(b["judul"], b["cuplikan"], konf)
            if awal["relevansi"] == "tidak" and not awal["komoditas"] and not KATA_HARGA.search(_norm(b["judul"] + " " + b["cuplikan"])):
                tak_relevan += 1
                continue
            if not waktu_habis and time.monotonic() - mulai > float(cfg["maks_menit"]) * 60:
                waktu_habis = True
                tulis(f"Batas waktu mengunduh halaman ({cfg['maks_menit']} menit) tercapai. Sisa berita hanya memakai judul dan cuplikan.", "peringatan")
            if waktu_habis:
                b["catatan_baca"] = "batas waktu pengunduhan habis"
            else:
                b["catatan_baca"] = baca_halaman(b, robots, ambil)
                if not pengambil and cfg["jeda_detik"]:
                    time.sleep(float(cfg["jeda_detik"]))
        teks = b["teks"] or b["cuplikan"]
        a = analisis_isi(b["judul"], teks, konf)
        if a["relevansi"] == "tidak":
            tak_relevan += 1
            continue
        if not b["teks"]:
            tak_terbaca += 1
        harga = ekstrak_harga(teks if b["teks"] else "", konf, alias)
        e = _entri(b, a, harga, sekarang)
        e["_teks"] = teks
        baru.append(e)
    tulis(f"{len(baru)} berita baru relevan, {tak_relevan} tidak relevan dibuang, {tak_terbaca} isinya tidak terbaca (hanya judul dan cuplikan).")

    # ringkasan: AI untuk yang paling relevan, cadangan ekstraktif untuk sisanya
    info_ai: dict = {}
    pakai_ai = bool(cfg["pakai_ai"]) and not tanpa_ai
    untuk_ai = [e for e in sorted(baru, key=lambda x: (x["relevansi"] != "tinggi", -x["skor"])) if e["isi_terbaca"]][: int(cfg["maks_diringkas"])]
    ringkas_ai: dict[str, dict] = {}
    if pakai_ai and untuk_ai:
        ringkas_ai, info_ai = ringkas_dengan_ai(konf, untuk_ai, klien.get("ai"), tulis)
    elif not pakai_ai:
        tulis("Ringkasan AI dimatikan, dipakai ringkasan otomatis tanpa AI.")
    for e in baru:
        r = ringkas_ai.get(e["id"])
        if r:
            e.update({"ringkasan": r["ringkasan"], "dampak_harga": r["dampak_harga"], "tindak_lanjut": r["tindak_lanjut"], "metode_ringkas": "ai"})
            if info_ai:
                e["penyedia_ai"] = info_ai["penyedia"]
        elif e["isi_terbaca"]:
            e.update({"ringkasan": ringkas_ekstraktif(e["judul"], e["_teks"], konf), "metode_ringkas": "ekstraktif",
                      "dampak_harga": dampak_dari_tag(e["tag"]), "tindak_lanjut": bool({"pasokan", "cuaca", "intervensi"} & set(e["tag"]))})
        else:
            e.update({"ringkasan": "Isi berita tidak bisa dibaca otomatis. Buka tautan untuk membaca beritanya.", "metode_ringkas": "judul",
                      "dampak_harga": dampak_dari_tag(e["tag"])})
    for e in baru:
        e.pop("_teks", None)

    # gabung ke arsip (tanpa teks lengkap), buang yang lama
    simpan_sejak = hari - timedelta(days=int(cfg["simpan_hari"]))
    lama = [{**b, "baru": False} for b in arsip_lama.get("berita", []) if (b.get("tanggal") or b.get("diakses", "")[:10]) >= simpan_sejak.isoformat()]
    semua = sorted(baru + lama, key=lambda b: (b["tanggal"] or b["diakses"][:10], b["skor"]), reverse=True)[:MAKS_ARSIP]
    relevan_umur = [b for b in semua if (b["tanggal"] or b["diakses"][:10]) >= batas_tgl.isoformat()]

    kesimpulan = kesimpulan_dengan_ai(konf, baru, relevan_umur, umur, hari, klien.get("ai"), tulis) if pakai_ai else kesimpulan_ekstraktif(baru, relevan_umur, umur, hari)
    riwayat = [k for k in arsip_lama.get("kesimpulan", []) if k.get("tanggal") != hari.isoformat()]
    kesimpulan_semua = ([kesimpulan] + riwayat)[:MAKS_KESIMPULAN]
    tulis(f"Kesimpulan harian disusun ({kesimpulan['metode']}).")

    harga_kandidat = sum(1 for b in baru for h in b["harga"] if h["status"] == "kandidat")
    return {
        "diperbarui": sekarang.isoformat(timespec="seconds"),
        "kesimpulan": kesimpulan_semua,
        "berita": semua,
        "statistik": {"hasil_pencarian": len(mentah), "setelah_duplikat": len(unik), "berita_baru": len(baru), "total_arsip": len(semua),
                      "kandidat_harga_baru": harga_kandidat, "isi_tidak_terbaca": tak_terbaca,
                      "penyedia_ai": info_ai.get("penyedia", ""), "model_ai": info_ai.get("model", "")},
        "galat": galat[:20],
        "log": langkah,
    }


# ---------------------------------------------------------------- penyimpanan

def jalur(konf: Konfigurasi) -> Path:
    return konf.akar / "data" / "berita" / "berita.json"


def muat(konf: Konfigurasi) -> dict:
    p = jalur(konf)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {"berita": [], "kesimpulan": []}
    except (OSError, ValueError):
        return {"berita": [], "kesimpulan": []}


def simpan(konf: Konfigurasi, hasil: dict) -> Path:
    p = jalur(konf)
    p.parent.mkdir(parents=True, exist_ok=True)
    isi = {k: v for k, v in hasil.items() if k != "log"}
    p.write_text(json.dumps(isi, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


URUT_PERAN = ["target", "pembanding", "provinsi", "nasional", "tidak jelas"]
AMBANG_BEDA_JAUH_PERSEN = 15.0


def ringkasan_harga(konf: Konfigurasi, berita: list[dict], harga_utama: dict[str, float] | None, hari: date, umur: int = 14) -> list[dict]:
    """Harga kandidat dari berita, dikelompokkan per komoditas: rentang, wilayah paling relevan, arah, alasan di berita, dan (bila ada)
    selisih terhadap harga utama sistem. Hanya penunjuk; tidak pernah masuk deret harga resmi."""
    batas = (hari - timedelta(days=umur)).isoformat()
    kelompok: dict[tuple[str, str], list[dict]] = {}
    for b in berita:
        tgl = b.get("tanggal") or (b.get("diakses") or "")[:10]
        if tgl < batas:
            continue
        for h in b.get("harga", []):
            if h.get("status") == "kandidat":
                kelompok.setdefault((h["kode_komoditas"], h["satuan"]), []).append(
                    {**h, "tanggal": tgl, "judul": b.get("judul", ""), "url": b.get("url", ""), "sumber": b.get("sumber", ""), "tag": b.get("tag", [])})
    hasil = []
    for (kode_k, satuan), daftar in kelompok.items():
        nilai = sorted(x["nilai"] for x in daftar)
        peran = lambda x: URUT_PERAN.index(x["peran_wilayah"]) if x.get("peran_wilayah") in URUT_PERAN else len(URUT_PERAN)  # noqa: E731
        terbaik = sorted(daftar, key=lambda x: (peran(x), [-ord(c) for c in x["tanggal"]]))[0]
        sebanding = [x for x in daftar if peran(x) == peran(terbaik)]
        nilai_w = sorted(x["nilai"] for x in sebanding)
        median = nilai_w[len(nilai_w) // 2] if len(nilai_w) % 2 else (nilai_w[len(nilai_w) // 2 - 1] + nilai_w[len(nilai_w) // 2]) / 2
        naik, turun = sum(1 for x in daftar if x.get("arah") == "naik"), sum(1 for x in daftar if x.get("arah") == "turun")
        alasan = [TAG[t][0] for t in dict.fromkeys(t for x in daftar for t in x["tag"]) if t in TAG and t not in ("harga_naik", "harga_turun")]
        banding = None
        if harga_utama and satuan in ("kg", "liter"):
            varian = sorted({x["kode_varian"] for x in daftar if x.get("kode_varian")})
            acuan = [harga_utama[v] for v in varian if v in harga_utama] or \
                    [harga_utama[v.kode] for v in konf.varian.values() if v.kode_komoditas == kode_k and v.kode in harga_utama]
            if acuan:
                acuan.sort()
                utama = acuan[len(acuan) // 2] if len(acuan) % 2 else (acuan[len(acuan) // 2 - 1] + acuan[len(acuan) // 2]) / 2
                selisih = round((median / utama - 1) * 100, 1)
                banding = {"dasar": varian[0] if len(varian) == 1 else "median varian komoditas", "harga_utama": round(utama), "selisih_persen": selisih,
                           "beda_jauh": abs(selisih) > AMBANG_BEDA_JAUH_PERSEN}
        hasil.append({
            "kode_komoditas": kode_k, "komoditas": terbaik["komoditas"], "satuan": satuan, "jumlah_kandidat": len(daftar),
            "jumlah_berita": len({x["url"] for x in daftar}), "wilayah": terbaik.get("peran_wilayah", "tidak jelas"),
            "median": round(median), "minimum": nilai[0], "maksimum": nilai[-1], "tanggal_terbaru": max(x["tanggal"] for x in daftar),
            "arah": "naik" if naik > turun else "turun" if turun > naik else "belum jelas", "alasan": alasan[:3], "banding": banding,
            "contoh": {k: terbaik.get(k) for k in ("nilai", "bukti", "url", "judul", "sumber", "pasar", "tanggal")},
        })
    hasil.sort(key=lambda x: (URUT_PERAN.index(x["wilayah"]) if x["wilayah"] in URUT_PERAN else 9, -x["jumlah_berita"], x["komoditas"]))
    return hasil


def untuk_situs(konf: Konfigurasi, harga_utama: dict[str, float] | None = None, hari: date | None = None) -> dict:
    """Data untuk halaman Berita Lokal (site/data/berita.json): arsip, kesimpulan, statistik, dan penjelasan batasnya."""
    d = muat(konf)
    hari = hari or datetime.now(WIB).date()
    umur = int(pengaturan_berita(konf)["umur_maks_hari"])
    return {"diperbarui": d.get("diperbarui"), "kesimpulan": d.get("kesimpulan", []), "berita": d.get("berita", []),
            "statistik": d.get("statistik", {}), "galat": d.get("galat", []),
            "ringkasan_harga": ringkasan_harga(konf, d.get("berita", []), harga_utama, hari, umur),
            "ambang_beda_jauh_persen": AMBANG_BEDA_JAUH_PERSEN,
            "label_tag": {k: v[0] for k, v in TAG.items()},
            "catatan": "Harga di berita hanyalah penunjuk. Angkanya belum diverifikasi dan tidak masuk deret harga resmi."}

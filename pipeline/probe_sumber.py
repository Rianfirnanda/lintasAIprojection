"""Penjajakan sumber data harga pangan tingkat kabupaten/kota (dijalankan di GitHub Actions, bukan di sandbox pengembangan).

Tujuannya hanya mencari tahu apa yang sungguh tersedia: apakah PIHPS punya data tingkat kota/kabupaten untuk Provinsi
Bengkulu, dan apakah Panel Harga Bapanas, SP2KP, atau portal data terbuka menyediakan harga Kabupaten Bengkulu Tengah,
Kepahiang, dan Kota Bengkulu. Tidak ada data yang dikarang: hasilnya apa adanya (status HTTP, bentuk jawaban, dan apakah
nama wilayah sasaran muncul), ditulis ke data/sumber/hasil_probe.json untuk dibaca manusia.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (pemantauan harga BPS Bengkulu Tengah; penjajakan sumber)", "Accept": "application/json, text/html, */*",
      "X-Requested-With": "XMLHttpRequest"}
WILAYAH = ("bengkulu tengah", "kepahiang", "kota bengkulu", "bengkulu")
PIHPS = "https://www.bi.go.id/hargapangan/WebSite/TabelHarga/GetGridDataDaerah"
PIHPS_REF = "https://www.bi.go.id/hargapangan/WebSite/Home"
BAPANAS_API = "https://api-panelharga.badanpangan.go.id/api/front"
JEDA = 1.0


def ambil(url: str, batas_waktu: int = 25, maks_byte: int = 400_000) -> dict:
    """GET apa adanya. Tidak pernah melempar: galat jaringan dicatat sebagai hasil."""
    mulai = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=batas_waktu) as r:
            isi = r.read(maks_byte)
            return {"url": url, "status": r.status, "jenis": r.headers.get("Content-Type", ""), "byte": len(isi),
                    "detik": round(time.time() - mulai, 1), "isi": isi}
    except urllib.error.HTTPError as e:
        return {"url": url, "status": e.code, "jenis": "", "byte": 0, "detik": round(time.time() - mulai, 1), "isi": b"",
                "galat": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"url": url, "status": 0, "jenis": "", "byte": 0, "detik": round(time.time() - mulai, 1), "isi": b"",
                "galat": f"{e.__class__.__name__}: {e}"[:200]}


def _teks(h: dict) -> str:
    return h["isi"].decode("utf-8", "replace")


def ringkas(h: dict, catatan: str = "") -> dict:
    t = _teks(h)
    ada = sorted({w for w in WILAYAH if w in t.lower()})
    hasil = {"url": h["url"], "status": h["status"], "jenis": h["jenis"], "byte": h["byte"], "detik": h["detik"],
             "wilayah_disebut": ada, "cuplikan": re.sub(r"\s+", " ", t)[:400]}
    if h.get("galat"):
        hasil["galat"] = h["galat"]
    if catatan:
        hasil["catatan"] = catatan
    try:
        d = json.loads(t)
        hasil["json"] = True
        hasil["kunci"] = list(d)[:15] if isinstance(d, dict) else f"daftar {len(d)} item"
    except ValueError:
        hasil["json"] = False
    return hasil


def penjajakan_pihps(ambil_fn=ambil, hari: date | None = None) -> list[dict]:
    hari = hari or date.today()
    mulai = (hari - timedelta(days=6)).isoformat()
    hasil = []
    for jalur in ("GetRefProvince", "GetRefRegency?ref_prov_id=7", "GetRefRegency?province_id=7", "GetRefMarket?ref_prov_id=7",
                  "GetRefMarket?province_id=7", "GetRefCommodity"):
        hasil.append(ringkas(ambil_fn(f"{PIHPS_REF}/{jalur}"), "daftar acuan PIHPS"))
        time.sleep(JEDA)
    for tipe in (1, 2, 3):
        for price_type in (1,):
            q = {"price_type_id": price_type, "comcat_id": "", "province_id": 7, "regency_id": "", "market_id": "",
                 "tipe_laporan": tipe, "start_date": mulai, "end_date": hari.isoformat()}
            h = ambil_fn(f"{PIHPS}?{urllib.parse.urlencode(q)}")
            r = ringkas(h, f"tabel harga tipe_laporan={tipe}")
            try:
                d = json.loads(_teks(h))
                baris = d.get("data") or []
                r["jumlah_baris"] = len(baris)
                r["nama_level"] = sorted({(str(b.get("level")), str(b.get("name"))) for b in baris})[:40]
            except (ValueError, AttributeError):
                pass
            hasil.append(r)
            time.sleep(JEDA)
    return hasil


def penjajakan_bapanas(ambil_fn=ambil, hari: date | None = None) -> list[dict]:
    hari = hari or date.today()
    tgl = (hari - timedelta(days=1)).strftime("%d/%m/%Y")
    calon = [
        f"{BAPANAS_API}/komoditas",
        f"{BAPANAS_API}/harga-peta-provinsi?level_harga_id=3&komoditas_id=27&period_date={urllib.parse.quote(tgl + ' - ' + tgl)}",
        f"{BAPANAS_API}/harga-peta-kabkota?level_harga_id=3&komoditas_id=27&period_date={urllib.parse.quote(tgl + ' - ' + tgl)}&provinsi_id=7",
        f"{BAPANAS_API}/provinsi",
        "https://panelharga.badanpangan.go.id/",
    ]
    out = []
    for u in calon:
        out.append(ringkas(ambil_fn(u), "Panel Harga Bapanas (tebakan jalur; lihat status)"))
        time.sleep(JEDA)
    return out


def penjajakan_lain(ambil_fn=ambil) -> list[dict]:
    calon = [
        ("https://sp2kp.kemendag.go.id/", "SP2KP halaman utama"),
        ("https://api-sp2kp.kemendag.go.id/", "SP2KP kemungkinan API"),
        ("https://data.go.id/api/3/action/package_search?q=harga+bahan+pokok+kabupaten&rows=10", "data.go.id pencarian"),
        ("https://satudata.badanpangan.go.id/", "Bapanas satu data"),
        ("https://www.bi.go.id/hargapangan/", "PIHPS beranda"),
        ("https://webapi.bps.go.id/", "BPS Web API (butuh kunci)"),
    ]
    out = []
    for u, c in calon:
        h = ambil_fn(u)
        r = ringkas(h, c)
        if h["status"] == 200 and "html" in h["jenis"].lower():
            t = _teks(h)
            r["tautan_menarik"] = sorted(set(re.findall(r"""(?:src|href)=["']([^"']*(?:api|harga|data)[^"']*)["']""", t, re.I)))[:15]
        out.append(r)
        time.sleep(JEDA)
    return out


POLA_ENDPOINT = re.compile(
    r"""["'`]((?:https?:)?//[^"'`\s<>]*(?:api|hargapangan|badanpangan|sp2kp)[^"'`\s<>]*|/[A-Za-z0-9_\-./]*(?:Get[A-Za-z]+|api/[A-Za-z0-9_\-./]+)[A-Za-z0-9_\-./?=&%]*)["'`]""",
    re.I)
HALAMAN_JELAJAH = (
    ("pihps", "https://www.bi.go.id/hargapangan/TabelHarga/PasarTradisionalDaerah"),
    ("bapanas", "https://panelharga.badanpangan.go.id/"),
    ("sp2kp", "https://sp2kp.kemendag.go.id/"),
)
KUNCI_NAMA = ("text", "name", "nama", "label", "regency_name", "market_name", "province_name", "nama_kabupaten", "nama_kota")


POLA_KONTEKS = {
    # (pola, lebar potongan, maksimal potongan): fungsi inline PIHPS yang mengisi parameter, dan nama parameter API Panel Harga
    "pihps": [(re.compile(r"function\s+(?:beforesend\w+|provinceChanged|OnBeforeSend|refreshPasar|regencyChanged)"), 700, 12),
              (re.compile(r"GetRef\w+|GetGrid\w+|GetChart\w+"), 170, 20)],
    "bapanas": [(re.compile(r"period_date|level_harga_id|kode_provinsi|province_id|provinsi_id|kabkota|kab_kota|city_id|kota_id|kode_kab"), 280, 60),
                (re.compile(r"""["'`][\w\-/{}$.:]*(?:front)/[\w\-/{}$.:?=&]*["'`]"""), 120, 40)],
    "sp2kp": [(re.compile(r"""["'`]https://api-sp2kp[\w\-/.:?=&{}$]*["'`]|["'`]/(?:report|master|public|front)/api[\w\-/?=&{}$]*["'`]"""), 160, 40)],
}


def cari_konteks(teks: str, pola: re.Pattern, lebar: int = 170, maks: int = 45) -> list[str]:
    """Potongan teks di sekitar kata kunci, supaya terlihat parameter apa yang dipakai situs saat memanggil alamat itu."""
    hasil, lihat = [], set()
    for m in pola.finditer(teks):
        kunci = m.group(0)
        if kunci in lihat:
            continue
        lihat.add(kunci)
        hasil.append(re.sub(r"\s+", " ", teks[max(0, m.start() - lebar): m.end() + lebar]))
        if len(hasil) >= maks:
            break
    return hasil


def jelajah_halaman(url: str, ambil_fn=ambil, maks_skrip: int = 10, pola_konteks: list | None = None) -> dict:
    """Membuka halaman, lalu berkas JavaScript-nya, untuk membaca alamat API yang dipakai situs itu sendiri."""
    h = ambil_fn(url, 30, 2_500_000) if ambil_fn is ambil else ambil_fn(url)
    hasil = {"halaman": url, "status": h["status"], "skrip": [], "endpoint": [], "konteks": []}
    if h["status"] != 200:
        hasil["galat"] = h.get("galat", "")
        return hasil
    html = _teks(h)
    hasil["endpoint"] = sorted(set(POLA_ENDPOINT.findall(html)))[:80]
    for pola, lebar, maks in pola_konteks or []:
        hasil["konteks"] += [("html", c) for c in cari_konteks(html, pola, lebar, maks)]
    srcs = re.findall(r"""<script[^>]+src=["']([^"']+\.js[^"']*)["']""", html, re.I)
    for src in srcs[:maks_skrip]:
        alamat = urllib.parse.urljoin(url, src)
        hs = ambil_fn(alamat, 30, 2_500_000) if ambil_fn is ambil else ambil_fn(alamat)
        hasil["skrip"].append({"url": alamat, "status": hs["status"], "byte": hs["byte"]})
        if hs["status"] == 200:
            hasil["endpoint"] = sorted(set(hasil["endpoint"]) | set(POLA_ENDPOINT.findall(_teks(hs))))[:120]
            if pola_konteks and hs["byte"] > 100_000:  # berkas aplikasi utama, bukan pustaka kecil
                for pola, lebar, maks in pola_konteks:
                    hasil["konteks"] += [(src.rsplit("/", 1)[-1], c) for c in cari_konteks(_teks(hs), pola, lebar, maks)]
        time.sleep(JEDA)
    return hasil


def nama_dari_json(teks: str, batas: int = 80) -> list[str]:
    try:
        d = json.loads(teks)
    except ValueError:
        return []
    if isinstance(d, dict):
        d = d.get("data") or d.get("result") or d.get("items") or []
    nama = []
    for item in d if isinstance(d, list) else []:
        if isinstance(item, dict):
            n = next((str(item[k]) for k in KUNCI_NAMA if k in item), None)
            if n:
                nama.append(n)
        elif isinstance(item, str):
            nama.append(item)
    return nama[:batas]


def coba_daftar_acuan_pihps(ambil_fn=ambil, endpoint: list[str] | None = None) -> list[dict]:
    """Mencoba alamat daftar provinsi, kabupaten/kota, dan pasar PIHPS (dugaan umum + yang ditemukan di JavaScript situsnya)."""
    dasar = "https://www.bi.go.id/hargapangan/WebSite/TabelHarga"
    calon = [f"{dasar}/GetRefProvince", f"{dasar}/GetRefRegency?ref_prov_id=7", f"{dasar}/GetRefRegency?province_id=7",
             f"{dasar}/GetRefRegency?provId=7", f"{dasar}/GetRefMarket?ref_regency_id=", f"{dasar}/GetRefMarket?regency_id=",
             f"{dasar}/GetRefCommodity", "https://www.bi.go.id/hargapangan/WebSite/Home/GetProvince",
             "https://www.bi.go.id/hargapangan/WebSite/Home/GetRegency?province_id=7"]
    for e in endpoint or []:
        if re.search(r"Get(Ref)?(Province|Regency|City|Market|Komoditas|Commodity)", e, re.I) and "/hargapangan/" in e:
            calon.append(urllib.parse.urljoin("https://www.bi.go.id", e) if e.startswith("/") else e)
    hasil, dilihat = [], set()
    for u in calon:
        if u in dilihat:
            continue
        dilihat.add(u)
        h = ambil_fn(u)
        r = ringkas(h, "daftar acuan PIHPS (lanjutan)")
        r["nama"] = nama_dari_json(_teks(h)) if h["status"] == 200 else []
        hasil.append(r)
        time.sleep(JEDA)
    return hasil


def coba_kabupaten_pihps(ambil_fn=ambil) -> list[dict]:
    """Daftar kabupaten/kota dan pasar PIHPS untuk Provinsi Bengkulu (id 7): mencoba nama parameter yang mungkin dipakai situsnya."""
    dasar = "https://www.bi.go.id/hargapangan/WebSite/TabelHarga"
    hasil = []
    for jalur, nama_param in (("GetRefRegency", ("prov_id", "provinceId", "ProvinceId", "province", "id", "ref_province_id", "idProv", "provid", "ProvId")),
                              ("GetRefMarket", ("regency_id", "regencyId", "RegencyId", "city_id", "id", "ref_regency_id", "idKab", "regid"))):
        for nama in nama_param:
            for tambah in ("", "&price_type_id=1"):
                u = f"{dasar}/{jalur}?{nama}={7 if jalur == 'GetRefRegency' else ''}{tambah}"
                h = ambil_fn(u)
                n = nama_dari_json(_teks(h)) if h["status"] == 200 else []
                if n:
                    hasil.append({"url": u, "status": h["status"], "nama": n})
                time.sleep(JEDA * 0.2)
    return hasil


BAPANAS_V2 = "https://api-panelhargav2.badanpangan.go.id/api"


def coba_bapanas_v2(ambil_fn=ambil) -> list[dict]:
    """Panel Harga Bapanas versi 2: alamat yang dipakai situs publiknya sendiri (ditemukan di JavaScript-nya). Hanya membaca."""
    hasil = []
    for jalur in ("/front/komoditas?level_harga_id=3", "/front/komoditas?level_harga_id=1", "/front/harga-pangan-table-province",
                  "/front/harga-pangan-table-v2", "/front/table-rekapitulasi"):
        h = ambil_fn(BAPANAS_V2 + jalur)
        r = ringkas(h, "Panel Harga Bapanas v2")
        r["nama"] = nama_dari_json(_teks(h)) if h["status"] == 200 else []
        hasil.append(r)
        time.sleep(JEDA)
    return hasil


def penjajakan_lanjutan(ambil_fn=ambil) -> dict:
    halaman = [jelajah_halaman(u, ambil_fn, pola_konteks=POLA_KONTEKS.get(n, [])) | {"nama": n} for n, u in HALAMAN_JELAJAH]
    pihps = next((x["endpoint"] for x in halaman if x["nama"] == "pihps"), [])
    return {"halaman": halaman, "acuan_pihps": coba_daftar_acuan_pihps(ambil_fn, pihps), "kabupaten_pihps": coba_kabupaten_pihps(ambil_fn),
            "bapanas_v2": coba_bapanas_v2(ambil_fn)}


def jalankan(akar: Path, ambil_fn=ambil) -> dict:
    hasil = {"waktu": datetime.now(timezone.utc).isoformat(timespec="seconds"), "pihps": penjajakan_pihps(ambil_fn),
             "bapanas": penjajakan_bapanas(ambil_fn), "lain": penjajakan_lain(ambil_fn),
             "lanjutan": penjajakan_lanjutan(ambil_fn)}
    folder = akar / "data" / "sumber"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "hasil_probe.json").write_text(json.dumps(hasil, ensure_ascii=False, indent=1), encoding="utf-8")
    return hasil

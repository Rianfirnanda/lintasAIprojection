"""Penjajakan lanjutan sumber harga (dijalankan di GitHub Actions; sandbox pengembangan tidak bisa membuka situs resmi).

Lanjutan dari probe_sumber.py. Tujuannya menemukan jalur data yang sungguh bisa diambil otomatis untuk Kabupaten Bengkulu Tengah,
Kepahiang, dan Kota Bengkulu, serta riwayat 5 tahun:
  - SP2KP Kemendag: membaca seluruh potongan JavaScript situsnya untuk mendaftar alamat API (api-sp2kp.kemendag.go.id) dan
    tampilan Tableau Public yang dipakai halaman statistiknya, lalu mencoba alamat yang tampak publik.
  - Panel Harga Bapanas: mencoba lagi dengan batas waktu panjang dan tajuk yang sama dengan situsnya; mendiagnosis apakah
    servernya memang tidak menjawab dari luar Indonesia. Juga data terbuka Bapanas (data.badanpangan.go.id).
  - Portal data terbuka daerah (CKAN) Bengkulu, Bengkulu Tengah, Kepahiang.
  - BPS Web API bila kunci BPS_API_KEY tersedia.
  - PIHPS: ketersediaan riwayat sejak 2020 dan jenis pasar lain (modern, pedagang besar, produsen).
  - Arsip cuaca Open-Meteo 5 tahun.
Tidak ada data yang dikarang: hasilnya apa adanya, ditulis ke data/sumber/hasil_probe_lanjut.json.
"""

from __future__ import annotations

import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
JEDA = 0.8
WILAYAH = ("bengkulu tengah", "kepahiang", "kota bengkulu")


def ambil(url: str, batas_waktu: int = 30, maks_byte: int = 3_000_000, tajuk: dict | None = None, data: bytes | None = None,
          metode: str | None = None) -> dict:
    """Permintaan HTTP apa adanya; tidak pernah melempar galat (galat dicatat sebagai hasil)."""
    h = {"User-Agent": UA, "Accept": "application/json, text/html, */*"}
    h.update(tajuk or {})
    mulai = time.time()
    try:
        req = urllib.request.Request(url, headers=h, data=data, method=metode)
        with urllib.request.urlopen(req, timeout=batas_waktu) as r:
            isi = r.read(maks_byte)
            return {"url": url, "status": r.status, "jenis": r.headers.get("Content-Type", ""), "byte": len(isi),
                    "detik": round(time.time() - mulai, 1), "isi": isi, "tajuk": dict(r.headers)}
    except urllib.error.HTTPError as e:
        isi = b""
        try:
            isi = e.read(20_000)
        except Exception:  # noqa: BLE001
            pass
        return {"url": url, "status": e.code, "jenis": e.headers.get("Content-Type", "") if e.headers else "", "byte": len(isi),
                "detik": round(time.time() - mulai, 1), "isi": isi, "galat": f"HTTP {e.code}",
                "tajuk": dict(e.headers) if e.headers else {}}
    except Exception as e:  # noqa: BLE001
        return {"url": url, "status": 0, "jenis": "", "byte": 0, "detik": round(time.time() - mulai, 1), "isi": b"",
                "galat": f"{e.__class__.__name__}: {e}"[:200], "tajuk": {}}


def teks(h: dict) -> str:
    return h["isi"].decode("utf-8", "replace")


def ringkas(h: dict, catatan: str = "", cuplikan: int = 500) -> dict:
    t = teks(h)
    r = {"url": h["url"], "status": h["status"], "jenis": h["jenis"], "byte": h["byte"], "detik": h["detik"],
         "wilayah_disebut": sorted({w for w in WILAYAH if w in t.lower()}), "cuplikan": re.sub(r"\s+", " ", t)[:cuplikan]}
    cors = {k: v for k, v in (h.get("tajuk") or {}).items() if k.lower().startswith("access-control")}
    if cors:
        r["cors"] = cors
    if h.get("galat"):
        r["galat"] = h["galat"]
    if catatan:
        r["catatan"] = catatan
    try:
        d = json.loads(t)
        r["json"] = True
        r["kunci"] = list(d)[:20] if isinstance(d, dict) else f"daftar {len(d)} item"
    except ValueError:
        r["json"] = False
    return r


def konteks(t: str, pola: re.Pattern, lebar: int = 200, maks: int = 60) -> list[str]:
    hasil, lihat = [], set()
    for m in pola.finditer(t):
        k = m.group(0)
        if k in lihat:
            continue
        lihat.add(k)
        hasil.append(re.sub(r"\s+", " ", t[max(0, m.start() - lebar): m.end() + lebar]))
        if len(hasil) >= maks:
            break
    return hasil


# ---------------------------------------------------------------- SP2KP

SP2KP = "https://sp2kp.kemendag.go.id"
POLA_API_SP2KP = re.compile(r"https://api-sp2kp\.kemendag\.go\.id/[\w\-./{}$]*")
POLA_JALUR = re.compile(r"""["'`](/(?:report|master|public|front|statistik|harga|api)[\w\-./{}$]*)["'`]""")
POLA_TABLEAU = re.compile(r"https://public\.tableau\.com/(?:views|app/profile)/[\w\-./%?=&:]+")
POLA_CHUNK = re.compile(r"""["'(,]\s*["']?(?:\./|/_nuxt/)?([\w\-]{6,}\.js)["']""")


def jelajah_sp2kp(ambil_fn=ambil, maks_chunk: int = 220) -> dict:
    halaman = ["/", "/statistik/area", "/statistik/komoditas", "/statistik", "/harga", "/informasi-harga", "/peta-harga"]
    hasil: dict = {"halaman": [], "chunk": 0, "api": [], "jalur": [], "tableau": [], "konteks": []}
    chunk: list[str] = []
    for p in halaman:
        h = ambil_fn(SP2KP + p)
        hasil["halaman"].append({"jalur": p, "status": h["status"], "byte": h["byte"]})
        if h["status"] == 200:
            t = teks(h)
            chunk += re.findall(r"/_nuxt/([\w\-]+\.js)", t)
            hasil["api"] += POLA_API_SP2KP.findall(t)
            hasil["tableau"] += POLA_TABLEAU.findall(t)
        time.sleep(JEDA)
    dilihat: set[str] = set()
    antrian = list(dict.fromkeys(chunk))
    pola_kon = re.compile(r"api-sp2kp\.kemendag\.go\.id/(?:report|public|front|statistik|harga)[\w\-./]*|average-price|harga-rata|"
                          r"kode_kab|kab_kota|kabupaten_kota|id_kab|kode_provinsi|tableau\.com/views")
    while antrian and len(dilihat) < maks_chunk:
        nama = antrian.pop(0)
        if nama in dilihat:
            continue
        dilihat.add(nama)
        h = ambil_fn(f"{SP2KP}/_nuxt/{nama}", 30, 4_000_000)
        if h["status"] != 200:
            continue
        t = teks(h)
        hasil["api"] += POLA_API_SP2KP.findall(t)
        hasil["jalur"] += POLA_JALUR.findall(t)
        hasil["tableau"] += POLA_TABLEAU.findall(t)
        hasil["konteks"] += [f"[{nama}] {c}" for c in konteks(t, pola_kon, 220, 25)]
        for c in re.findall(r"""["'](?:\./|/_nuxt/)([\w\-]{4,}\.js)["']""", t):
            if c not in dilihat:
                antrian.append(c)
        time.sleep(0.2)
    hasil["chunk"] = len(dilihat)
    hasil["api"] = sorted(set(hasil["api"]))[:300]
    hasil["jalur"] = sorted(set(hasil["jalur"]))[:300]
    hasil["tableau"] = sorted(set(hasil["tableau"]))[:80]
    hasil["konteks"] = hasil["konteks"][:220]
    return hasil


def coba_api_sp2kp(api: list[str], ambil_fn=ambil) -> list[dict]:
    """Mencoba alamat API SP2KP yang tidak berbau login/admin dan tidak berparameter template (hanya membaca, GET)."""
    hindari = re.compile(r"auth|login|logout|token|user|admin|upload|store|update|delete|create|password|otp|intranet", re.I)
    calon = [a.rstrip("/.") for a in api if "{" not in a and "$" not in a and not hindari.search(a)]
    calon += [f"https://api-sp2kp.kemendag.go.id/{p}" for p in (
        "master/api/provinsi", "master/api/kab-kota", "master/api/kabkota", "master/api/komoditas", "master/api/variant",
        "master/api/pasar", "report/api/average-price", "report/api/average-price/public",
        "report/api/average-price/generate-perbandingan-harga", "report/api/average-price/export-area-daily-json")]
    hasil, lihat = [], set()
    for u in calon:
        if u in lihat or len(lihat) >= 70:
            continue
        lihat.add(u)
        h = ambil_fn(u, 30, 400_000, {"Origin": SP2KP, "Referer": SP2KP + "/"})
        hasil.append(ringkas(h, "API SP2KP", 400))
        time.sleep(JEDA)
    return hasil


def coba_tableau(views: list[str], ambil_fn=ambil) -> list[dict]:
    hasil = []
    for v in views[:12]:
        dasar = v.split("?")[0].rstrip("/")
        for u in (dasar + ".csv", dasar + ".csv?:showVizHome=no", dasar + "?:showVizHome=no&:embed=true"):
            h = ambil_fn(u, 40, 600_000)
            hasil.append(ringkas(h, "Tableau Public", 600))
            time.sleep(JEDA)
    return hasil


# ---------------------------------------------------------------- Bapanas

BAPANAS_V2 = "https://api-panelhargav2.badanpangan.go.id/api"


def kunci_bapanas(ambil_fn=ambil) -> tuple[str | None, list[str]]:
    """Kunci x-api-key yang ditanam di JavaScript publik panelharga.badanpangan.go.id (dipakai semua pengunjung situs itu)."""
    h = ambil_fn("https://panelharga.badanpangan.go.id/", 30, 500_000)
    if h["status"] != 200:
        return None, []
    skrip = re.findall(r"""src=["']([^"']*main[\w.\-]*\.js)["']""", teks(h))
    for s in skrip:
        hs = ambil_fn(urllib.parse.urljoin("https://panelharga.badanpangan.go.id/", s), 40, 4_000_000)
        t = teks(hs)
        kunci = re.findall(r'"x-api-key":"([A-Za-z0-9]{20,})"', t)
        jalur = sorted(set(re.findall(r"apiURL\}(/front/[\w\-/]+)", t)))
        if kunci:
            return kunci[0], jalur
    return None, []


def diagnosa_tcp(host: str, port: int = 443, batas: float = 10.0) -> dict:
    hasil: dict = {"host": host}
    try:
        ip = sorted({a[4][0] for a in socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)})
        hasil["ip"] = ip
    except Exception as e:  # noqa: BLE001
        hasil["galat_dns"] = str(e)[:160]
        return hasil
    mulai = time.time()
    try:
        with socket.create_connection((host, port), timeout=batas):
            hasil["tcp"] = f"tersambung {round(time.time() - mulai, 2)} detik"
    except Exception as e:  # noqa: BLE001
        hasil["tcp"] = f"gagal setelah {round(time.time() - mulai, 1)} detik: {e.__class__.__name__}"
    return hasil


def coba_bapanas(ambil_fn=ambil, hari: date | None = None) -> dict:
    hari = hari or date.today()
    kunci, jalur = kunci_bapanas(ambil_fn)
    tajuk = {"Origin": "https://panelharga.badanpangan.go.id", "Referer": "https://panelharga.badanpangan.go.id/"}
    if kunci:
        tajuk["x-api-key"] = kunci
    kemarin = (hari - timedelta(days=1)).isoformat()
    calon = [f"{BAPANAS_V2}/front/komoditas?level_harga_id=3",
             f"{BAPANAS_V2}/front/harga-pangan-informasi?province_id=17&city_id=&level_harga_id=3",
             f"{BAPANAS_V2}/front/harga-pangan-table-province?province_id=17&level_harga_id=3&period_date={kemarin}%20-%20{kemarin}"]
    hasil = {"kunci_ditemukan": bool(kunci), "jalur_front": jalur[:80], "tcp": diagnosa_tcp("api-panelhargav2.badanpangan.go.id"),
             "coba": []}
    for u in calon:
        hasil["coba"].append(ringkas(ambil_fn(u, 60, 400_000, tajuk), "Bapanas v2 (batas waktu 60 detik)", 400))
        time.sleep(JEDA)
    # data terbuka Bapanas: daftar dataset harga
    for u in ("https://data.badanpangan.go.id/datasetpublications", "https://data.badanpangan.go.id/dataset",
              "https://data.badanpangan.go.id/api/3/action/package_search?q=harga&rows=50"):
        h = ambil_fn(u, 40, 2_000_000)
        r = ringkas(h, "Data terbuka Bapanas", 300)
        if h["status"] == 200:
            t = teks(h)
            r["tautan"] = sorted(set(re.findall(r"""href=["']([^"']*(?:harga|price)[^"']*)["']""", t, re.I)))[:60]
            r["unduhan"] = sorted(set(re.findall(r"""href=["']([^"']+\.(?:csv|xlsx|xls|json))["']""", t, re.I)))[:40]
        hasil.setdefault("data_terbuka", []).append(r)
        time.sleep(JEDA)
    return hasil


# ---------------------------------------------------------------- portal daerah, BPS, PIHPS, cuaca

CKAN = ("https://satudata.bengkuluprov.go.id", "https://data.bengkuluprov.go.id", "https://opendata.bengkuluprov.go.id",
        "https://data.bengkulutengahkab.go.id", "https://satudata.bengkulutengahkab.go.id", "https://opendata.bengkulutengahkab.go.id",
        "https://satudata.kepahiangkab.go.id", "https://data.kepahiangkab.go.id", "https://opendata.bengkulukota.go.id",
        "https://satudata.bengkulukota.go.id")


def coba_ckan(ambil_fn=ambil) -> list[dict]:
    hasil = []
    for dasar in CKAN:
        h = ambil_fn(f"{dasar}/api/3/action/package_search?q=harga&rows=30", 25, 1_500_000)
        r = ringkas(h, "CKAN daerah", 200)
        try:
            d = json.loads(teks(h))
            r["dataset"] = [{"nama": p.get("title"), "sumber": [x.get("url") for x in p.get("resources", [])][:5]}
                            for p in d.get("result", {}).get("results", [])][:30]
        except (ValueError, AttributeError):
            pass
        hasil.append(r)
        time.sleep(JEDA)
    return hasil


def coba_bps(ambil_fn=ambil) -> dict:
    kunci = os.environ.get("BPS_API_KEY", "").strip()
    if not kunci:
        return {"status": "kunci BPS_API_KEY belum ada di GitHub Secrets"}
    hasil = {"status": "kunci ada", "coba": []}
    for dom in ("1709", "1708", "1771", "1700"):
        u = f"https://webapi.bps.go.id/v1/api/list/model/var/domain/{dom}/key/{kunci}/keyword/harga"
        h = ambil_fn(u, 40, 1_000_000)
        r = ringkas(h, f"BPS domain {dom}", 300)
        r["url"] = r["url"].replace(kunci, "***")
        try:
            d = json.loads(teks(h))
            isi = d.get("data", [None, []])
            r["variabel"] = [{"var_id": x.get("var_id"), "judul": x.get("title")} for x in (isi[1] if len(isi) > 1 else [])][:40]
        except (ValueError, AttributeError, TypeError):
            pass
        hasil["coba"].append(r)
        time.sleep(JEDA)
    return hasil


PIHPS = "https://www.bi.go.id/hargapangan/WebSite/TabelHarga/GetGridDataDaerah"


def coba_pihps(ambil_fn=ambil) -> list[dict]:
    """Riwayat PIHPS Provinsi Bengkulu per tahun (2019-2021) dan jenis pasar lain untuk 7 hari terakhir."""
    hasil = []
    uji = [(1, "2019-10-01", "2019-10-10"), (1, "2020-10-01", "2020-10-10"), (1, "2021-10-01", "2021-10-10"),
           (2, None, None), (3, None, None), (4, None, None)]
    hari = date.today()
    for jenis, a, b in uji:
        a = a or (hari - timedelta(days=7)).isoformat()
        b = b or hari.isoformat()
        q = {"price_type_id": jenis, "comcat_id": "", "province_id": 7, "regency_id": "", "market_id": "", "tipe_laporan": 1,
             "start_date": a, "end_date": b}
        h = ambil_fn(f"{PIHPS}?{urllib.parse.urlencode(q)}", 40, 1_000_000)
        r = ringkas(h, f"PIHPS jenis pasar {jenis} {a}..{b}", 200)
        try:
            baris = [x for x in (json.loads(teks(h)).get("data") or []) if x.get("level") == 2]
            r["varian"] = len(baris)
            r["terisi"] = sum(1 for x in baris for k, v in x.items() if re.fullmatch(r"\d{2}/\d{2}/\d{4}", k) and str(v).strip() not in ("", "-", "0"))
            r["nama"] = [x.get("name") for x in baris][:30]
        except (ValueError, AttributeError):
            pass
        hasil.append(r)
        time.sleep(JEDA * 2)
    return hasil


def coba_lain(ambil_fn=ambil) -> list[dict]:
    calon = [
        ("https://archive-api.open-meteo.com/v1/archive?latitude=-3.73&longitude=102.43&start_date=2021-10-01&end_date=2021-10-03"
         "&daily=precipitation_sum,temperature_2m_mean&timezone=Asia%2FJakarta", "Open-Meteo arsip 2021"),
        ("https://sisp.kemendag.go.id/", "SISP Kemendag"),
        ("https://bengkulutengahkab.bps.go.id/id/statistics-table?subject=525", "BPS Bengkulu Tengah tabel harga"),
        ("https://bengkulutengahkab.bps.go.id/", "BPS Bengkulu Tengah"),
        ("https://kepahiangkab.bps.go.id/", "BPS Kepahiang"),
        ("https://bengkulu.bps.go.id/", "BPS Provinsi Bengkulu"),
        ("https://disperindag.bengkuluprov.go.id/", "Disperindag Provinsi Bengkulu"),
        ("https://bengkulutengahkab.go.id/", "Pemkab Bengkulu Tengah"),
        ("https://kepahiangkab.go.id/", "Pemkab Kepahiang"),
        ("https://ews.kemendag.go.id/", "EWS Kemendag"),
    ]
    out = []
    for u, c in calon:
        h = ambil_fn(u, 30, 1_500_000)
        r = ringkas(h, c, 300)
        if h["status"] == 200 and "html" in (h["jenis"] or "").lower():
            r["tautan_harga"] = sorted(set(re.findall(r"""href=["']([^"']*(?:harga|pangan|bapok|sembako|inflasi)[^"']*)["']""", teks(h), re.I)))[:30]
        out.append(r)
        time.sleep(JEDA)
    return out


def jalankan(akar: Path, ambil_fn=ambil) -> dict:
    sp = jelajah_sp2kp(ambil_fn)
    hasil = {"waktu": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sp2kp": sp,
             "sp2kp_coba": coba_api_sp2kp(sp["api"], ambil_fn), "tableau": coba_tableau(sp["tableau"], ambil_fn),
             "bapanas": coba_bapanas(ambil_fn), "ckan": coba_ckan(ambil_fn), "bps": coba_bps(ambil_fn),
             "pihps": coba_pihps(ambil_fn), "lain": coba_lain(ambil_fn)}
    folder = akar / "data" / "sumber"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "hasil_probe_lanjut.json").write_text(json.dumps(hasil, ensure_ascii=False, indent=1), encoding="utf-8")
    return hasil

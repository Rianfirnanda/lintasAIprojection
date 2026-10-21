"""BPS Web API (webapi.bps.go.id): uji kunci dan petakan data yang tersedia untuk wilayah kerja.

Kunci BPS_API_KEY diisi Administrator di Pengaturan situs (tersimpan di Firestore) atau sebagai GitHub Secret. BPS
meminta kunci di dalam alamat URL, jadi semua teks yang dicetak atau disimpan dilewatkan `samarkan` dulu dan hasil di
data/sumber/hasil_bps.json tidak pernah memuat kunci. Dijalankan di GitHub Actions, karena mesin pengembangan
diblokir pelindung situs BPS.

Yang dicek: (1) kunci diterima BPS (daftar kabupaten/kota di Provinsi Bengkulu), (2) variabel dan tabel statis yang
memuat harga, inflasi, atau nama komoditas pangan untuk Bengkulu Tengah, Provinsi Bengkulu, dan Kota Bengkulu, dan
(3) contoh angka dari beberapa variabel teratas, supaya jelas datanya benar-benar bisa ditarik, bukan hanya judulnya.
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from .probe_lanjut import ambil, teks

DASAR = "https://webapi.bps.go.id/v1/api"
WILAYAH = {"1709": "Kabupaten Bengkulu Tengah", "1700": "Provinsi Bengkulu", "1771": "Kota Bengkulu"}
KATA_VARIABEL = ("harga", "inflasi", "indeks harga", "beras", "cabai", "bawang", "minyak goreng", "gula", "daging", "telur")
KATA_TABEL = ("harga", "inflasi")
MAKS_HALAMAN = 3
MAKS_CONTOH = 6
JEDA = 0.5
BERKAS = Path("data/sumber/hasil_bps.json")
# Variabel yang paling berguna untuk dashboard ini diambil contohnya lebih dulu.
PRIORITAS = ("inflasi", "indeks harga konsumen", "harga eceran", "harga produsen", "nilai tukar petani", "harga")
# Judul yang cocok dengan kata "harga" hanya karena istilah "atas dasar harga berlaku/konstan": bukan data harga.
BUKAN_HARGA = ("produk domestik regional bruto", "pdrb", "input-output", "input output")


def samarkan(isi, kunci: str) -> str:
    """Hilangkan kunci dari teks apa pun (pesan galat, alamat URL) sebelum dicetak atau disimpan."""
    s = str(isi)
    return s.replace(kunci, "***") if kunci else s


def _url(jalur: str, kunci: str) -> str:
    return f"{DASAR}/{jalur.strip('/')}/key/{kunci}/"


def minta(jalur: str, kunci: str, ambil_fn=ambil) -> tuple[dict | None, str | None]:
    """(isi JSON, galat). Galat sudah disamarkan dan ditulis dengan bahasa yang mudah dipahami."""
    h = ambil_fn(_url(jalur, kunci), 40, 3_000_000)
    isi = teks(h).lstrip()
    if h.get("status") != 200:
        rinci = ""
        if isi.startswith("{"):
            try:
                rinci = str(json.loads(isi).get("message") or "")
            except ValueError:
                rinci = ""
        elif isi.startswith("<"):
            rinci = "jawaban berupa halaman web (kemungkinan diblokir pelindung situs BPS)"
        dasar = h.get("galat") or f"HTTP {h.get('status')}"
        return None, samarkan(f"{dasar}{': ' + rinci if rinci else ''}", kunci)[:300]
    if isi.startswith("<"):
        return None, "jawaban berupa halaman web, bukan data (kemungkinan diblokir pelindung situs BPS)"
    try:
        d = json.loads(isi)
    except ValueError:
        return None, "jawaban bukan JSON"
    if str(d.get("status", "")).upper() != "OK":
        return None, samarkan(d.get("message") or d.get("status") or "ditolak BPS", kunci)[:300]
    return d, None


def daftar(d: dict | None) -> tuple[dict, list]:
    """Bentuk jawaban daftar BPS: data = [info halaman, [isi]]. Data kosong dianggap daftar kosong."""
    data = (d or {}).get("data")
    if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
        return (data[0] if isinstance(data[0], dict) else {}), data[1]
    return {}, []


def _semua_halaman(jalur: str, kunci: str, ambil_fn, tidur) -> tuple[list, str | None]:
    isi_semua: list = []
    for hal in range(1, MAKS_HALAMAN + 1):
        d, g = minta(f"{jalur}/page/{hal}", kunci, ambil_fn)
        if g:
            return isi_semua, g
        info, isi = daftar(d)
        isi_semua += isi
        if hal >= int(info.get("pages") or 1):
            break
        tidur(JEDA)
    return isi_semua, None


def _cocok(x: dict, kata: str, *kolom: str) -> bool:
    """Semua kata pencarian ada di judul atau subjeknya (penyaring kedua, bila BPS mengabaikan parameter kata kunci), dan
    bukan PDRB atau tabel input-output yang hanya memuat istilah "atas dasar harga"."""
    isi = " ".join(str(x.get(k) or "") for k in kolom).lower()
    return all(k in isi for k in kata.lower().split()) and not any(b in isi for b in BUKAN_HARGA)


def _skor(judul: str) -> int:
    j = judul.lower()
    return next((len(PRIORITAS) - i for i, kata in enumerate(PRIORITAS) if kata in j), 0)


def _label(daftar_label) -> list[tuple[str, str]]:
    return [(str(x.get("val")), str(x.get("label") or "").strip()) for x in (daftar_label or []) if isinstance(x, dict)]


def uraikan_data(d: dict, var_id) -> list[dict]:
    """Ubah datacontent BPS menjadi baris berlabel. Kunci datacontent BPS = kode vervar + var + turvar + tahun + turtahun."""
    isi = d.get("datacontent") or {}
    if not isinstance(isi, dict):
        return []
    vervar = _label(d.get("vervar")) or [("", "")]
    turvar = _label(d.get("turvar")) or [("0", "")]
    tahun = _label(d.get("tahun"))
    turtahun = _label(d.get("turtahun")) or [("0", "")]
    baris = []
    for (v, vl) in vervar:
        for (tv, tvl) in turvar:
            for (th, thl) in tahun:
                for (tt, ttl) in turtahun:
                    k = f"{v}{var_id}{tv}{th}{tt}"
                    if k in isi and isi[k] not in (None, ""):
                        baris.append({"rincian": vl, "turunan": tvl, "tahun": thl, "periode": ttl,
                                      "urut": (int(th) if th.isdigit() else 0, int(tt) if tt.isdigit() else 0), "nilai": isi[k]})
    return baris


def _contoh_data(wilayah: str, var_id, kunci: str, ambil_fn) -> dict:
    """Tarik angka dua tahun terakhir satu variabel (BPS mewajibkan parameter tahun) dan tampilkan contoh terbarunya."""
    d, g = minta(f"list/model/th/lang/ind/domain/{wilayah}/var/{var_id}", kunci, ambil_fn)
    if g:
        return {"bisa_diambil": False, "galat": f"daftar tahun: {g}"}
    _, th = daftar(d)
    th = sorted((x for x in th if isinstance(x, dict) and str(x.get("th_id", "")).isdigit()), key=lambda x: int(x["th_id"]))
    if not th:
        return {"bisa_diambil": False, "galat": "BPS tidak mencantumkan tahun untuk variabel ini"}
    pilih = th[-2:]
    d, g = minta(f"list/model/data/lang/ind/domain/{wilayah}/var/{var_id}/th/{';'.join(str(x['th_id']) for x in pilih)}",
                 kunci, ambil_fn)
    if g:
        return {"bisa_diambil": False, "galat": g, "tahun": [str(x.get("th")) for x in pilih]}
    baris = uraikan_data(d, var_id)
    if not baris:
        return {"bisa_diambil": False, "galat": "variabel ada, tetapi angkanya kosong", "tahun": [str(x.get("th")) for x in pilih]}
    terbaru = max(b["urut"] for b in baris)
    contoh = [{k: b[k] for k in ("rincian", "turunan", "tahun", "periode", "nilai")} for b in baris if b["urut"] == terbaru][:8]
    return {"bisa_diambil": True, "jumlah_angka": len(baris), "tahun": [str(x.get("th")) for x in pilih],
            "terbaru": f"{contoh[0]['periode']} {contoh[0]['tahun']}".strip(), "contoh": contoh}


def cek(kunci: str, ambil_fn=ambil, tidur=time.sleep, sekarang=None) -> dict:
    """Uji kunci dan petakan data BPS untuk wilayah kerja. Tidak pernah melempar galat dan tidak memuat kunci."""
    kunci = (kunci or "").strip()
    waktu = (sekarang or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    hasil = {"waktu": waktu, "kunci": "ada" if kunci else "belum", "kunci_sah": None, "pesan": "", "wilayah": {},
             "domain_bengkulu": [], "variabel": [], "tabel_statis": [], "contoh_data": [], "galat": []}
    if not kunci:
        hasil["pesan"] = ("Kunci BPS_API_KEY belum diisi. Isi di Pengaturan situs (Kunci sumber data) atau sebagai "
                          "GitHub Secret, lalu jalankan cek ini lagi.")
        return hasil

    d, g = minta("domain/type/kabbyprov/prov/17", kunci, ambil_fn)
    if g:
        hasil["kunci_sah"] = False
        hasil["pesan"] = f"Kunci belum bisa dipakai: {g}"
        return hasil
    hasil["kunci_sah"] = True
    _, dom = daftar(d)
    hasil["domain_bengkulu"] = [{"id": str(x.get("domain_id")), "nama": x.get("domain_name")} for x in dom if isinstance(x, dict)]

    terlihat = set()
    for kode, nama in WILAYAH.items():
        ringkas = {"nama": nama, "variabel": 0, "tabel_statis": 0}
        for kata in KATA_VARIABEL:
            tidur(JEDA)
            isi, g = _semua_halaman(f"list/model/var/lang/ind/domain/{kode}/keyword/{urllib.parse.quote(kata)}",
                                    kunci, ambil_fn, tidur)
            if g:
                hasil["galat"].append(f"{nama}, variabel '{kata}': {g}")
            for x in isi:
                if not isinstance(x, dict) or (kode, x.get("var_id")) in terlihat or not _cocok(x, kata, "title", "sub_name"):
                    continue
                terlihat.add((kode, x.get("var_id")))
                ringkas["variabel"] += 1
                hasil["variabel"].append({"wilayah": kode, "var_id": x.get("var_id"), "judul": x.get("title"),
                                          "subjek": x.get("sub_name"), "satuan": x.get("unit"), "kata": kata})
        for kata in KATA_TABEL:
            tidur(JEDA)
            isi, g = _semua_halaman(f"list/model/statictable/lang/ind/domain/{kode}/keyword/{urllib.parse.quote(kata)}",
                                    kunci, ambil_fn, tidur)
            if g:
                hasil["galat"].append(f"{nama}, tabel '{kata}': {g}")
            for x in isi:
                if not isinstance(x, dict) or (kode, "tabel", x.get("table_id")) in terlihat or not _cocok(x, kata, "title"):
                    continue
                terlihat.add((kode, "tabel", x.get("table_id")))
                ringkas["tabel_statis"] += 1
                hasil["tabel_statis"].append({"wilayah": kode, "table_id": x.get("table_id"), "judul": x.get("title"),
                                              "diperbarui": x.get("updt_date")})
        hasil["wilayah"][kode] = ringkas

    calon = sorted(hasil["variabel"], key=lambda v: (-_skor(str(v.get("judul") or "")), v["wilayah"] != "1709"))
    for v in calon[:MAKS_CONTOH]:
        tidur(JEDA)
        hasil["contoh_data"].append({"wilayah": v["wilayah"], "var_id": v["var_id"], "judul": v["judul"],
                                     **_contoh_data(v["wilayah"], v["var_id"], kunci, ambil_fn)})

    n_var, n_tab = len(hasil["variabel"]), len(hasil["tabel_statis"])
    bisa = sum(1 for c in hasil["contoh_data"] if c.get("bisa_diambil"))
    hasil["pesan"] = (f"Kunci diterima BPS. Ditemukan {n_var} variabel dan {n_tab} tabel statis tentang harga, inflasi, atau "
                      f"komoditas pangan; {bisa} dari {len(hasil['contoh_data'])} contoh variabel berhasil diambil angkanya.")
    return hasil


def simpan(akar: Path, hasil: dict, berkas: Path = BERKAS) -> Path:
    path = akar / berkas
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hasil, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def baca(akar: Path, berkas: Path = BERKAS) -> dict | None:
    path = akar / berkas
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except ValueError:
        return None


# ---------------------------------------------------------------- deret inflasi untuk dashboard

# Bengkulu Tengah belum termasuk kota penghitung IHK, jadi TPID memakai angka Provinsi Bengkulu dan kota IHK di
# provinsi ini (Kota Bengkulu dan Mukomuko) sebagai acuan. Semua deret IHK tahun dasar 2022=100.
SERI = (
    ("mtm", "1700", 555, "Inflasi bulanan (m-to-m) menurut kelompok pengeluaran"),
    ("ytd", "1700", 556, "Inflasi tahun kalender (y-to-d) menurut kelompok pengeluaran"),
    ("yoy", "1700", 557, "Inflasi tahunan (y-on-y) menurut kelompok pengeluaran"),
    ("mtm_wilayah", "1700", 559, "Inflasi bulanan (m-to-m) menurut kabupaten/kota IHK"),
    ("yoy_wilayah", "1700", 560, "Inflasi tahunan (y-on-y) menurut kabupaten/kota IHK"),
    ("it", "1700", 421, "Indeks harga yang diterima petani (It)"),
    ("ib", "1700", 422, "Indeks harga yang dibayar petani (Ib)"),
)
TAHUN_SERI = 3
BERKAS_SERI = Path("data/sumber/bps_seri.json")
BULAN = ("januari", "februari", "maret", "april", "mei", "juni", "juli", "agustus", "september", "oktober", "november",
         "desember")
TANPA_RINCIAN = ("", "-", "tidak ada", "tidak ada turunan variabel")


def _no_bulan(label) -> int | None:
    s = str(label or "").strip().lower()
    return BULAN.index(s) + 1 if s in BULAN else None


def baris_bulanan(baris: list[dict]) -> list[dict]:
    """Baris hasil `uraikan_data` menjadi {periode YYYY-MM, kategori, nilai}. Tabel BPS versi baru menaruh bulan di
    turunan tahun (kategori di rincian); versi lama menaruh bulan di rincian (kategori di turunan). Baris tahunan dan
    angka yang bukan bilangan dilewati."""
    hasil = []
    for b in baris:
        turunan = str(b.get("turunan") or "").strip()
        bulan = _no_bulan(b.get("periode"))
        if bulan:
            kategori = str(b.get("rincian") or "").strip()
            if turunan.lower() not in TANPA_RINCIAN:
                kategori = f"{kategori}, {turunan}" if kategori else turunan
        else:
            bulan = _no_bulan(b.get("rincian"))
            kategori = "" if turunan.lower() in TANPA_RINCIAN else turunan
        tahun = str(b.get("tahun") or "").strip()
        try:
            nilai = round(float(b.get("nilai")), 2)
        except (TypeError, ValueError):
            continue
        if bulan and tahun.isdigit():
            hasil.append({"periode": f"{tahun}-{bulan:02d}", "kategori": kategori or "Umum", "nilai": nilai})
    return sorted(hasil, key=lambda x: (x["periode"], x["kategori"]))


def _tahun_terakhir(d: dict | None, n: int) -> list[dict]:
    _, th = daftar(d)
    th = [x for x in th if isinstance(x, dict) and str(x.get("th_id", "")).isdigit()]
    # Urut menurut tahunnya, bukan nomor th_id: nomor BPS tidak selalu searah dengan tahun.
    th.sort(key=lambda x: (int(x["th"]) if str(x.get("th", "")).isdigit() else 0, int(x["th_id"])))
    return th[-n:]


def _satu_seri(wilayah: str, var_id: int, kunci: str, ambil_fn, tidur) -> tuple[dict | None, list, str | None, bool]:
    """(keterangan variabel, baris bulanan, galat, ditolak). `ditolak` berarti permintaannya sendiri gagal (kunci salah,
    diblokir, situs bermasalah), bukan sekadar variabelnya kosong."""
    d, g = minta(f"list/model/th/lang/ind/domain/{wilayah}/var/{var_id}", kunci, ambil_fn)
    if g:
        return None, [], g, True
    th = _tahun_terakhir(d, TAHUN_SERI)
    if not th:
        return None, [], "BPS tidak mencantumkan tahun untuk variabel ini", False
    # BPS membatasi parameter tahun paling banyak 2 tahun per permintaan. Pasangan tahun terbaru diminta lebih dulu;
    # bila tahun yang lebih lama gagal, angka terbaru tetap dipakai (trennya saja yang lebih pendek).
    info, data = {}, []
    for j in range(len(th), 0, -2):
        bagian = th[max(0, j - 2):j]
        tidur(JEDA)
        d, g = minta(f"list/model/data/lang/ind/domain/{wilayah}/var/{var_id}/th/{';'.join(str(x['th_id']) for x in bagian)}",
                     kunci, ambil_fn)
        if g:
            if data:
                break
            return None, [], g, True
        data += baris_bulanan(uraikan_data(d, var_id))
        v = d.get("var")
        info = info or (v[0] if isinstance(v, list) and v and isinstance(v[0], dict) else {})
    if not data:
        return None, [], "angka bulanan kosong", False
    return info, sorted(data, key=lambda x: (x["periode"], x["kategori"])), None, False


def _angka_setelah(t: str, penanda: str) -> float | None:
    """Angka "sebesar X persen" pertama sesudah penanda terakhir (mis. y-on-y), supaya angka bulanan di kalimat yang
    sama tidak terbaca sebagai angka tahunan."""
    letak = [m.end() for m in re.finditer(penanda, t)]
    m = re.search(r"sebesar\s+(-?\d+(?:[.,]\d+)?)\s*persen", t[letak[-1]:]) if letak else None
    return float(m.group(1).replace(",", ".")) if m else None


def baca_rilis(judul: str, abstrak: str = "") -> dict | None:
    """Angka inflasi Provinsi Bengkulu dari judul (dan ringkasan) Berita Resmi Statistik, mis. "Inflasi Year-on-Year
    (y-on-y) Provinsi Bengkulu Juni 2026 sebesar 3,96 persen". Rilis lain (NTP, kota saja, ekspor) dilewati."""
    t = " ".join(str(judul or "").lower().split())
    a = " ".join(re.sub(r"<[^>]+>", " ", html.unescape(str(abstrak or ""))).lower().split())
    tahunan = r"y-on-y|year[- ]on[- ]year"
    if "provinsi bengkulu" not in t or not re.search(tahunan, t):
        return None
    b = re.search(rf"\b({'|'.join(BULAN)})\s+(\d{{4}})\b", t)
    yoy = _angka_setelah(t, tahunan)
    if not b or yoy is None:
        return None
    deflasi = "deflasi" in t and "inflasi" not in t.replace("deflasi", "")
    mtm = _angka_setelah(a, r"m-to-m|month[- ]to[- ]month")
    return {"periode": f"{b.group(2)}-{BULAN.index(b.group(1)) + 1:02d}", "yoy": -abs(yoy) if deflasi else yoy,
            "mtm": mtm, "judul": " ".join(str(judul).split())}


def ambil_rilis(kunci: str, ambil_fn=ambil, maks: int = 6) -> tuple[list[dict], list[str], str | None]:
    """Berita Resmi Statistik inflasi Provinsi Bengkulu terbaru: (rilis terbaca, judul yang dilewati, galat). Rilis ini
    terbit awal bulan, biasanya beberapa bulan lebih cepat daripada tabel dinamis Web API, jadi angka utamanya dipakai
    sebagai angka resmi terbaru."""
    d, g = minta("list/model/pressrelease/lang/ind/domain/1700/keyword/inflasi/page/1", kunci, ambil_fn)
    if g:
        return [], [], g
    hasil, lewat = {}, []
    for x in daftar(d)[1]:
        if not isinstance(x, dict):
            continue
        r = baca_rilis(x.get("title"), x.get("abstract"))
        if not r:
            lewat.append(" ".join(str(x.get("title") or "").split())[:200])
            continue
        if r["periode"] in hasil:
            continue
        url = str(x.get("pdf") or "")
        r["tanggal"] = str(x.get("rl_date") or "")[:10] or None
        r["url"] = url if re.match(r"^https://([a-z0-9-]+\.)*bps\.go\.id/", url) else None
        hasil[r["periode"]] = r
    return [hasil[p] for p in sorted(hasil, reverse=True)[:maks]], lewat[:10], None


def ambil_seri(kunci: str, ambil_fn=ambil, tidur=time.sleep, sekarang=None) -> dict:
    """Tarik deret inflasi Provinsi Bengkulu (SERI) untuk tiga tahun terakhir. Tidak pernah melempar galat dan tidak
    memuat kunci. Bila permintaan pertama sudah ditolak (kunci salah, diblokir), deret lain tidak dicoba."""
    kunci = (kunci or "").strip()
    waktu = (sekarang or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    hasil = {"waktu": waktu, "sumber": "BPS Web API (webapi.bps.go.id)", "kunci": "ada" if kunci else "belum",
             "seri": {}, "galat": []}
    if not kunci:
        hasil["pesan"] = "Kunci BPS_API_KEY belum diisi. Isi di Pengaturan situs (Kunci sumber data) atau sebagai GitHub Secret."
        return hasil
    for i, (kode, wilayah, var_id, judul) in enumerate(SERI):
        tidur(JEDA)
        info, data, g, ditolak = _satu_seri(wilayah, var_id, kunci, ambil_fn, tidur)
        if g:
            hasil["galat"].append(samarkan(f"{judul} (var {var_id}): {g}", kunci))
            if ditolak and i == 0:
                break  # permintaan pertama sudah ditolak: deret lain pasti bernasib sama
            continue
        hasil["seri"][kode] = {"wilayah": wilayah, "nama_wilayah": WILAYAH.get(wilayah, wilayah), "var_id": var_id,
                               "judul": judul, "judul_bps": str(info.get("label") or "").strip() or None,
                               "satuan": str(info.get("unit") or "").strip() or None, "diambil": waktu,
                               "terbaru": data[-1]["periode"], "data": data}
    if hasil["seri"]:
        tidur(JEDA)
        rilis, lewat, g = ambil_rilis(kunci, ambil_fn)
        if g:
            hasil["galat"].append(samarkan(f"Berita Resmi Statistik inflasi: {g}", kunci))
        hasil["rilis"], hasil["rilis_dilewati"] = rilis, lewat
    n = len(hasil["seri"])
    terbaru = max((s["terbaru"] for s in hasil["seri"].values()), default=None)
    hasil["pesan"] = (f"{n} dari {len(SERI)} deret BPS berhasil diambil" + (f", data terbaru {terbaru}." if terbaru else ".")
                      if n else "Deret BPS belum bisa diambil: " + (hasil["galat"][0] if hasil["galat"] else "tanpa keterangan"))
    return hasil


def gabung_seri(lama: dict | None, baru: dict) -> dict:
    """Deret yang gagal diambil kali ini tetap memakai hasil sebelumnya (dengan tanggal ambilnya sendiri), supaya
    dashboard tidak kosong hanya karena satu permintaan gagal."""
    seri = {**((lama or {}).get("seri") or {}), **baru.get("seri", {})}
    return {**baru, "seri": {k: seri[k] for k, *_ in SERI if k in seri},
            "rilis": baru.get("rilis") or (lama or {}).get("rilis") or []}


def ringkas_untuk_situs(d: dict | None, bulan_tren: int = 25) -> dict | None:
    """Ringkasan kecil untuk ringkasan.json: angka bulan terbaru per kelompok dan per kota IHK, serta tren tahunan."""
    seri = (d or {}).get("seri") or {}
    if not any(k in seri for k in ("mtm", "yoy")):
        return None

    def per_periode(kode: str) -> dict[str, dict[str, float]]:
        hasil: dict[str, dict[str, float]] = {}
        for x in (seri.get(kode) or {}).get("data", []):
            hasil.setdefault(x["periode"], {})[x["kategori"]] = x["nilai"]
        return hasil

    mtm, ytd, yoy = per_periode("mtm"), per_periode("ytd"), per_periode("yoy")
    periode = max((p for p in (*mtm, *yoy) if "Umum" in mtm.get(p, {}) or "Umum" in yoy.get(p, {})), default=None)
    if not periode:
        return None
    nama = list(dict.fromkeys([*mtm.get(periode, {}), *yoy.get(periode, {}), *ytd.get(periode, {})]))
    kelompok = [{"nama": k, "mtm": mtm.get(periode, {}).get(k), "ytd": ytd.get(periode, {}).get(k),
                 "yoy": yoy.get(periode, {}).get(k)} for k in nama]
    umum = next((k for k in kelompok if k["nama"] == "Umum"), None)
    makanan = next((k for k in kelompok if k["nama"].lower().startswith("makanan")), None)

    w_mtm, w_yoy = per_periode("mtm_wilayah"), per_periode("yoy_wilayah")
    p_wil = max((*w_mtm, *w_yoy), default=None)
    wilayah = [{"nama": k, "mtm": w_mtm.get(p_wil, {}).get(k), "yoy": w_yoy.get(p_wil, {}).get(k)}
               for k in dict.fromkeys([*w_mtm.get(p_wil, {}), *w_yoy.get(p_wil, {})])] if p_wil else []

    semua = sorted({*mtm, *yoy})[-bulan_tren:]
    tren = [{"periode": p, "mtm": mtm.get(p, {}).get("Umum"), "yoy": yoy.get(p, {}).get("Umum"),
             "yoy_makanan": yoy.get(p, {}).get(makanan["nama"]) if makanan else None} for p in semua]

    # Nilai Tukar Petani = It / Ib x 100 untuk bulan yang punya keduanya (kategori yang sama, mis. subsektor gabungan).
    it, ib = per_periode("it"), per_periode("ib")
    ntp = None
    for p in sorted(set(it) & set(ib), reverse=True):
        sama = [k for k in it[p] if k in ib[p] and ib[p][k]]
        if sama:
            utama = next((k for k in sama if "gabungan" in k.lower() or k == "Umum"), None)
            ntp = {"periode": p, "subsektor": [{"nama": k, "it": it[p][k], "ib": ib[p][k],
                                                "ntp": round(it[p][k] / ib[p][k] * 100, 2)} for k in sama],
                   "utama": utama}
            break

    ambil = [s.get("diambil") for s in seri.values() if s.get("diambil")]
    return {"sumber": "BPS Web API", "wilayah": "Provinsi Bengkulu", "periode": periode,
            "diambil": min(ambil)[:10] if ambil else str((d or {}).get("waktu", ""))[:10] or None,
            "umum": umum, "makanan": makanan, "kelompok": kelompok,
            "wilayah_ihk": {"periode": p_wil, "daftar": wilayah} if wilayah else None,
            "tren": tren, "ntp": ntp}

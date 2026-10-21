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

import json
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
PRIORITAS = ("inflasi", "indeks harga konsumen", "harga eceran", "harga produsen", "harga")


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
    """Semua kata pencarian ada di judul atau subjeknya. Penyaring kedua, bila BPS mengabaikan parameter kata kunci."""
    isi = " ".join(str(x.get(k) or "") for k in kolom).lower()
    return all(k in isi for k in kata.lower().split())


def _skor(judul: str) -> int:
    j = judul.lower()
    return next((len(PRIORITAS) - i for i, kata in enumerate(PRIORITAS) if kata in j), 0)


def _contoh_data(wilayah: str, var_id, kunci: str, ambil_fn) -> dict:
    """Ringkas angka satu variabel: berapa angka, tahun yang tersedia, dan satu contoh terbaru."""
    d, g = minta(f"list/model/data/lang/ind/domain/{wilayah}/var/{var_id}", kunci, ambil_fn)
    if g:
        return {"bisa_diambil": False, "galat": g}
    isi = d.get("datacontent") or {}
    tahun = [str(t.get("label")) for t in (d.get("tahun") or []) if isinstance(t, dict) and t.get("label")]
    if not isi:
        return {"bisa_diambil": False, "galat": "variabel ada, tetapi angkanya kosong", "tahun": tahun[-5:]}
    kunci_terakhir = sorted(isi)[-1]
    return {"bisa_diambil": True, "jumlah_angka": len(isi), "tahun": tahun[-5:], "contoh_kode": kunci_terakhir,
            "contoh_nilai": isi[kunci_terakhir]}


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


def simpan(akar: Path, hasil: dict) -> Path:
    path = akar / BERKAS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hasil, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return path


def baca(akar: Path) -> dict | None:
    path = akar / BERKAS
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except ValueError:
        return None

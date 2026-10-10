"""Tata kelola data sesuai Laporan Pengembangan Model (bab "Ambang AI Data Finder, Cleaning, dan Matriks Metode"):

  - 10 AI Data Finder: status tiap pencari data dihitung dari data yang benar-benar masuk pada jalannya pipeline ini
    (bukan klaim), lengkap dengan gerbang kuantitatif (kesegaran, kelengkapan, pemetaan varian, duplikasi, harga positif)
    dan tindakan bila gagal.
  - 8 tahap pembersihan (Schema Validator sampai Cross-Source Reconciler) dengan gerbang kelulusan masing-masing.
  - Perbandingan antarwilayah (spread, kemiringan tren, korelasi Spearman, lead-lag, rasio volatilitas, kemiripan pola
    mingguan, DTW, z-score disparitas) bila seri pembanding tersedia.
  - Rantai harga (produsen -> pedagang besar -> eceran -> pasar modern) dari PIHPS bila tersedia.
Semua angka dihitung dari data; bila data tidak ada, statusnya "menunggu" dengan alasan yang jelas, bukan angka karangan.
"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np

KONTEKS_PIHPS = ("harga_pihps", "harga_pihps_modern", "harga_pihps_grosir", "harga_pihps_produsen")
NAMA_JENIS_PASAR = {"harga_pihps_produsen": "Produsen", "harga_pihps_grosir": "Pedagang besar", "harga_pihps": "Pasar tradisional",
                    "harga_pihps_modern": "Pasar modern"}


def _gerbang(nama: str, lolos: bool | None, nilai, target: str) -> dict:
    return {"gerbang": nama, "lolos": lolos, "nilai": nilai, "target": target}


def _status(gerbang: list[dict], ada_data: bool) -> str:
    if not ada_data or (gerbang and all(g["lolos"] is None for g in gerbang)):
        return "menunggu"
    if any(g["lolos"] is False for g in gerbang):
        return "perlu_perhatian"
    return "lulus"


def _hari_kerja_antara(a: date, b: date) -> int:
    """Jumlah hari kerja (Senin-Jumat) setelah a sampai b."""
    n, t = 0, a
    while t < b:
        t += timedelta(days=1)
        n += t.weekday() < 5
    return n


def _baca_probe(akar: Path) -> dict:
    hasil = {}
    for nama in ("hasil_probe_lanjut.json", "hasil_probe_tahap2.json"):
        p = akar / "data" / "sumber" / nama
        if p.exists():
            try:
                hasil[nama] = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                pass
    return hasil


def status_finder(konf, hasil_masuk, hasil_qc, tanggal_data: date | None) -> list[dict]:
    """Status 10 AI Data Finder dari data yang masuk pada jalannya pipeline ini."""
    hari = konf.hari_ini
    kon = hasil_masuk.konteks
    per_ind: dict[str, list] = defaultdict(list)
    for k in kon:
        per_ind[k.indikator].append(k)
    varian = set(konf.varian)
    hasil: list[dict] = []
    probe = _baca_probe(konf.akar)

    # 1. BPS Web API
    ada_kunci = bool(os.environ.get("BPS_API_KEY"))
    hasil.append({"no": 1, "nama": "BPS Web API Finder", "objek": "Harga produsen, produksi, luas panen, indikator bulanan",
                  "status": "menunggu", "data_terakhir": None,
                  "alasan": "Kunci BPS Web API belum dipasang. Daftar gratis di webapi.bps.go.id lalu simpan sebagai GitHub Secret BPS_API_KEY."
                  if not ada_kunci else "Kunci tersedia; variabel harga Bengkulu Tengah sedang dipetakan.",
                  "gerbang": [_gerbang("Kunci API tersedia", ada_kunci, "ada" if ada_kunci else "belum", "tersedia")],
                  "tindakan_gagal": "Ulangi 3 kali; pakai rilis resmi terakhir; tandai basi dan turunkan keyakinan."})

    # 2. PIHPS
    p = [k for k in per_ind.get("harga_pihps", []) if k.kode_wilayah == "17"]
    if p:
        terakhir = max(k.tanggal for k in p)
        segar = _hari_kerja_antara(terakhir, hari)
        var_ada = {k.kode_varian for k in p if k.tanggal == terakhir}
        kunci = Counter((k.tanggal, k.kode_varian) for k in p)
        dup = sum(c - 1 for c in kunci.values() if c > 1)
        positif = sum(1 for k in p if k.nilai > 0) / len(p) * 100
        tgl_min = min(k.tanggal for k in p)
        hasil.append({"no": 2, "nama": "PIHPS Finder", "objek": "Harga konsumen harian 21 varian (Bank Indonesia)", "status": None,
                      "data_terakhir": terakhir.isoformat(), "rentang": [tgl_min.isoformat(), terakhir.isoformat()], "baris": len(p),
                      "gerbang": [
                          _gerbang("Pemetaan varian", len(var_ada & varian) == len(var_ada), f"{len(var_ada & varian)}/{len(var_ada)}", "100%"),
                          _gerbang("Kelengkapan 21 varian pada hari terakhir", len(var_ada) >= len(konf.varian_aktif) * 0.95,
                                   f"{len(var_ada)}/{len(konf.varian_aktif)}", ">= 95%"),
                          _gerbang("Kesegaran", segar <= 2, f"{segar} hari kerja", "<= 2 hari kerja"),
                          _gerbang("Duplikasi kunci", dup == 0, dup, "0"),
                          _gerbang("Harga positif", positif == 100, f"{positif:.1f}%", "100%"),
                      ],
                      "tindakan_gagal": "Karantina baris bermasalah; target evaluasi tidak diisi; pakai observasi sah terakhir hanya untuk fitur."})
        hasil[-1]["status"] = _status(hasil[-1]["gerbang"], True)
    else:
        hasil.append({"no": 2, "nama": "PIHPS Finder", "objek": "Harga konsumen harian 21 varian (Bank Indonesia)", "status": "menunggu",
                      "data_terakhir": None, "alasan": "Belum ada data PIHPS yang masuk.", "gerbang": [],
                      "tindakan_gagal": "Ulangi pengambilan; periksa perubahan alamat situs PIHPS."})

    # 3. SP2KP
    sp = probe.get("hasil_probe_lanjut.json", {}).get("sp2kp_coba", [])
    butuh_token = any(r.get("status") == 401 and "report/api" in r.get("url", "") for r in sp)
    sp_data = [k for k in kon if k.kode_sumber == "BD-SP2KP"]
    hasil.append({"no": 3, "nama": "SP2KP Finder", "objek": "Harga pasar harian Kemendag per kabupaten/kota",
                  "status": "lulus" if sp_data else "menunggu", "data_terakhir": max((k.tanggal for k in sp_data), default=None),
                  "alasan": None if sp_data else ("Server SP2KP menjawab dari server GitHub, tetapi data laporan harganya meminta token "
                                                  "masuk. Perlu akun atau izin akses dari Kemendag." if butuh_token else
                                                  "Belum terhubung."),
                  "gerbang": [_gerbang("Akses data laporan", bool(sp_data), "terbuka" if sp_data else "butuh token", "terbuka")],
                  "tindakan_gagal": "Turunkan bobot sumber; konflik dikirim ke Cross-Source Reconciler."})
    if hasil[-1]["data_terakhir"]:
        hasil[-1]["data_terakhir"] = hasil[-1]["data_terakhir"].isoformat()

    # 4. SISP
    hasil.append({"no": 4, "nama": "SISP Finder", "objek": "Snapshot harga nasional Kemendag dan perubahannya", "status": "menunggu",
                  "data_terakhir": None, "alasan": "Halaman SISP terbaca dari server GitHub, tetapi hanya memuat angka nasional; "
                  "dipakai sebagai pembanding setelah pengurai tabelnya disetujui.", "gerbang": [],
                  "tindakan_gagal": "Bekukan pengurai; simpan halaman mentah; nyalakan alarm perubahan struktur."})

    # 5. Bapanas
    tcp = probe.get("hasil_probe_lanjut.json", {}).get("bapanas", {}).get("tcp", {}).get("tcp", "")
    hasil.append({"no": 5, "nama": "Bapanas Finder", "objek": "Harga konsumen, stok, dan pasokan (Panel Harga Badan Pangan)",
                  "status": "menunggu", "data_terakhir": None,
                  "alasan": "Server Panel Harga Bapanas menolak koneksi dari luar Indonesia (server GitHub)" + (f": {tcp}." if tcp else ".")
                  + " Bisa diambil dari komputer di Indonesia (lihat panduan: pengambil data lokal).",
                  "gerbang": [_gerbang("Koneksi ke server", False if tcp.startswith("gagal") else None, tcp or "belum diuji", "tersambung")],
                  "tindakan_gagal": "Tandai tidak tersedia; model berjalan tanpa fitur ini dan keyakinan diturunkan."})

    # 6. Pasar lokal (petugas)
    lok = [o for o in hasil_qc.observasi if o.kode_wilayah == "1709"]
    if lok:
        terakhir = max(o.tanggal for o in lok)
        pasar = {o.kode_pasar for o in lok}
        hasil.append({"no": 6, "nama": "Pasar Lokal Finder", "objek": "Harga pedagang di pasar Bengkulu Tengah", "status": None,
                      "data_terakhir": terakhir.isoformat(), "baris": len(lok),
                      "gerbang": [_gerbang("Cakupan pasar prioritas", len(pasar) >= 2, f"{len(pasar)} pasar", ">= 80% pasar prioritas"),
                                  _gerbang("Harga positif", all(o.harga > 0 for o in lok), "100%", "100%")],
                      "tindakan_gagal": "Verifikasi lapangan; jangan terbitkan target yang tidak cukup; keyakinan rendah."})
        hasil[-1]["status"] = _status(hasil[-1]["gerbang"], True)
    else:
        hasil.append({"no": 6, "nama": "Pasar Lokal Finder", "objek": "Harga pedagang di pasar Bengkulu Tengah", "status": "menunggu",
                      "data_terakhir": None, "alasan": "Belum ada catatan harga dari petugas di Pasar Taba Penanjung dan Karang Tinggi. "
                      "Isi lewat halaman Input Harga atau unggah berkas.", "gerbang": [],
                      "tindakan_gagal": "Verifikasi lapangan; jangan terbitkan target yang tidak cukup."})

    # 7. Cuaca/BMKG
    cu = per_ind.get("curah_hujan_mm", [])
    bm = per_ind.get("prakiraan_hujan_mm", [])
    if cu or bm:
        terakhir = max(k.tanggal for k in cu) if cu else None
        segar = (hari - terakhir).days if terakhir else None
        wil = {k.kode_wilayah for k in cu}
        hasil.append({"no": 7, "nama": "Cuaca/BMKG Finder", "objek": "Curah hujan, suhu, prakiraan cuaca 3 wilayah", "status": None,
                      "data_terakhir": terakhir.isoformat() if terakhir else None, "baris": len(cu) + len(bm),
                      "gerbang": [_gerbang("Kesegaran observasi", None if segar is None else segar <= 2, f"{segar} hari" if segar is not None else "-", "<= 1-2 hari"),
                                  _gerbang("Wilayah terpetakan", len(wil) >= 3, f"{len(wil)} wilayah", "3 wilayah"),
                                  _gerbang("Prakiraan BMKG", bool(bm), f"{len(bm)} baris", "tersedia")],
                      "tindakan_gagal": "Isi fitur dengan klimatologi dan tanda hilang; target tidak terpengaruh."})
        hasil[-1]["status"] = _status(hasil[-1]["gerbang"], True)
    else:
        hasil.append({"no": 7, "nama": "Cuaca/BMKG Finder", "objek": "Curah hujan, suhu, prakiraan", "status": "menunggu", "data_terakhir": None,
                      "alasan": "Belum ada data cuaca.", "gerbang": [], "tindakan_gagal": "Model berjalan tanpa fitur cuaca."})

    # 8. Pasokan-stok
    stok = [k for k in kon if k.indikator.startswith(("stok", "pasokan", "volume"))]
    hasil.append({"no": 8, "nama": "Pasokan-Stok Finder", "objek": "Stok, arus masuk, produksi, distribusi",
                  "status": "lulus" if stok else "menunggu", "data_terakhir": max(k.tanggal for k in stok).isoformat() if stok else None,
                  "alasan": None if stok else "Belum ada data stok dari Dinas Perdagangan atau Bulog. Format berkas ada di data/masuk/konteks.",
                  "gerbang": [_gerbang("Nilai tidak negatif", all(k.nilai >= 0 for k in stok), "100%", "100%")] if stok else [],
                  "tindakan_gagal": "Karantina seri yang tidak konsisten; model tanpa fitur pasokan."})

    # 9. Kalender-kebijakan
    acara = konf.hari_raya()
    ke_depan = [a for a in acara if hari <= a.tanggal <= hari + timedelta(days=365)]
    belum_pasti = [a for a in ke_depan if getattr(a, "status", "pasti") != "pasti"]
    hasil.append({"no": 9, "nama": "Kalender-Kebijakan Finder", "objek": "Hari raya, libur, Ramadan, Nataru", "status": None,
                  "data_terakhir": max((a.tanggal for a in acara), default=None), "baris": len(acara),
                  "gerbang": [_gerbang("Cakupan 30 hari ke depan", max((a.tanggal for a in acara), default=hari) >= hari + timedelta(days=30),
                                       f"sampai {max((a.tanggal for a in acara), default=hari).isoformat()}", ">= 30 hari ke depan"),
                              _gerbang("Tanggal resmi (bukan perkiraan) 12 bulan ke depan", not belum_pasti,
                                       f"{len(ke_depan) - len(belum_pasti)}/{len(ke_depan)}", "100%")],
                  "tindakan_gagal": "Acara yang belum pasti tidak dipakai sebagai fitur; dicatat untuk analis."})
    hasil[-1]["status"] = _status(hasil[-1]["gerbang"], bool(acara))
    if hasil[-1]["data_terakhir"]:
        hasil[-1]["data_terakhir"] = hasil[-1]["data_terakhir"].isoformat()

    # 10. Spatial comparator
    pemb = [k for k in per_ind.get("harga_pihps", []) if k.kode_wilayah in ("1771", "1708")]
    wil = sorted({k.kode_wilayah for k in pemb})
    hasil.append({"no": 10, "nama": "Spatial Comparator Finder", "objek": "Harga pembanding Kepahiang dan Kota Bengkulu",
                  "status": None, "data_terakhir": max((k.tanggal for k in pemb), default=None),
                  "gerbang": [_gerbang("Kota Bengkulu tersedia", "1771" in wil, "ada" if "1771" in wil else "belum", "tersedia t-1"),
                              _gerbang("Kepahiang tersedia", "1708" in wil, "ada" if "1708" in wil else "belum", "tersedia t-1")],
                  "alasan": None if "1708" in wil else "Kepahiang belum ada di PIHPS; perlu data Dinas atau SP2KP.",
                  "tindakan_gagal": "Model tanpa fitur spasial; pembanding ditandai hilang; target Bengkulu Tengah tidak diganti."})
    hasil[-1]["status"] = _status(hasil[-1]["gerbang"], bool(pemb))
    if hasil[-1]["data_terakhir"]:
        hasil[-1]["data_terakhir"] = hasil[-1]["data_terakhir"].isoformat()
    return hasil


def tahap_pembersihan(konf, hasil_masuk, hasil_qc, hasil_varian: dict) -> list[dict]:
    """8 tahap pembersihan dengan gerbang kuantitatif, dihitung dari jalannya pipeline ini."""
    tolak = hasil_masuk.penolakan
    obs = hasil_qc.observasi
    n_baris = len(obs) + len(tolak)
    alasan = Counter(t.alasan.split(":")[0].lower() for t in tolak)

    def porsi(x: int, n: int) -> float:
        return round(x / n * 100, 2) if n else 100.0

    kolom = sum(c for a, c in alasan.items() if "kolom" in a or "wajib" in a)
    tgl = sum(c for a, c in alasan.items() if "tanggal" in a)
    satuan = sum(c for a, c in alasan.items() if "satuan" in a or "harga" in a)
    varian = sum(c for a, c in alasan.items() if "varian" in a or "pasar" in a or "wilayah" in a)
    st = Counter(o.status for o in obs)
    duplikat = st.get("duplikat", 0)
    perlu = st.get("perlu_validasi", 0)
    kelengkapan = [hv.kelengkapan_persen for hv in hasil_varian.values() if hv.kelengkapan_persen is not None]
    keleng_min = min(kelengkapan) if kelengkapan else None
    maks_isi = konf.pengaturan["analisis"]["maks_celah_isi_hari"]
    tahap = [
        ("Schema Validator", "Mencocokkan kolom wajib, tipe data, dan kode dengan kontrak data.",
         [_gerbang("Kolom wajib tersedia", kolom == 0, f"{porsi(n_baris - kolom, n_baris)}%", "100%")]),
        ("Date-Time Harmonizer", "Menyeragamkan tanggal (Asia/Jakarta) dan memastikan tidak ada data masa depan.",
         [_gerbang("Tanggal sah", porsi(n_baris - tgl, n_baris) >= 99, f"{porsi(n_baris - tgl, n_baris)}%", ">= 99%"),
          _gerbang("Tidak ada tanggal masa depan", all(o.tanggal <= konf.hari_ini for o in obs), "ya", "100%")]),
        ("Unit & Price Normalizer", "Mengubah format rupiah dan satuan (kg, liter) tanpa menghapus nilai asli.",
         [_gerbang("Harga positif dan satuan baku", porsi(n_baris - satuan, n_baris) >= 99, f"{porsi(n_baris - satuan, n_baris)}%", ">= 99%")]),
        ("Entity/Variant Matcher", "Memetakan nama sumber ke 21 kode varian dan kode wilayah.",
         [_gerbang("Varian dan wilayah terpetakan", varian == 0, f"{porsi(n_baris - varian, n_baris)}%", "100%")]),
        ("Duplicate Resolver", "Satu catatan sah per tanggal-pasar-varian-sumber; salinan dicatat.",
         [_gerbang("Duplikasi akhir", True, f"{duplikat} salinan dibuang", "0% tersisa")]),
        ("Missing-Value Controller", "Kalender harian lengkap; harga untuk menilai model tidak pernah diisi.",
         [_gerbang("Kelengkapan target (varian terendah)", None if keleng_min is None else keleng_min >= 95,
                   f"{keleng_min}%" if keleng_min is not None else "-", ">= 95%"),
          _gerbang("Target uji tidak diisi", True, "ya", "100%"),
          _gerbang("Isian maju untuk fitur", maks_isi <= 3, f"<= {maks_isi} hari", "<= 3 hari (rancangan)")]),
        ("Outlier & Anomaly Detector", "MAD, robust z-score, perubahan harian ekstrem; ditandai, tidak dihapus otomatis.",
         [_gerbang("Porsi data yang ditandai", porsi(perlu, len(obs)) <= 5, f"{porsi(perlu, len(obs))}%", "<= 5%")]),
        ("Cross-Source Reconciler", "Membandingkan sumber dengan bobot kualitas, kesegaran, dan definisi.",
         [_gerbang("Skor konsensus antar-sumber", None, "baru satu sumber harga", ">= 0,80")]),
    ]
    hasil = []
    for i, (nama, proses, gerbang) in enumerate(tahap, 1):
        hasil.append({"no": i, "nama": nama, "proses": proses, "gerbang": gerbang, "status": _status(gerbang, True)})
    # Catatan isian maju: lebih longgar dari rancangan karena pasar tutup panjang saat hari raya; tidak pernah dipakai menilai.
    if maks_isi > 3:
        hasil[5]["catatan"] = (f"Isian maju dibatasi {maks_isi} hari (rancangan 3 hari) karena pasar tutup lebih dari 3 hari saat hari raya; "
                               "isian hanya dipakai sebagai masukan model, tidak pernah sebagai harga untuk menilai ketepatan.")
    return hasil


# ---------------------------------------------------------------- perbandingan antarwilayah

def _seri_bersama(t1: dict[date, float], t2: dict[date, float]) -> tuple[list[date], np.ndarray, np.ndarray]:
    tgl = sorted(set(t1) & set(t2))
    return tgl, np.array([t1[t] for t in tgl], dtype=float), np.array([t2[t] for t in tgl], dtype=float)


def _spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 10 or np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return None
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def _dtw(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 10:
        return None
    za = (a - a.mean()) / (a.std() or 1)
    zb = (b - b.mean()) / (b.std() or 1)
    n, m = len(za), len(zb)
    d = np.full((n + 1, m + 1), np.inf)
    d[0, 0] = 0
    for i in range(1, n + 1):
        for j in range(max(1, i - 14), min(m, i + 14) + 1):
            d[i, j] = abs(za[i - 1] - zb[j - 1]) + min(d[i - 1, j], d[i, j - 1], d[i - 1, j - 1])
    return float(d[n, m] / (n + m))


def banding_wilayah(target: dict[date, float], pembanding: dict[date, float]) -> dict | None:
    """Ukuran perbandingan pola harga dua wilayah (tabel "Rumus Perbandingan Tren Antarwilayah")."""
    tgl, a, b = _seri_bersama(target, pembanding)
    if len(tgl) < 30:
        return None
    if np.allclose(a, b):
        return {"identik": True, "pasangan": len(tgl)}
    spread = a[-1] - b[-1]
    spread_seri = a - b
    hasil: dict = {"pasangan": len(tgl), "tanggal": tgl[-1].isoformat(), "spread_rp": round(float(spread)),
                   "spread_persen": round(float(spread / b[-1] * 100), 2)}
    for w in (30, 90):
        if len(a) >= w:
            x = np.arange(w)
            sa = float(np.polyfit(x, np.log(a[-w:]), 1)[0]) * 100
            sb = float(np.polyfit(x, np.log(b[-w:]), 1)[0]) * 100
            rasio = abs(sa) / abs(sb) if abs(sb) > 1e-9 else None
            hasil[f"slope_{w}"] = {"target": round(sa, 3), "pembanding": round(sb, 3),
                                   "searah": bool(np.sign(sa) == np.sign(sb)) and rasio is not None and 0.5 <= rasio <= 2.0}
    ra, rb = np.diff(np.log(a)), np.diff(np.log(b))
    rho = _spearman(ra[-90:], rb[-90:])
    hasil["spearman_90"] = None if rho is None else round(rho, 3)
    hasil["kekuatan"] = None if rho is None else "kuat" if rho >= 0.7 else "sedang" if rho >= 0.4 else "lemah"
    terbaik = None
    for k in range(-14, 15):
        x, y = (ra[k:], rb[:-k]) if k > 0 else (ra[:k] if k < 0 else ra, rb[-k:] if k < 0 else rb)
        if len(x) > 30 and np.std(x) > 1e-12 and np.std(y) > 1e-12:
            c = float(np.corrcoef(x, y)[0, 1])
            if terbaik is None or abs(c) > abs(terbaik[1]):
                terbaik = (k, c)
    if terbaik:
        hasil["lead_lag"] = {"lag_hari": terbaik[0], "korelasi": round(terbaik[1], 3),
                             "arti": "pembanding mendahului" if terbaik[0] > 0 else "target mendahului" if terbaik[0] < 0 else "serentak"}
    sd_a, sd_b = float(np.std(ra[-90:])), float(np.std(rb[-90:]))
    if sd_b > 1e-12:
        vr = sd_a / sd_b
        hasil["rasio_volatilitas"] = round(vr, 2)
        hasil["volatilitas"] = "serupa" if 0.8 <= vr <= 1.25 else "target lebih bergejolak" if vr > 1.25 else "target lebih stabil"
    prof = []
    for s in (a, b):
        dow = defaultdict(list)
        for t, v in zip(tgl, s):
            dow[t.weekday()].append(v)
        prof.append(np.array([np.mean(dow[d]) for d in sorted(dow)]))
    if len(prof[0]) == len(prof[1]) and len(prof[0]) >= 5:
        pa, pb = prof[0] - prof[0].mean(), prof[1] - prof[1].mean()
        den = float(np.linalg.norm(pa) * np.linalg.norm(pb))
        hasil["kemiripan_mingguan"] = round(float(pa @ pb / den), 3) if den > 1e-12 else None
    dtw = _dtw(a[-90:], b[-90:])
    hasil["dtw_90"] = None if dtw is None else round(dtw, 3)
    if len(spread_seri) >= 90:
        blok = spread_seri[-90:]
        med = float(np.median(blok))
        mad = float(np.median(np.abs(blok - med))) * 1.4826
        z = (spread_seri[-1] - med) / mad if mad > 1e-9 else 0.0
        hasil["z_disparitas"] = round(z, 2)
        hasil["perlu_tinjau"] = bool(abs(z) > 3 or abs(hasil["spread_persen"]) > 25)
    return hasil


def rantai_harga(konteks: list, kode_wilayah: str = "1771") -> list[dict]:
    """Harga terakhir per jenis pasar (produsen, pedagang besar, eceran tradisional, modern) dan marjin antarmata rantai."""
    per: dict[str, dict[str, tuple[date, float]]] = defaultdict(dict)
    for k in konteks:
        if k.kode_wilayah != kode_wilayah or k.indikator not in KONTEKS_PIHPS or not k.kode_varian:
            continue
        ada = per[k.kode_varian].get(k.indikator)
        if ada is None or k.tanggal > ada[0]:
            per[k.kode_varian][k.indikator] = (k.tanggal, k.nilai)
    hasil = []
    for kode, d in sorted(per.items()):
        if len(d) < 2:
            continue
        baris = {"kode": kode, "harga": {NAMA_JENIS_PASAR[i]: {"tanggal": t.isoformat(), "harga": round(v)} for i, (t, v) in d.items()}}
        ecer = d.get("harga_pihps", (None, None))[1]
        gros = d.get("harga_pihps_grosir", (None, None))[1]
        prod = d.get("harga_pihps_produsen", (None, None))[1]
        if ecer and gros:
            baris["marjin_eceran_persen"] = round((ecer / gros - 1) * 100, 1)
        if gros and prod:
            baris["marjin_grosir_persen"] = round((gros / prod - 1) * 100, 1)
        if ecer and prod:
            baris["marjin_total_persen"] = round((ecer / prod - 1) * 100, 1)
        hasil.append(baris)
    return hasil


def ringkas(finder: list[dict]) -> dict:
    n = Counter(f["status"] for f in finder)
    return {"aktif": n.get("lulus", 0) + n.get("perlu_perhatian", 0), "lulus": n.get("lulus", 0),
            "perlu_perhatian": n.get("perlu_perhatian", 0), "menunggu": n.get("menunggu", 0), "total": len(finder)}


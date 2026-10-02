"""Kebijakan TPID: rekomendasi langkah dari sinyal, catatan kebijakan beserta penilaian dampaknya, dan rapat TPID.

Rancangan Aksi Perubahan meminta agar sinyal tervalidasi dipakai dalam keputusan TPID, rekomendasi berisiko tinggi
selalu disetujui manusia, forum TPID berjalan minimal sekali per triwulan, dan dampak intervensi dievaluasi.

Berkas masukan (diisi lewat situs, disalin mesin dari Firestore; lihat firestore_sinkron.py):
  data/kebijakan/*.csv               id,tanggal_mulai,tanggal_selesai,jenis,kode_varian,tujuan,uraian,id_rekomendasi,pencatat
  data/rapat/*.csv                   id,tanggal,jenis,agenda,keputusan,jumlah_sinyal,peserta,tautan_notulen,pencatat
  data/keputusan_rekomendasi/*.csv   id_rekomendasi,keputusan,catatan,penyetuju,tanggal

Penilaian dampak sengaja sederhana dan terbuka: harga median sebelum kebijakan dibandingkan dengan harga median
sesudahnya, dengan memperhitungkan arah harga sebelum kebijakan. Ini bukan bukti sebab-akibat, karena panen,
cuaca, atau pasokan dari luar daerah juga menggerakkan harga.
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path
from statistics import median

JENIS_KEBIJAKAN = {
    "operasi_pasar": "Operasi pasar atau pasar murah",
    "koordinasi_pasokan": "Koordinasi pasokan dan stok",
    "distribusi": "Fasilitasi distribusi atau angkutan",
    "komunikasi_publik": "Imbauan atau komunikasi publik",
    "pengawasan": "Pengawasan atau sidak pasar",
    "penyerapan_panen": "Penyerapan hasil panen",
    "lainnya": "Lainnya",
}
TUJUAN = {
    "menurunkan_harga": "Menurunkan harga",
    "menahan_kenaikan": "Menahan kenaikan harga",
    "menahan_penurunan": "Menahan harga jatuh (melindungi petani)",
}
JENIS_RAPAT = {
    "rapat_koordinasi": "Rapat koordinasi TPID",
    "high_level_meeting": "High Level Meeting TPID",
    "rapat_teknis": "Rapat teknis",
}
LABEL_DAMPAK = {
    "berpengaruh": "Berpengaruh",
    "tidak_berpengaruh": "Tidak berpengaruh",
    "netral": "Netral",
    "menunggu": "Menunggu data",
    "belum_dapat_dinilai": "Belum dapat dinilai",
}
ATURAN_BAWAAN = {"ambang_persen": 2.0, "hari_sebelum": 7, "hari_sesudah": 14, "jeda_hari": 2, "minimal_titik": 3}


def _baca_csv(folder: Path) -> list[dict]:
    baris = []
    for p in sorted(folder.glob("*.csv")) if folder.is_dir() else []:
        with p.open(newline="", encoding="utf-8-sig") as f:
            for b in csv.DictReader(f):
                baris.append({k.strip(): (v or "").strip() for k, v in b.items() if k})
    return baris


def _tanggal(teks: str) -> date | None:
    try:
        return date.fromisoformat(str(teks)[:10])
    except ValueError:
        return None


def baca_kebijakan(akar: Path) -> list[dict]:
    hasil = {}
    for b in _baca_csv(akar / "data" / "kebijakan"):
        if b.get("id") and _tanggal(b.get("tanggal_mulai", "")):
            hasil[b["id"]] = b
    return list(hasil.values())


def baca_rapat(akar: Path) -> list[dict]:
    hasil = {}
    for b in _baca_csv(akar / "data" / "rapat"):
        if b.get("id") and _tanggal(b.get("tanggal", "")):
            hasil[b["id"]] = b
    return list(hasil.values())


def baca_keputusan_rekomendasi(akar: Path) -> dict[str, dict]:
    hasil: dict[str, dict] = {}
    for b in sorted(_baca_csv(akar / "data" / "keputusan_rekomendasi"), key=lambda x: x.get("tanggal", "")):
        if b.get("id_rekomendasi") and b.get("keputusan") in ("setuju", "tolak"):
            hasil[b["id_rekomendasi"]] = b
    return hasil


# ---------------------------------------------------------------- rekomendasi dari sinyal

def _langkah(s: dict) -> tuple[list[str], str]:
    """Langkah yang disarankan untuk satu sinyal, beserta jenis kebijakan yang paling sesuai."""
    kom = (s.get("komoditas") or s.get("varian") or "komoditas ini").lower()
    var = s.get("varian") or kom
    jenis, kep, arah = s["jenis"], s.get("keparahan"), s.get("arah")
    if jenis == "anomali_harga" and arah == "turun":
        return ([f"Cek harga {kom} di tingkat petani atau peternak, karena harga jatuh bisa merugikan produsen.",
                 "Pertimbangkan penyerapan hasil panen atau penyaluran ke daerah lain.",
                 "Pastikan penurunan ini bukan salah catat dengan verifikasi ke pasar."], "penyerapan_panen")
    if jenis == "anomali_harga" and kep == "tinggi":
        return ([f"Verifikasi harga {var} ke pasar hari ini, minimal ke dua pedagang.",
                 f"Minta Dinas Perdagangan mengecek stok dan pasokan {kom}.",
                 f"Bila kenaikan bertahan 3 hari atau lebih, bahas operasi pasar atau pasar murah {kom} di rapat TPID.",
                 "Siapkan imbauan agar warga tidak membeli berlebihan."], "operasi_pasar")
    if jenis == "anomali_harga":
        return ([f"Verifikasi harga {var} ke pasar dalam 2 hari.",
                 f"Pantau pasokan {kom} bersama Dinas Perdagangan.",
                 "Bahas di rapat TPID berikutnya bila kenaikan berlanjut."], "koordinasi_pasokan")
    if jenis == "proyeksi_naik":
        return ([f"Pantau harga {var} setiap hari selama 7 hari ke depan.",
                 f"Pastikan stok {kom} cukup sebelum kenaikan terjadi."], "koordinasi_pasokan")
    if jenis == "risiko_hari_raya":
        return ([f"Pantau harga {kom} setiap hari sejak H-14.",
                 "Koordinasikan stok dan distribusi menjelang hari raya.",
                 f"Siapkan pasar murah {kom} bila harga mulai naik."], "operasi_pasar")
    if jenis == "data_terlambat":
        return (["Hubungi petugas pencatat di pasar terkait.",
                 "Untuk pasar di wilayah sulit sinyal, pakai pengiriman luring lalu kirim saat ada sinyal."], "lainnya")
    return (["Analis mengecek ulang cara prakiraan di halaman Akurasi sebelum angkanya dipakai."], "lainnya")


def rekomendasi(sinyal: list[dict], keputusan: dict[str, dict]) -> list[dict]:
    """Rekomendasi untuk sinyal aktif yang penting. Yang berisiko tinggi wajib disetujui manusia sebelum dijalankan."""
    hasil = []
    for s in sinyal:
        if not s.get("aktif") or s.get("keparahan") not in ("tinggi", "sedang"):
            continue
        if s.get("status") in ("selesai", "false_alarm"):
            continue
        langkah, jenis = _langkah(s)
        rid = f"R-{s['id']}"
        k = keputusan.get(rid)
        hasil.append({
            "id": rid, "id_sinyal": s["id"], "jenis_sinyal": s["jenis"], "judul": s.get("judul", ""),
            "kode_varian": s.get("kode_varian"), "varian": s.get("varian"), "komoditas": s.get("komoditas"),
            "keparahan": s.get("keparahan"), "risiko_tinggi": s.get("keparahan") == "tinggi",
            "tanggal": s.get("tanggal_terakhir") or s.get("tanggal_mulai"),
            "langkah": langkah, "jenis_kebijakan": jenis,
            "status": {"setuju": "disetujui", "tolak": "ditolak"}[k["keputusan"]] if k else "menunggu",
            "keputusan": k,
        })
    urut = {"tinggi": 0, "sedang": 1}
    hasil.sort(key=lambda r: (r["status"] != "menunggu", urut.get(r["keparahan"], 2), r["tanggal"] or ""), reverse=False)
    return hasil


# ---------------------------------------------------------------- dampak kebijakan

def _median_jendela(per: dict[date, float], mulai: date, akhir: date) -> tuple[float | None, int]:
    nilai = [v for t, v in per.items() if mulai <= t <= akhir and v == v]
    return (float(median(nilai)) if nilai else None), len(nilai)


def _klasifikasi(perubahan: float, tren: float | None, tujuan: str, ambang: float) -> str:
    """perubahan: % harga sesudah vs sebelum. tren: % harga sebelum vs periode sebelumnya lagi (arah sebelum kebijakan)."""
    if tujuan == "menahan_penurunan":  # tujuan kebalikan: harga diharapkan tidak terus turun
        perubahan, tren = -perubahan, (-tren if tren is not None else None)
    if perubahan <= -ambang:
        return "berpengaruh"  # harga turun sesudah kebijakan
    if tren is not None and tren >= ambang and perubahan <= tren - ambang:
        return "berpengaruh"  # sebelumnya naik, sesudahnya kenaikan jelas melambat atau berhenti
    if perubahan >= ambang and (tren is None or perubahan > tren - ambang):
        return "tidak_berpengaruh"  # harga tetap naik secepat sebelumnya atau lebih
    return "netral"


def nilai_dampak(k: dict, harga: dict[str, dict[date, float]], hari_ini: date, aturan: dict | None = None) -> dict:
    """Penilaian dampak satu kebijakan terhadap harga varian yang disasar."""
    a = {**ATURAN_BAWAAN, **(aturan or {})}
    t0 = _tanggal(k["tanggal_mulai"])
    siap = t0 + timedelta(days=a["hari_sesudah"])
    dasar = {"siap_dinilai": siap.isoformat(), "per_varian": [], "perubahan_persen": None, "tren_sebelum_persen": None}
    if hari_ini < siap:
        return {**dasar, "status": "menunggu",
                "keterangan": f"Dinilai otomatis mulai {siap.isoformat()}, setelah {a['hari_sesudah']} hari data terkumpul."}
    per_varian = []
    for kode in [x for x in k.get("kode_varian", "").replace(",", ";").split(";") if x.strip()]:
        per = harga.get(kode.strip().upper()) or {}
        sebelum, n1 = _median_jendela(per, t0 - timedelta(days=a["hari_sebelum"]), t0 - timedelta(days=1))
        sesudah, n2 = _median_jendela(per, t0 + timedelta(days=a["jeda_hari"]), siap)
        awal, n0 = _median_jendela(per, t0 - timedelta(days=2 * a["hari_sebelum"]), t0 - timedelta(days=a["hari_sebelum"] + 1))
        if not sebelum or not sesudah or n1 < a["minimal_titik"] or n2 < a["minimal_titik"]:
            per_varian.append({"kode_varian": kode.strip().upper(), "status": "belum_dapat_dinilai"})
            continue
        perubahan = (sesudah / sebelum - 1) * 100
        tren = (sebelum / awal - 1) * 100 if awal and n0 >= a["minimal_titik"] else None
        per_varian.append({
            "kode_varian": kode.strip().upper(), "harga_sebelum": round(sebelum), "harga_sesudah": round(sesudah),
            "perubahan_persen": round(perubahan, 1), "tren_sebelum_persen": None if tren is None else round(tren, 1),
            "status": _klasifikasi(perubahan, tren, k.get("tujuan") or "menurunkan_harga", a["ambang_persen"]),
        })
    dinilai = [v for v in per_varian if v["status"] != "belum_dapat_dinilai"]
    if not dinilai:
        return {**dasar, "per_varian": per_varian, "status": "belum_dapat_dinilai",
                "keterangan": "Data harga sebelum atau sesudah kebijakan belum cukup (minimal 3 hari di tiap sisi)."}
    perubahan = median(v["perubahan_persen"] for v in dinilai)
    tren_ada = [v["tren_sebelum_persen"] for v in dinilai if v["tren_sebelum_persen"] is not None]
    tren = median(tren_ada) if tren_ada else None
    status = _klasifikasi(perubahan, tren, k.get("tujuan") or "menurunkan_harga", a["ambang_persen"])
    return {**dasar, "per_varian": per_varian, "perubahan_persen": round(perubahan, 1),
            "tren_sebelum_persen": None if tren is None else round(tren, 1), "status": status,
            "keterangan": _kalimat(status, perubahan, tren, a)}


def _kalimat(status: str, perubahan: float, tren: float | None, a: dict) -> str:
    arah = f"{'naik' if perubahan > 0 else 'turun'} {abs(perubahan):.1f}%" if abs(perubahan) >= 0.05 else "tetap"
    sebelum = f" Sebelum kebijakan, harga {'naik' if tren > 0 else 'turun'} {abs(tren):.1f}% dalam seminggu." if tren and abs(tren) >= 0.05 else ""
    inti = {
        "berpengaruh": "Harga bergerak sesuai tujuan kebijakan.",
        "tidak_berpengaruh": "Harga tetap bergerak berlawanan dengan tujuan kebijakan.",
        "netral": f"Perubahan harga kecil (kurang dari {a['ambang_persen']:g}%).",
    }[status]
    return (f"{inti} Harga {a['hari_sesudah']} hari sesudah kebijakan {arah} dibanding seminggu sebelumnya.{sebelum} "
            "Faktor lain seperti panen dan cuaca juga ikut memengaruhi.")


# ---------------------------------------------------------------- rapat dan ringkasan

def _triwulan(t: date) -> str:
    return f"{t.year}-T{(t.month - 1) // 3 + 1}"


def bentuk(akar: Path, sinyal: list[dict], harga: dict[str, dict[date, float]], hari_ini: date,
           nama_varian: dict[str, str], aturan: dict | None = None) -> dict:
    keputusan = baca_keputusan_rekomendasi(akar)
    rek = rekomendasi(sinyal, keputusan)
    daftar = []
    for k in sorted(baca_kebijakan(akar), key=lambda x: x["tanggal_mulai"], reverse=True):
        kode = [x.strip().upper() for x in k.get("kode_varian", "").replace(",", ";").split(";") if x.strip()]
        daftar.append({
            **k, "kode_varian": kode, "nama_varian": [nama_varian.get(x, x) for x in kode],
            "nama_jenis": JENIS_KEBIJAKAN.get(k.get("jenis", ""), k.get("jenis", "")),
            "nama_tujuan": TUJUAN.get(k.get("tujuan", ""), TUJUAN["menurunkan_harga"]),
            "dampak": nilai_dampak(k, harga, hari_ini, aturan),
        })
    rapat = []
    for r in sorted(baca_rapat(akar), key=lambda x: x["tanggal"], reverse=True):
        rapat.append({**r, "nama_jenis": JENIS_RAPAT.get(r.get("jenis", ""), r.get("jenis", "")),
                      "triwulan": _triwulan(_tanggal(r["tanggal"]))})
    tri_ini = _triwulan(hari_ini)
    per_triwulan: dict[str, int] = {}
    for r in rapat:
        per_triwulan[r["triwulan"]] = per_triwulan.get(r["triwulan"], 0) + 1
    tinggi = [r for r in rek if r["risiko_tinggi"]]
    hitung = {s: sum(1 for k in daftar if k["dampak"]["status"] == s) for s in LABEL_DAMPAK}
    return {
        "rekomendasi": rek,
        "kebijakan": daftar,
        "rapat": rapat,
        "ringkasan": {
            "rekomendasi_menunggu": sum(1 for r in rek if r["status"] == "menunggu"),
            "rekomendasi_tinggi": len(tinggi),
            "rekomendasi_tinggi_diputuskan": sum(1 for r in tinggi if r["status"] != "menunggu"),
            "kebijakan": len(daftar), "dampak": hitung,
            "triwulan_ini": tri_ini, "rapat_triwulan_ini": per_triwulan.get(tri_ini, 0), "rapat_per_triwulan": per_triwulan,
        },
        "label": {"jenis": JENIS_KEBIJAKAN, "tujuan": TUJUAN, "rapat": JENIS_RAPAT, "dampak": LABEL_DAMPAK},
        "aturan_dampak": {**ATURAN_BAWAAN, **(aturan or {})},
    }

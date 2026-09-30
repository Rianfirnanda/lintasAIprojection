"""Buletin & laporan berkala (Tabel 4 Rancangan Aksi Perubahan).

  mingguan   : buletin harga mingguan, sinyal dini, prioritas verifikasi lapangan
  bulanan    : analisis bulanan, proyeksi, kinerja model, rekomendasi pengendalian harga
  triwulanan : bahan rapat TPID: pola, volatilitas, tindak lanjut sinyal, evaluasi model
  semesteran : evaluasi tengah tahun: stabilitas model, kualitas layanan, cakupan wilayah, kalibrasi ulang
  tahunan    : laporan tahunan: mutu data, akurasi proyeksi, manfaat kebijakan, keputusan lanjut atau henti model

Semua angka dihitung dari deret harga yang lolos quality gate. "Indeks harga pangan sederhana" adalah rata-rata
geometrik relatif harga antarperiode (tanpa bobot), sifatnya indikatif, BUKAN Indeks Harga Konsumen resmi BPS.
Rekomendasi disusun berbasis aturan sebagai bahan pertimbangan dan wajib ditelaah analis.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import date, timedelta
from statistics import mean, pstdev

from .kualitas import hari_wajib

JUMLAH_PERIODE = {"mingguan": 8, "bulanan": 6, "triwulanan": 4, "semesteran": 3, "tahunan": 2}
JUDUL = {
    "mingguan": "Buletin Harga Pangan Mingguan",
    "bulanan": "Analisis Harga Pangan Bulanan",
    "triwulanan": "Bahan Rapat TPID Triwulanan",
    "semesteran": "Evaluasi Harga Pangan Semesteran",
    "tahunan": "Laporan Tahunan Harga Pangan",
}
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
         "November", "Desember"]


def _a(x: float, digit: int = 1, tanda: bool = False) -> str:
    """Format angka gaya Indonesia (koma desimal)."""
    teks = f"{x:+.{digit}f}" if tanda else f"{x:.{digit}f}"
    return teks.replace(".", ",")


def _periode(jenis: str, tgl: date) -> tuple[date, date, str]:
    if jenis == "mingguan":
        mulai = tgl - timedelta(days=tgl.weekday())
        akhir = mulai + timedelta(days=6)
        iso = mulai.isocalendar()
        return mulai, akhir, f"Minggu ke-{iso.week} {iso.year}"
    if jenis == "bulanan":
        mulai = tgl.replace(day=1)
        akhir = (mulai + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        return mulai, akhir, f"{BULAN[tgl.month - 1]} {tgl.year}"
    if jenis == "semesteran":
        smt = 0 if tgl.month <= 6 else 1
        mulai = date(tgl.year, smt * 6 + 1, 1)
        akhir = date(tgl.year, 6, 30) if smt == 0 else date(tgl.year, 12, 31)
        return mulai, akhir, f"Semester {['I', 'II'][smt]} {tgl.year}"
    if jenis == "tahunan":
        return date(tgl.year, 1, 1), date(tgl.year, 12, 31), f"Tahun {tgl.year}"
    tw = (tgl.month - 1) // 3
    mulai = date(tgl.year, tw * 3 + 1, 1)
    akhir = (date(tgl.year + (tw == 3), (tw * 3 + 3) % 12 + 1, 1)) - timedelta(days=1)
    return mulai, akhir, f"Triwulan {['I', 'II', 'III', 'IV'][tw]} {tgl.year}"


def _sebelumnya(jenis: str, mulai: date) -> tuple[date, date, str]:
    return _periode(jenis, mulai - timedelta(days=1))


def _tahun_lalu(jenis: str, mulai: date) -> tuple[date, date, str]:
    if jenis == "mingguan":
        return _periode(jenis, mulai - timedelta(weeks=52))
    return _periode(jenis, mulai.replace(year=mulai.year - 1))


def _rata(per_tanggal: dict[date, float], mulai: date, akhir: date) -> float | None:
    nilai = [v for t, v in per_tanggal.items() if mulai <= t <= akhir]
    return mean(nilai) if nilai else None


def _persen(a: float | None, b: float | None) -> float | None:
    return round((a / b - 1) * 100, 2) if a is not None and b else None


def _volatilitas(per_tanggal: dict[date, float], mulai: date, akhir: date) -> float | None:
    urut = [per_tanggal[t] for t in sorted(per_tanggal) if mulai <= t <= akhir]
    r = [math.log(b / a) for a, b in zip(urut, urut[1:]) if a > 0 and b > 0]
    return round(pstdev(r) * 100, 2) if len(r) >= 3 else None


def _indeks_sederhana(relatif: list[float]) -> float | None:
    relatif = [x for x in relatif if x and x > 0]
    return round(math.exp(mean(math.log(x) for x in relatif)) * 100, 2) if relatif else None


def _kelengkapan(konf, observasi, mulai: date, akhir: date) -> dict:
    wajib = set(hari_wajib(konf, mulai, min(akhir, konf.hari_ini)))
    varian = {v.kode for v in konf.varian_aktif}
    per_pasar = []
    for p in konf.pasar_di(konf.wilayah_target):
        terima = {(o.tanggal, o.kode_varian) for o in observasi
                  if o.kode_pasar == p.kode and o.tanggal in wajib and o.kode_varian in varian and o.status != "ditolak_validator"}
        harap = len(wajib) * len(varian)
        per_pasar.append({"kode_pasar": p.kode, "nama_pasar": p.nama,
                          "kelengkapan_persen": round(len(terima) / harap * 100, 1) if harap else None})
    nilai = [p["kelengkapan_persen"] for p in per_pasar if p["kelengkapan_persen"] is not None]
    return {"hari_wajib": len(wajib), "rata_persen": round(mean(nilai), 1) if nilai else None, "per_pasar": per_pasar}


def _rekomendasi(konf, jenis, baris_varian, sinyal_periode, kelengkapan, hari_raya, drift) -> list[str]:
    ambang = konf.pengaturan["sinyal"]["ambang_persen"]
    rek: list[str] = []
    naik = [b for b in baris_varian if b["vs_sebelumnya_persen"] is not None
            and b["vs_sebelumnya_persen"] >= ambang[b["kelompok"]]]
    for b in sorted(naik, key=lambda b: -b["vs_sebelumnya_persen"])[:5]:
        pembanding = ""
        s = next((s for s in sinyal_periode if s.get("kode_varian") == b["kode"] and s["jenis"] == "anomali_harga"), None)
        wp = (s or {}).get("konteks", {}).get("wilayah_pembanding", {})
        if wp:
            pembanding = " Sebagai pembanding: " + ", ".join(
                f"{v['wilayah']} (selisih {_a(v.get('selisih_persen', 0), 0, True)}%)" for v in wp.values()) + "."
        rek.append(f"{b['nama']} naik {_a(b['vs_sebelumnya_persen'])}% dibanding periode sebelumnya. Perlu dicek langsung "
                   f"ke lapangan, termasuk kelancaran pasokan dan distribusinya.{pembanding}")
    belum = [s for s in sinyal_periode if s["jenis"] == "anomali_harga" and s["keparahan"] == "tinggi"
             and s.get("status") in ("baru", "perlu_verifikasi")]
    if belum:
        rek.append(f"Ada {len(belum)} peringatan penting yang belum diverifikasi. Tunjuk penanggung jawab dan sepakati tenggatnya.")
    kurang = [p for p in kelengkapan["per_pasar"]
              if p["kelengkapan_persen"] is not None and p["kelengkapan_persen"] < konf.pengaturan["target_kinerja"]["ketepatan_waktu_persen"]]
    for p in kurang:
        rek.append(f"Data {p['nama_pasar']} baru lengkap {_a(p['kelengkapan_persen'], 0)}%. Koordinasikan dengan petugas; "
                   "kalau sinyal sulit, halaman Catat Harga bisa dipakai tanpa internet.")
    if hari_raya:
        rek.append(f"{hari_raya['nama']} jatuh pada {hari_raya['tanggal']} (H-{hari_raya['h_minus']}). Siapkan pemantauan "
                   "harian mulai H-14 dan pastikan ketersediaan stok bersama Pemda dan Bulog.")
    if jenis != "mingguan" and drift:
        rek.append("Prakiraan untuk " + ", ".join(drift) + " perlu dicek ulang.")
    if jenis == "semesteran":
        rek.append("Periksa cara prakiraan, sumber data, hak akses, dan riwayat perubahan untuk evaluasi tengah tahun, "
                   "lalu sesuaikan ulang prakiraan yang mulai kurang tepat.")
    if jenis == "tahunan":
        rek.append("Putuskan lanjut atau hentikan tiap cara prakiraan berdasarkan uji independen dan persetujuan tata kelola, "
                   "lalu susun rencana pengembangan tahun berikutnya.")
    if not rek:
        rek.append("Harga semua varian masih dalam pola normal. Pemantauan rutin cukup dilanjutkan.")
    return rek


def _satu_periode(jenis, konf, harian_target, hasil_varian, sinyal, observasi, mulai, akhir, label, terbaru, ekstra) -> dict:
    s_mulai, s_akhir, s_label = _sebelumnya(jenis, mulai)
    y_mulai, y_akhir, y_label = _tahun_lalu(jenis, mulai)
    baris_varian = []
    relatif = []
    for v in konf.varian_aktif:
        per = harian_target.get(v.kode, {})
        kini = _rata(per, mulai, akhir)
        if kini is None:
            continue
        lalu = _rata(per, s_mulai, s_akhir)
        tahun_lalu = _rata(per, y_mulai, y_akhir)
        nilai_periode = [x for t, x in per.items() if mulai <= t <= akhir]
        if lalu:
            relatif.append(kini / lalu)
        b = {
            "kode": v.kode, "nama": v.nama, "komoditas": v.komoditas, "kelompok": v.kelompok, "satuan": v.satuan,
            "rata_rata": round(kini), "minimum": round(min(nilai_periode)), "maksimum": round(max(nilai_periode)),
            "vs_sebelumnya_persen": _persen(kini, lalu), "vs_tahun_lalu_persen": _persen(kini, tahun_lalu),
            "volatilitas_harian_persen": _volatilitas(per, mulai, akhir), "hari_data": len(nilai_periode),
        }
        if terbaru and v.kode in hasil_varian:
            hv = hasil_varian[v.kode]
            h7 = next((p for p in hv.proyeksi if p["h"] == 7), None)
            b["proyeksi_h7"] = h7
        baris_varian.append(b)

    sinyal_periode = [
        s for s in sinyal
        if s["jenis"] in ("anomali_harga", "proyeksi_naik", "risiko_hari_raya", "data_terlambat")
        and s["tanggal_mulai"] <= akhir.isoformat() and s["tanggal_terakhir"] >= mulai.isoformat()
    ]
    kelengkapan = _kelengkapan(konf, observasi, mulai, akhir)
    hari_raya = next(({"nama": a.nama, "tanggal": a.tanggal.isoformat(), "h_minus": (a.tanggal - akhir).days}
                      for a in konf.kalender if a.jenis == "hari_raya" and 0 <= (a.tanggal - akhir).days <= 30), None)
    drift = [s["varian"] for s in sinyal if s["jenis"] == "drift"] if terbaru else []
    dengan_perubahan = [b for b in baris_varian if b["vs_sebelumnya_persen"] is not None]
    teratas = sorted(dengan_perubahan, key=lambda b: -b["vs_sebelumnya_persen"])
    indeks = _indeks_sederhana(relatif)

    ringkasan = []
    if indeks is not None:
        arah = "naik" if indeks > 100 else "turun" if indeks < 100 else "stabil"
        ringkasan.append(f"Indeks harga pangan sederhana berada di {_a(indeks, 2)}, artinya harga secara umum {arah} "
                         f"{_a(abs(indeks - 100), 2)}% dibanding {s_label}.")
    if teratas:
        ringkasan.append(f"Kenaikan terbesar terjadi pada {teratas[0]['nama']} ({_a(teratas[0]['vs_sebelumnya_persen'], 1, True)}%), "
                         f"penurunan terbesar pada {teratas[-1]['nama']} ({_a(teratas[-1]['vs_sebelumnya_persen'], 1, True)}%).")
    status = Counter(s.get("status", "baru") for s in sinyal_periode if s["jenis"] == "anomali_harga")
    n_anomali = sum(status.values())
    if n_anomali:
        ringkasan.append(f"Ada {n_anomali} peringatan harga janggal pada periode ini, "
                         f"{status.get('ditindaklanjuti', 0) + status.get('selesai', 0)} di antaranya sudah ditindaklanjuti.")
    else:
        ringkasan.append("Tidak ada harga janggal pada periode ini.")
    if kelengkapan["rata_persen"] is not None:
        ringkasan.append(f"Rata-rata kelengkapan data pasar {_a(kelengkapan['rata_persen'])}%.")

    hasil = {
        "jenis": jenis, "judul": JUDUL[jenis], "label": label, "mulai": mulai.isoformat(), "akhir": akhir.isoformat(),
        "pembanding": {"sebelumnya": s_label, "tahun_lalu": y_label},
        "indeks_sederhana": indeks, "ringkasan": ringkasan, "varian": baris_varian,
        "kenaikan_teratas": [b["kode"] for b in teratas[:5] if b["vs_sebelumnya_persen"] > 0],
        "penurunan_teratas": [b["kode"] for b in reversed(teratas[-5:]) if b["vs_sebelumnya_persen"] < 0],
        "sinyal": [{k: s.get(k) for k in ("id", "jenis", "judul", "keparahan", "status", "tanggal_mulai",
                                          "tanggal_terakhir", "url_issue", "narasi")} for s in sinyal_periode],
        "status_sinyal": dict(status), "kelengkapan": kelengkapan, "hari_raya": hari_raya,
        "rekomendasi": _rekomendasi(konf, jenis, baris_varian, sinyal_periode, kelengkapan, hari_raya, drift),
        "periode_berjalan": akhir >= konf.hari_ini,
    }
    if terbaru:
        hasil.update(ekstra.get(jenis, {}))
    return hasil


def bentuk_semua(konf, harian_target: dict, hasil_varian: dict, sinyal: list[dict], observasi: list,
                 tanggal_data: date | None, ekstra: dict | None = None) -> dict:
    """Kembalikan {jenis: [periode terbaru dahulu]} untuk mingguan, bulanan, triwulanan, semesteran, tahunan."""
    if tanggal_data is None:
        return {j: [] for j in JUMLAH_PERIODE}
    ekstra = ekstra or {}
    hasil = {}
    for jenis, jumlah in JUMLAH_PERIODE.items():
        daftar = []
        mulai, akhir, label = _periode(jenis, tanggal_data)
        for k in range(jumlah):
            daftar.append(_satu_periode(jenis, konf, harian_target, hasil_varian, sinyal, observasi,
                                        mulai, akhir, label, k == 0, ekstra))
            mulai, akhir, label = _sebelumnya(jenis, mulai)
        hasil[jenis] = [d for d in daftar if d["varian"]]
    return hasil

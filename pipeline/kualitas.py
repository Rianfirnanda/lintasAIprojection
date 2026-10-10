"""Quality gate: deduplikasi, kewajaran, pencilan, rekonsiliasi, validasi manusia, dan ketepatan waktu.

Status observasi setelah quality gate:
  lolos            -> dipakai analisis
  divalidasi       -> sempat ditandai, lalu diterima validator (dipakai analisis)
  perlu_validasi   -> ditandai; menunggu keputusan validator (TIDAK dipakai analisis)
  ditolak_validator-> ditolak validator (tidak dipakai)
  duplikat         -> salinan identik, dibuang
"""

from __future__ import annotations

import csv
from bisect import insort
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from statistics import median

from .konfigurasi import Konfigurasi
from .masukan import Observasi

DIPAKAI = ("lolos", "divalidasi")

KETERANGAN_TANDA = {
    "duplikat_konflik": "Ada dua catatan untuk hari, pasar, varian, dan sumber yang sama, tetapi harganya berbeda",
    "di_luar_batas_wajar": "Harganya di luar batas wajar untuk varian ini (config/komoditas.csv)",
    "perubahan_ekstrem": "Harganya berubah terlalu jauh dari catatan sebelumnya di pasar yang sama",
    "pencilan_statistik": "Harganya jauh berbeda dari kebiasaan 28 hari terakhir di wilayah ini",
}


@dataclass
class Keputusan:
    keputusan: str  # terima | tolak
    alasan: str
    validator: str
    tanggal: str


@dataclass
class HasilKualitas:
    observasi: list[Observasi]
    jumlah_duplikat: int = 0
    rekonsiliasi: list[dict] = field(default_factory=list)
    ketepatan: dict = field(default_factory=dict)
    libur: set = field(default_factory=set)  # hari kerja tanpa pencatatan di semua pasar satu sumber (libur nasional, cuti bersama)

    def dipakai(self) -> list[Observasi]:
        return [o for o in self.observasi if o.status in DIPAKAI]

    def perlu_validasi(self) -> list[Observasi]:
        return [o for o in self.observasi if o.status == "perlu_validasi"]


def baca_keputusan(path: Path) -> dict[str, Keputusan]:
    """Baca data/validasi/*.csv berisi keputusan validator. Baris terakhir per id yang berlaku."""
    hasil: dict[str, Keputusan] = {}
    berkas = sorted(path.glob("*.csv")) if path.is_dir() else ([path] if path.exists() else [])
    for p in berkas:
        with p.open(newline="", encoding="utf-8-sig") as f:
            for b in csv.DictReader(f):
                oid = (b.get("id_observasi") or "").strip()
                kep = (b.get("keputusan") or "").strip().lower()
                if not oid or kep not in ("terima", "tolak"):
                    continue
                hasil[oid] = Keputusan(
                    keputusan=kep, alasan=(b.get("alasan") or "").strip(),
                    validator=(b.get("validator") or "").strip(),
                    tanggal=(b.get("tanggal_validasi") or "").strip(),
                )
    return hasil


def _robust_z(nilai: float, riwayat: list[float]) -> float:
    m = median(riwayat)
    mad = median(abs(x - m) for x in riwayat)
    skala = max(mad, 0.01 * m) / 0.6745  # batas bawah 1%: harga pasar dibulatkan (MAD sering 0)
    return (nilai - m) / skala if skala > 0 else 0.0


def jalankan(observasi: list[Observasi], konf: Konfigurasi, keputusan: dict[str, Keputusan]) -> HasilKualitas:
    aturan = konf.pengaturan["kualitas"]

    # 1. Deduplikasi: salinan identik (id sama) dan kiriman ulang formulir luring (id_klien sama).
    unik: list[Observasi] = []
    lihat_id: set[str] = set()
    lihat_klien: set[str] = set()
    duplikat = 0
    for o in sorted(observasi, key=lambda o: (o.tanggal, o.berkas, o.baris)):
        if o.id in lihat_id or (o.id_klien and o.id_klien in lihat_klien):
            duplikat += 1
            continue
        lihat_id.add(o.id)
        if o.id_klien:
            lihat_klien.add(o.id_klien)
        unik.append(o)

    # 2. Konflik kunci: kunci sama, harga berbeda.
    per_kunci: dict[tuple, list[Observasi]] = defaultdict(list)
    for o in unik:
        per_kunci[(o.tanggal, o.kode_pasar, o.kode_varian, o.kode_sumber, o.responden)].append(o)
    for kelompok in per_kunci.values():
        if len({o.harga for o in kelompok}) > 1:
            for o in kelompok:
                o.tanda.append("duplikat_konflik")

    # 3. Batas kewajaran.
    for o in unik:
        v = konf.varian[o.kode_varian]
        if not (v.batas_bawah <= o.harga <= v.batas_atas):
            o.tanda.append("di_luar_batas_wajar")

    # 4. Pemeriksaan temporal (kronologis, memakai riwayat yang sudah diterima).
    per_hari: dict[date, list[Observasi]] = defaultdict(list)
    for o in unik:
        per_hari[o.tanggal].append(o)

    terakhir_pasar: dict[tuple, tuple[date, float]] = {}
    riwayat_wilayah: dict[tuple, list] = defaultdict(list)  # terurut (tanggal, harga)
    tertunda: dict[tuple, Observasi] = {}  # observasi terakhir yang tertahan hanya karena tanda temporal
    z_ambang = aturan["z_pencilan"]
    toleransi = aturan["toleransi_konfirmasi_persen"] / 100
    temporal = {"perubahan_ekstrem", "pencilan_statistik"}

    def terima(o: Observasi) -> None:
        terakhir = terakhir_pasar.get((o.kode_pasar, o.kode_varian))
        if terakhir is None or o.tanggal >= terakhir[0]:
            terakhir_pasar[(o.kode_pasar, o.kode_varian)] = (o.tanggal, o.harga)
        insort(riwayat_wilayah[(o.kode_wilayah, o.kode_varian)], (o.tanggal, o.harga))

    def hanya_temporal(o: Observasi) -> bool:
        return bool(temporal & set(o.tanda)) and not (set(o.tanda) - temporal)

    for tgl in sorted(per_hari):
        harian = per_hari[tgl]
        for o in harian:
            v = konf.varian[o.kode_varian]
            ambang = aturan["ambang_perubahan_harian_persen"][v.kelompok] / 100
            sebelum = terakhir_pasar.get((o.kode_pasar, o.kode_varian))
            if sebelum and (tgl - sebelum[0]).days <= 14:
                if abs(o.harga / sebelum[1] - 1) > ambang:
                    o.tanda.append("perubahan_ekstrem")
            riw = riwayat_wilayah[(o.kode_wilayah, o.kode_varian)]
            while riw and (tgl - riw[0][0]).days > 28:
                riw.pop(0)
            jendela = [x for t, x in riw if t < tgl]
            if len(jendela) >= 8:
                if abs(_robust_z(o.harga, jendela)) > z_ambang:
                    o.tanda.append("pencilan_statistik")

        # Konfirmasi silang: lonjakan yang didukung observasi independen (pasar/responden lain) pada hari
        # yang sama dianggap nyata, bukan salah catat -> tanda temporal dilepas agar sinyal tidak tertahan.
        for o in harian:
            if not hanya_temporal(o):
                continue
            pendukung = [
                p for p in harian
                if p is not o and p.kode_varian == o.kode_varian and p.kode_wilayah == o.kode_wilayah
                and (p.kode_pasar, p.responden) != (o.kode_pasar, o.responden)
                and abs(p.harga / o.harga - 1) <= toleransi
            ]
            if pendukung:
                o.tanda = [t for t in o.tanda if t not in temporal] + ["lonjakan_terkonfirmasi"]

        # Konfirmasi persistensi: level baru yang bertahan pada observasi berikutnya dari pasar & responden yang
        # sama (mis. pasar pembanding dengan satu responden) dianggap perubahan nyata -> keduanya dilepas.
        for o in harian:
            kunci = (o.kode_pasar, o.kode_varian, o.responden)
            sebelum = tertunda.pop(kunci, None)
            if sebelum and (hanya_temporal(o) or "lonjakan_terkonfirmasi" in o.tanda) \
                    and abs(o.harga / sebelum.harga - 1) <= toleransi \
                    and sebelum.status == "perlu_validasi" and sebelum.id not in keputusan:
                for x in (sebelum, o):
                    x.tanda = [t for t in x.tanda if t not in temporal] + ["lonjakan_terkonfirmasi"]
                sebelum.status = "lolos"
                terima(sebelum)

        for o in harian:
            blokir = [t for t in o.tanda if t != "lonjakan_terkonfirmasi"]
            kep = keputusan.get(o.id)
            if kep and kep.keputusan == "tolak":
                o.status = "ditolak_validator"
            elif kep and kep.keputusan == "terima":
                o.status = "divalidasi" if blokir else "lolos"
            elif blokir:
                o.status = "perlu_validasi"
            else:
                o.status = "lolos"
            if o.status in DIPAKAI:
                terima(o)
            elif o.status == "perlu_validasi" and hanya_temporal(o):
                tertunda[(o.kode_pasar, o.kode_varian, o.responden)] = o

    hasil = HasilKualitas(observasi=unik, jumlah_duplikat=duplikat)
    hasil.rekonsiliasi = rekonsiliasi(hasil.dipakai(), konf)
    hasil.libur = libur_pencatatan(unik)
    hasil.ketepatan = ketepatan_waktu(unik, konf, hasil.libur)
    return hasil


def libur_pencatatan(observasi: list[Observasi]) -> set[date]:
    """Hari kerja (Senin-Jumat) tanpa satu pun catatan dari sumber yang mencatat di beberapa pasar (mis. SP2KP: tiga pasar
    di tiga kabupaten/kota), dalam rentang data sumber itu. Bila semua pasar sumber yang sama kosong pada hari yang sama,
    hari itu libur pencatatan (libur nasional atau cuti bersama), bukan data hilang. Terdeteksi dari data, tanpa daftar manual."""
    pasar: dict[str, set] = defaultdict(set)
    tanggal: dict[str, set] = defaultdict(set)
    for o in observasi:
        if o.status != "ditolak_validator":
            pasar[o.kode_sumber].add(o.kode_pasar)
            tanggal[o.kode_sumber].add(o.tanggal)
    libur: set[date] = set()
    for sumber, ps in pasar.items():
        if len(ps) < 2:
            continue
        ada = tanggal[sumber]
        d, akhir = min(ada), max(ada)
        while d <= akhir:
            if d.weekday() < 5 and d not in ada:
                libur.add(d)
            d += timedelta(days=1)
    return libur


def rekonsiliasi(observasi: list[Observasi], konf: Konfigurasi) -> list[dict]:
    """Bandingkan median antar-sumber untuk tanggal-wilayah-varian yang sama."""
    batas = konf.pengaturan["kualitas"]["selisih_rekonsiliasi_persen"]
    grup: dict[tuple, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for o in observasi:
        grup[(o.tanggal, o.kode_wilayah, o.kode_varian)][o.kode_sumber].append(o.harga)
    hasil = []
    for (tgl, wil, var), per_sumber in grup.items():
        if len(per_sumber) < 2:
            continue
        med = {s: median(h) for s, h in per_sumber.items()}
        rendah, tinggi = min(med.values()), max(med.values())
        selisih = (tinggi / rendah - 1) * 100
        dipakai = min(med, key=konf.prioritas_sumber)
        hasil.append({
            "tanggal": tgl.isoformat(), "kode_wilayah": wil, "kode_varian": var,
            "median_per_sumber": {s: round(v) for s, v in sorted(med.items())},
            "selisih_persen": round(selisih, 2), "melebihi_batas": selisih > batas,
            "sumber_dipakai": dipakai,
        })
    hasil.sort(key=lambda r: (r["tanggal"], r["kode_varian"]), reverse=True)
    return hasil


def hari_wajib(konf: Konfigurasi, mulai: date, akhir: date, libur_data: set[date] | None = None) -> list[date]:
    hari = konf.pengaturan["hari_pencatatan"]
    libur = {a.tanggal for a in konf.kalender if a.jenis in ("hari_raya", "libur_nasional")} | (libur_data or set())
    hasil = []
    d = mulai
    while d <= akhir:
        if d.weekday() in hari and d not in libur:
            hasil.append(d)
        d += timedelta(days=1)
    return hasil


def ketepatan_waktu(observasi: list[Observasi], konf: Konfigurasi, libur_data: set[date] | None = None) -> dict:
    """Kelengkapan & ketepatan waktu pengiriman per pasar di wilayah target (jendela N hari terakhir)."""
    jendela = konf.pengaturan["kualitas"]["jendela_evaluasi_ketepatan_hari"]
    jam_batas = konf.pengaturan["jam_batas_tepat_waktu"]
    akhir = konf.hari_ini - timedelta(days=1)  # hari ini belum selesai
    mulai = akhir - timedelta(days=jendela - 1)
    wajib = set(hari_wajib(konf, mulai, akhir, libur_data))
    varian = [v.kode for v in konf.varian_aktif]

    diterima: dict[tuple, Observasi] = {}
    terakhir: dict[str, date] = {}
    for o in observasi:
        if o.status == "ditolak_validator":
            continue
        terakhir[o.kode_pasar] = max(terakhir.get(o.kode_pasar, o.tanggal), o.tanggal)
        if o.tanggal in wajib and o.kode_varian in varian:
            kunci = (o.kode_pasar, o.tanggal, o.kode_varian)
            if kunci not in diterima:
                diterima[kunci] = o

    per_pasar = []
    total_harap = total_terima = total_tepat = total_diketahui = 0
    tanpa_sumber = []
    for p in konf.pasar_di(konf.wilayah_target):
        if p.kode not in terakhir:
            # Pasar belum punya sumber data sama sekali (mis. menunggu pencatatan petugas): dicatat terpisah, tidak
            # dirata-rata, supaya kelengkapan pasar yang sudah dicatat tidak tertutup angka nol.
            tanpa_sumber.append(p.nama)
            per_pasar.append({"kode_pasar": p.kode, "nama_pasar": p.nama, "blank_spot": p.blank_spot, "diharapkan": len(wajib) * len(varian),
                              "diterima": 0, "kelengkapan_persen": 0.0, "ketepatan_persen": None, "waktu_input_tercatat": 0,
                              "tanggal_terakhir": None, "belum_ada_sumber": True})
            continue
        harap = len(wajib) * len(varian)
        obs = [o for (kp, _, _), o in diterima.items() if kp == p.kode]
        terima = len(obs)
        diketahui = [o for o in obs if o.waktu_input is not None]
        tepat = sum(
            1 for o in diketahui
            if o.waktu_input.replace(tzinfo=None) <= datetime.combine(o.tanggal, time(jam_batas))
        )
        per_pasar.append({
            "kode_pasar": p.kode, "nama_pasar": p.nama, "blank_spot": p.blank_spot,
            "diharapkan": harap, "diterima": terima,
            "kelengkapan_persen": round(terima / harap * 100, 1) if harap else None,
            "ketepatan_persen": round(tepat / len(diketahui) * 100, 1) if diketahui else None,
            "waktu_input_tercatat": len(diketahui),
            "tanggal_terakhir": terakhir[p.kode].isoformat() if p.kode in terakhir else None,
        })
        total_harap += harap
        total_terima += terima
        total_tepat += tepat
        total_diketahui += len(diketahui)
    return {
        "periode": {"mulai": mulai.isoformat(), "akhir": akhir.isoformat(), "hari_wajib": len(wajib)},
        "kelengkapan_persen": round(total_terima / total_harap * 100, 1) if total_harap else None,
        "ketepatan_persen": round(total_tepat / total_diketahui * 100, 1) if total_diketahui else None,
        "per_pasar": per_pasar, "pasar_tanpa_sumber": tanpa_sumber, "hari_libur_terdeteksi": sorted(d.isoformat() for d in (libur_data or set())
                                                                                             if mulai <= d <= akhir),
    }

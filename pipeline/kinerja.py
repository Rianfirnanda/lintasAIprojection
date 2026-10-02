"""Indikator kinerja (SMART, Tabel 1 & 5 Rancangan Aksi Perubahan) yang dapat dihitung otomatis dari data sistem.

Indikator yang tidak dapat diukur dari data sistem tetap ditampilkan dengan status "diukur_manual" agar kekurangannya
terlihat, bukan disembunyikan. Dengan login Google (Firebase), pemakaian sistem diukur dari akun yang aktif.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median

from .kualitas import DIPAKAI

STATUS_TANGGAPAN = ("terverifikasi", "false_alarm", "ditindaklanjuti", "selesai")
KOREKSI = ("perlu_validasi", "divalidasi", "ditolak_validator")


# ---------------------------------------------------------------- persetujuan model

def baca_persetujuan(folder: Path) -> dict[str, dict]:
    """data/persetujuan_model/*.csv: kode_varian,model,keputusan(setuju|tolak),penyetuju,tanggal,catatan.

    Kembalikan per varian: model yang saat ini disetujui (baris terbaru yang berlaku) beserta jejaknya.
    """
    baris = []
    for p in sorted(folder.glob("*.csv")) if folder.exists() else []:
        with p.open(newline="", encoding="utf-8-sig") as f:
            for b in csv.DictReader(f):
                b = {k.strip(): (v or "").strip() for k, v in b.items() if k}
                if b.get("kode_varian") and b.get("model") and b.get("keputusan") in ("setuju", "tolak"):
                    baris.append(b)
    baris.sort(key=lambda b: b.get("tanggal", ""))
    hasil: dict[str, dict] = {}
    for b in baris:
        kode = b["kode_varian"].upper()
        lama = hasil.get(kode, {"model": None, "riwayat": []})
        riwayat = lama["riwayat"] + [b]
        if b["keputusan"] == "setuju":
            hasil[kode] = {"model": b["model"], "penyetuju": b.get("penyetuju", ""), "tanggal": b.get("tanggal", ""),
                           "riwayat": riwayat}
        else:
            model = None if lama["model"] == b["model"] else lama["model"]
            hasil[kode] = {**lama, "model": model, "riwayat": riwayat}
    return hasil


# ---------------------------------------------------------------- koreksi supervisor

def koreksi_supervisor(observasi: list, hari_ini: date) -> dict:
    """Proporsi observasi yang memerlukan campur tangan supervisor (ditahan quality gate) per bulan."""
    per_bulan: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for o in observasi:
        kunci = o.tanggal.strftime("%Y-%m")
        per_bulan[kunci][0] += 1
        per_bulan[kunci][1] += o.status in KOREKSI
    seri = [
        {"bulan": b, "observasi": n, "koreksi": k, "persen": round(k / n * 100, 3) if n else None}
        for b, (n, k) in sorted(per_bulan.items())
    ]
    lengkap = [s for s in seri if s["bulan"] < hari_ini.strftime("%Y-%m") and s["observasi"] >= 50]
    if len(lengkap) < 2:
        return {"per_bulan": seri, "acuan": None, "terkini": None, "perubahan_persen": None,
                "catatan": "Butuh data minimal dua bulan penuh supaya bisa dibandingkan."}
    acuan, terkini = lengkap[0], lengkap[-1]
    perubahan = round((terkini["persen"] / acuan["persen"] - 1) * 100, 1) if acuan["persen"] else None
    return {"per_bulan": seri, "acuan": acuan, "terkini": terkini, "perubahan_persen": perubahan}


# ---------------------------------------------------------------- waktu respons tindak lanjut

def _ke_tanggal(nilai: str | None) -> datetime | None:
    if not nilai:
        return None
    try:
        t = datetime.fromisoformat(nilai.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def waktu_respons(sinyal: list[dict], buku: dict, status_issue: dict, hari_ini: date, jumlah_acuan: int = 10) -> dict:
    """Hari dari sinyal muncul sampai pertama kali mendapat status tanggapan (terverifikasi/false alarm/dst)."""
    catatan: list[tuple[datetime, float, str]] = []
    terhitung: set[str] = set()
    for sid, gi in status_issue.items():
        mulai, respons = _ke_tanggal(gi.get("dibuat")), _ke_tanggal(gi.get("direspons"))
        if mulai and respons and respons >= mulai:
            catatan.append((respons, (respons - mulai).total_seconds() / 86400, sid))
            terhitung.add(sid)
    mulai_sinyal = {s["id"]: s.get("tanggal_mulai") for s in sinyal}
    for sid, c in buku.items():
        if sid in terhitung or sid not in mulai_sinyal:
            continue
        pertama = next((r for r in c.riwayat if r["status"] in STATUS_TANGGAPAN), None)
        mulai, respons = _ke_tanggal(mulai_sinyal[sid]), _ke_tanggal(pertama["tanggal"]) if pertama else None
        if mulai and respons and respons >= mulai:
            catatan.append((respons, (respons - mulai).total_seconds() / 86400, sid))
    catatan.sort()
    hasil = {"jumlah_respons": len(catatan), "median_hari_semua": round(median(c[1] for c in catatan), 2) if catatan else None}
    if len(catatan) < jumlah_acuan + 3:
        hasil["catatan"] = (f"Butuh minimal {jumlah_acuan + 3} peringatan yang sudah ditanggapi supaya bisa dibandingkan "
                            f"({jumlah_acuan} tanggapan pertama dibanding yang terbaru).")
        hasil.update({"median_hari_acuan": None, "median_hari_terkini": None, "perbaikan_persen": None})
        return hasil
    acuan = catatan[:jumlah_acuan]
    batas = datetime.combine(hari_ini - timedelta(days=90), datetime.min.time(), tzinfo=timezone.utc)
    terkini = [c for c in catatan[jumlah_acuan:] if c[0] >= batas] or catatan[jumlah_acuan:]
    m_acuan, m_kini = median(c[1] for c in acuan), median(c[1] for c in terkini)
    hasil.update({
        "median_hari_acuan": round(m_acuan, 2), "median_hari_terkini": round(m_kini, 2),
        "perbaikan_persen": round((m_acuan - m_kini) / m_acuan * 100, 1) if m_acuan > 0 else None,
    })
    return hasil


# ---------------------------------------------------------------- stabilitas antar-segmen

def stabilitas_segmen(hasil_varian: dict, varian: dict) -> dict:
    """Rasio sMAPE model terpilih terhadap model naif per kelompok komoditas dan per kondisi (normal/hari raya).

    Rasio < 1 = lebih baik dari baseline. Target Rancangan: tidak ada segmen yang lebih buruk dari baseline dan
    selisih kinerja antarsegmen maksimal 20%.
    """
    per_kelompok: dict[str, list[float]] = defaultdict(list)
    kondisi: dict[str, list[float]] = defaultdict(list)
    for kode, hv in hasil_varian.items():
        m = hv.metrik_model
        if hv.model_terpilih in m and "naif" in m and m["naif"]["smape"] > 0:
            per_kelompok[varian[kode].kelompok].append(m[hv.model_terpilih]["smape"] / m["naif"]["smape"])
        seg = hv.segmen
        for nama in ("normal", "hari_raya"):
            t, n = seg.get("terpilih", {}).get(nama), seg.get("naif", {}).get(nama)
            if t is not None and n:
                kondisi[nama].append(t / n)
    segmen = {f"kelompok:{k}": round(mean(v), 3) for k, v in per_kelompok.items() if v}
    segmen.update({f"kondisi:{k}": round(mean(v), 3) for k, v in kondisi.items() if v})
    if not segmen:
        return {"rasio_vs_naif": {}, "gap_persen": None, "lebih_buruk_dari_baseline": [],
                "catatan": "Belum ada varian yang sudah diuji."}
    nilai = list(segmen.values())
    return {
        "rasio_vs_naif": segmen,
        "gap_persen": round((max(nilai) / min(nilai) - 1) * 100, 1) if min(nilai) > 0 else None,
        "lebih_buruk_dari_baseline": sorted(k for k, v in segmen.items() if v > 1.0),
    }


# ---------------------------------------------------------------- uptime

def ringkas_uptime(path: Path, hari_ini: date, hari: int = 30) -> dict:
    """Ringkas log uptime (dibuat workflow uptime.yml di cabang log-uptime)."""
    if not path.exists():
        return {"catatan": "Catatan pemeriksaan dashboard belum ada. Isinya muncul setelah pemeriksaan otomatis berjalan."}
    with path.open(newline="", encoding="utf-8") as f:
        baris = list(csv.DictReader(f))
    batas = hari_ini - timedelta(days=hari)
    cek = []
    for b in baris:
        t = _ke_tanggal(b.get("waktu_utc"))
        if not t or t.date() <= batas:
            continue
        ok = b.get("http_halaman") == "200" and b.get("http_data") == "200"
        lat = float(b["latensi_ms"]) if (b.get("latensi_ms") or "").replace(".", "", 1).isdigit() else None
        cek.append((t, ok, lat))
    if not cek:
        return {"catatan": f"Belum ada pemeriksaan dashboard dalam {hari} hari terakhir."}
    insiden, gagal_sebelum = 0, False
    for _, ok, _ in cek:
        if not ok and not gagal_sebelum:
            insiden += 1
        gagal_sebelum = not ok
    per_hari: dict[str, list[bool]] = defaultdict(list)
    for t, ok, _ in cek:
        per_hari[t.date().isoformat()].append(ok)
    latensi = [x for _, _, x in cek if x is not None]
    return {
        "periode_hari": hari, "jumlah_cek": len(cek), "berhasil": sum(ok for _, ok, _ in cek),
        "uptime_persen": round(sum(ok for _, ok, _ in cek) / len(cek) * 100, 2), "insiden": insiden,
        "latensi_median_ms": round(median(latensi)) if latensi else None,
        "cek_terakhir": cek[-1][0].isoformat(), "terakhir_ok": cek[-1][1],
        "per_hari": [{"tanggal": d, "uptime_persen": round(sum(v) / len(v) * 100, 1), "cek": len(v)}
                     for d, v in sorted(per_hari.items())],
    }


# ---------------------------------------------------------------- respons pedagang dan adopsi

STATUS_TIDAK_BERHASIL = ("menolak", "tidak_ada", "tutup")
TARGET_ADOPSI = ((3, 35), (6, 60), (12, 80), (10 ** 6, 95))  # (sampai bulan ke-, target %) Tabel 23


def baca_kunjungan(folder: Path) -> list[dict]:
    """data/kunjungan/*.csv: kunjungan ke pedagang yang tidak menghasilkan harga (menolak, tidak ada, tutup)."""
    hasil = {}
    for p in sorted(folder.rglob("*.csv")) if folder.is_dir() else []:
        with p.open(newline="", encoding="utf-8-sig") as f:
            for b in csv.DictReader(f):
                b = {k.strip(): (v or "").strip() for k, v in b.items() if k}
                if b.get("id") and b.get("status") in STATUS_TIDAK_BERHASIL and _ke_tanggal(b.get("tanggal")):
                    hasil[b["id"]] = b
    return list(hasil.values())


def respons_pedagang(observasi: list, kunjungan: list[dict], hari_ini: date, hari: int = 30) -> dict:
    """Tabel 25: respons pedagang = wawancara berhasil / seluruh kunjungan; penolakan = menolak / seluruh kunjungan.

    Wawancara berhasil dihitung dari harga yang dicatat petugas di pasar (sumber PSR-ENUM): satu pedagang per pasar per
    hari. Kunjungan yang gagal dicatat petugas di halaman Catat Harga.
    """
    mulai = hari_ini - timedelta(days=hari - 1)
    berhasil = {(o.tanggal, o.kode_pasar, o.responden or o.petugas or "-") for o in observasi
                if o.kode_sumber == "PSR-ENUM" and mulai <= o.tanggal <= hari_ini}
    gagal = [k for k in kunjungan if mulai <= _ke_tanggal(k["tanggal"]).date() <= hari_ini]
    total = len(berhasil) + len(gagal)
    alasan: dict[str, int] = defaultdict(int)
    for k in gagal:
        if k["status"] == "menolak":
            alasan[k.get("alasan") or "tidak disebut"] += 1
    return {
        "periode_hari": hari, "berhasil": len(berhasil), "menolak": sum(1 for k in gagal if k["status"] == "menolak"),
        "tidak_ada": sum(1 for k in gagal if k["status"] in ("tidak_ada", "tutup")), "total": total,
        "respons_persen": round(len(berhasil) / total * 100, 1) if total else None,
        "penolakan_persen": round(sum(1 for k in gagal if k["status"] == "menolak") / total * 100, 1) if total else None,
        "alasan_penolakan": dict(sorted(alasan.items(), key=lambda x: -x[1])),
        "catatan": "" if total else "Belum ada kunjungan pedagang yang tercatat.",
    }


def adopsi(path: Path, hari_ini: date) -> dict:
    """Tabel 23: akun aktif yang memakai sistem dalam 30 hari terakhir dibanding akun yang disetujui.

    data/adopsi.json ditulis mesin dari daftar akun Firestore (hanya angka ringkas, tanpa nama atau email).
    """
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"persen": None, "catatan": "Belum ada data pemakaian. Terisi otomatis bila situs memakai login Google."}
    akun, aktif = d.get("akun_aktif") or 0, d.get("aktif_30_hari") or 0
    mulai = _ke_tanggal(d.get("mulai"))
    bulan = ((hari_ini - mulai.date()).days // 30 + 1) if mulai else 1
    target = next(tg for batas, tg in TARGET_ADOPSI if bulan <= batas)
    return {**d, "persen": round(aktif / akun * 100, 1) if akun else None, "bulan_ke": bulan, "target_persen": target,
            "catatan": f"Bulan ke-{bulan} sejak akun pertama disetujui; target tahap ini {target}%."}


# ---------------------------------------------------------------- rangkuman SMART

def _status(nilai, target, arah: str) -> str:
    if nilai is None:
        return "belum_dapat_dinilai"
    if arah == ">=":
        return "memenuhi" if nilai >= target else "belum_memenuhi"
    return "memenuhi" if nilai <= target else "belum_memenuhi"


def indikator_smart(konf, hasil_qc, hasil_masuk, ringkasan_model: dict, evaluasi: dict, sinyal: list[dict],
                    respons: dict, koreksi: dict, stabilitas: dict, uptime: dict, persetujuan: dict,
                    layanan: dict | None = None, tambahan: dict | None = None) -> list[dict]:
    tk = konf.pengaturan["target_kinerja"]
    aktif = konf.varian_aktif
    lengkap = sum(1 for v in aktif if v.satuan and v.batas_bawah and v.batas_atas and v.kode_komoditas)
    batch = hasil_masuk.batch
    blank_spot = [p for p in konf.pasar_di(konf.wilayah_target) if p.blank_spot]
    ada_data = {o.kode_pasar for o in hasil_qc.observasi if o.status in DIPAKAI}
    anomali_tinggi = [s for s in sinyal if s["jenis"] == "anomali_harga" and s["keparahan"] == "tinggi"]
    ditanggapi = sum(1 for s in anomali_tinggi if s["status"] in STATUS_TANGGAPAN)
    ditindak = sum(1 for s in anomali_tinggi if s["status"] in ("ditindaklanjuti", "selesai"))
    dinilai = ringkasan_model.get("varian_dinilai") or 0
    layanan = layanan or {}
    tambahan = tambahan or {}
    pedagang = tambahan.get("respons_pedagang") or {}
    pakai = tambahan.get("adopsi") or {}
    kbj = tambahan.get("kebijakan") or {}

    def i(kode, sasaran, indikator, nilai, target, status, bukti, catatan="", satuan="%"):
        return {"kode": kode, "sasaran": sasaran, "indikator": indikator, "nilai": nilai, "target": target,
                "satuan": satuan, "status": status, "sumber_bukti": bukti, "catatan": catatan}

    persen = lambda a, b: round(a / b * 100, 1) if b else None  # noqa: E731
    daftar = [
        i("S1", "Data baku dan harga normal", "Varian yang sudah punya definisi, satuan, dan batas harga wajar",
          persen(lengkap, len(aktif)), 100, _status(persen(lengkap, len(aktif)), 100, ">="), "config/komoditas.csv"),
        i("S2", "Data baku dan harga normal", "Berkas masuk yang sudah tercatat dan bisa dilacak",
          persen(sum(1 for b in batch if b.sha256), len(batch)), 100,
          _status(persen(sum(1 for b in batch if b.sha256), len(batch)), 100, ">="), "Halaman Cek Data"),
        i("M1", "Mutu dan ketepatan waktu", "Data dikirim tepat waktu (30 hari terakhir)",
          hasil_qc.ketepatan.get("ketepatan_persen"), tk["ketepatan_waktu_persen"],
          _status(hasil_qc.ketepatan.get("ketepatan_persen"), tk["ketepatan_waktu_persen"], ">="), "Waktu pengisian di formulir Catat Harga"),
        i("M2", "Mutu dan ketepatan waktu", "Perubahan jumlah koreksi dari supervisor (bulan ini dibanding awal)",
          koreksi.get("perubahan_persen"), -30, _status(koreksi.get("perubahan_persen"), -30, "<="),
          "Keputusan validator dan antrean Cek Data", koreksi.get("catatan", "")),
        i("B1", "Jangkauan wilayah blank spot", "Pasar blank spot yang sudah mengirim data",
          f"{sum(1 for p in blank_spot if p.kode in ada_data)}/{len(blank_spot)}" if blank_spot else None, "8/8",
          ("memenuhi" if blank_spot and all(p.kode in ada_data for p in blank_spot) and len(blank_spot) >= 8 else
           "belum_dapat_dinilai" if not blank_spot else "belum_memenuhi"),
          "config/pasar.csv (kolom blank_spot)",
          "" if blank_spot else "Delapan wilayah blank spot belum ditandai di config/pasar.csv.", satuan=""),
        i("A1", "Kinerja prakiraan AI", "Varian yang prakiraannya minimal 10% lebih tepat dari cara sederhana",
          persen(ringkasan_model.get("lolos_smape", 0), dinilai), 100,
          _status(persen(ringkasan_model.get("lolos_smape", 0), dinilai), 100, ">="), "Halaman Akurasi"),
        i("A2", "Kinerja prakiraan AI", "Varian yang prakiraannya tidak condong lebih dari 5%", persen(ringkasan_model.get("lolos_bias", 0), dinilai),
          100, _status(persen(ringkasan_model.get("lolos_bias", 0), dinilai), 100, ">="), "Halaman Akurasi"),
        i("A3", "Kinerja prakiraan AI", "Nilai gabungan peringatan harga janggal (F1)", evaluasi.get("f1"), tk["f1_min"],
          _status(evaluasi.get("f1"), tk["f1_min"], ">="), evaluasi.get("sumber_label", ""), satuan=""),
        i("A4", "Kinerja prakiraan AI", "Lonjakan harga penting yang tertangkap (recall)", evaluasi.get("recall"), tk["recall_min"],
          _status(evaluasi.get("recall"), tk["recall_min"], ">="), evaluasi.get("sumber_label", ""), satuan=""),
        i("A5", "Kinerja prakiraan AI", "Peringatan yang salah (false alarm)", evaluasi.get("false_positive_rate"), tk["fpr_maks"],
          _status(evaluasi.get("false_positive_rate"), tk["fpr_maks"], "<="), evaluasi.get("sumber_label", ""), satuan=""),
        i("A6", "Kinerja prakiraan AI", "Selisih ketepatan antar kelompok komoditas (paling besar)", stabilitas.get("gap_persen"), 20,
          ("belum_memenuhi" if stabilitas.get("lebih_buruk_dari_baseline") else
           _status(stabilitas.get("gap_persen"), 20, "<=")), "Uji data lama per kelompok dan masa hari raya",
          ("Kelompok yang lebih buruk dari cara sederhana: " + ", ".join(stabilitas["lebih_buruk_dari_baseline"]))
          if stabilitas.get("lebih_buruk_dari_baseline") else stabilitas.get("catatan", "")),
        i("L1", "Keandalan layanan", "Dashboard bisa dibuka (30 hari terakhir)", uptime.get("uptime_persen"), 99.5,
          _status(uptime.get("uptime_persen"), 99.5, ">="), "Pemeriksaan otomatis tiap jam", uptime.get("catatan", "")),
        (i("D1", "Pemakaian di lapangan", "Akun yang memakai sistem dalam 30 hari terakhir", pakai["persen"],
           pakai["target_persen"], _status(pakai["persen"], pakai["target_persen"], ">="), "Catatan akun aktif (login Google)",
           pakai.get("catatan", "")) if pakai.get("persen") is not None else
         i("D1", "Pemakaian di lapangan", "Seberapa banyak SOP dan dashboard dipakai", None, "35% → 95%", "diukur_manual",
           "Catatan pemakaian, survei kesiapan", pakai.get("catatan") or
           "Diukur lewat survei kesiapan dan berita acara evaluasi.")),
        i("K1", "Komunikasi dan partisipasi", "Kepuasan pengguna (Indeks Kepuasan Masyarakat)", layanan.get("ikm"), 76.61,
          _status(layanan.get("ikm"), 76.61, ">="), "Survei kepuasan (Issue Forms)", layanan.get("catatan_ikm", ""), satuan=""),
        i("K2", "Komunikasi dan partisipasi", "Pengaduan data yang sudah ditanggapi", layanan.get("pengaduan_ditanggapi_persen"),
          100, _status(layanan.get("pengaduan_ditanggapi_persen"), 100, ">="), "Pengaduan (Issue Forms)",
          layanan.get("catatan_pengaduan", "")),
        i("K3", "Komunikasi dan partisipasi", "Pedagang yang bersedia diwawancarai (30 hari terakhir)",
          pedagang.get("respons_persen"), 85, _status(pedagang.get("respons_persen"), 85, ">="),
          "Catat Harga: harga tercatat dan kunjungan yang gagal", pedagang.get("catatan", "")),
        i("K4", "Komunikasi dan partisipasi", "Pedagang yang menolak diwawancarai (30 hari terakhir)",
          pedagang.get("penolakan_persen"), 10, _status(pedagang.get("penolakan_persen"), 10, "<="),
          "Catat Harga: kunjungan yang gagal", pedagang.get("catatan", "")),
        i("T1", "Dipakai oleh TPID", "Peringatan penting yang sudah ditindaklanjuti", persen(ditindak, len(anomali_tinggi)),
          tk["tindak_lanjut_sinyal_persen"], _status(persen(ditindak, len(anomali_tinggi)), tk["tindak_lanjut_sinyal_persen"], ">="),
          "GitHub Issues atau buku tindak lanjut"),
        i("T2", "Dipakai oleh TPID", "Respons tindak lanjut makin cepat dibanding awal", respons.get("perbaikan_persen"), 20,
          _status(respons.get("perbaikan_persen"), 20, ">="), "Riwayat status peringatan", respons.get("catatan", "")),
        i("T3", "Dipakai oleh TPID", "Rapat TPID yang membahas data, triwulan ini", kbj.get("rapat_triwulan_ini"), 1,
          _status(kbj.get("rapat_triwulan_ini"), 1, ">=") if kbj else "belum_dapat_dinilai", "Halaman Kebijakan: catatan rapat",
          "" if kbj.get("rapat_triwulan_ini") else "Catat rapat TPID di halaman Kebijakan.", satuan=" rapat"),
        i("I1", "Keandalan dan pengawasan", "Peringatan berisiko tinggi yang sudah dicek manusia",
          persen(ditanggapi, len(anomali_tinggi)), 100, _status(persen(ditanggapi, len(anomali_tinggi)), 100, ">="),
          "Status peringatan"),
        i("I2", "Keandalan dan pengawasan", "Cara prakiraan yang dipakai sudah disetujui manusia",
          persen(sum(1 for s in persetujuan.values() if s == "disetujui"), len(persetujuan)), 100,
          _status(persen(sum(1 for s in persetujuan.values() if s == "disetujui"), len(persetujuan)), 100, ">="),
          "data/persetujuan_model/"),
        i("I3", "Keandalan dan pengawasan", "Rekomendasi berisiko tinggi yang sudah diputuskan manusia",
          persen(kbj.get("rekomendasi_tinggi_diputuskan", 0), kbj.get("rekomendasi_tinggi", 0)), 100,
          _status(persen(kbj.get("rekomendasi_tinggi_diputuskan", 0), kbj.get("rekomendasi_tinggi", 0)), 100, ">="),
          "Halaman Kebijakan: persetujuan rekomendasi",
          "" if kbj.get("rekomendasi_tinggi") else "Belum ada rekomendasi berisiko tinggi."),
    ]
    return daftar

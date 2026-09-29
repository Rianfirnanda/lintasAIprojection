"""Indikator kinerja (SMART, Tabel 1 & 5 Rancangan Aksi Perubahan) yang dapat dihitung otomatis dari data sistem.

Indikator yang tidak dapat diukur dari data sistem (mis. adopsi/log penggunaan di GitHub Pages) tetap ditampilkan
dengan status "diukur_manual" agar kekurangannya terlihat, bukan disembunyikan.
"""

from __future__ import annotations

import csv
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
                "catatan": "Butuh minimal dua bulan penuh data untuk dibandingkan."}
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
        hasil["catatan"] = (f"Butuh minimal {jumlah_acuan + 3} sinyal yang sudah ditanggapi untuk membandingkan periode acuan "
                            f"({jumlah_acuan} tanggapan pertama) dengan periode terkini.")
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
                "catatan": "Belum ada varian dengan backtest."}
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
        return {"catatan": "Log uptime belum tersedia (workflow Uptime belum berjalan)."}
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
        return {"catatan": f"Belum ada pemeriksaan uptime dalam {hari} hari terakhir."}
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


# ---------------------------------------------------------------- rangkuman SMART

def _status(nilai, target, arah: str) -> str:
    if nilai is None:
        return "belum_dapat_dinilai"
    if arah == ">=":
        return "memenuhi" if nilai >= target else "belum_memenuhi"
    return "memenuhi" if nilai <= target else "belum_memenuhi"


def indikator_smart(konf, hasil_qc, hasil_masuk, ringkasan_model: dict, evaluasi: dict, sinyal: list[dict],
                    respons: dict, koreksi: dict, stabilitas: dict, uptime: dict, persetujuan: dict,
                    layanan: dict | None = None) -> list[dict]:
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

    def i(kode, sasaran, indikator, nilai, target, status, bukti, catatan="", satuan="%"):
        return {"kode": kode, "sasaran": sasaran, "indikator": indikator, "nilai": nilai, "target": target,
                "satuan": satuan, "status": status, "sumber_bukti": bukti, "catatan": catatan}

    persen = lambda a, b: round(a / b * 100, 1) if b else None  # noqa: E731
    daftar = [
        i("S1", "Standardisasi & baseline", "Varian aktif dengan definisi, satuan, dan batas kewajaran",
          persen(lengkap, len(aktif)), 100, _status(persen(lengkap, len(aktif)), 100, ">="), "config/komoditas.csv"),
        i("S2", "Standardisasi & baseline", "Berkas masukan tercatat metadata (checksum SHA-256)",
          persen(sum(1 for b in batch if b.sha256), len(batch)), 100,
          _status(persen(sum(1 for b in batch if b.sha256), len(batch)), 100, ">="), "Halaman Quality Gate"),
        i("M1", "Mutu & ketepatan waktu", "Ketepatan waktu pengiriman data (30 hari)",
          hasil_qc.ketepatan.get("ketepatan_persen"), tk["ketepatan_waktu_persen"],
          _status(hasil_qc.ketepatan.get("ketepatan_persen"), tk["ketepatan_waktu_persen"], ">="), "waktu_input formulir"),
        i("M2", "Mutu & ketepatan waktu", "Perubahan tingkat koreksi supervisor (bulan terkini vs acuan)",
          koreksi.get("perubahan_persen"), -30, _status(koreksi.get("perubahan_persen"), -30, "<="),
          "Keputusan validator & antrean quality gate", koreksi.get("catatan", "")),
        i("B1", "Konektivitas blank spot", "Pasar blank spot yang memiliki bukti pengiriman data",
          f"{sum(1 for p in blank_spot if p.kode in ada_data)}/{len(blank_spot)}" if blank_spot else None, "8/8",
          ("memenuhi" if blank_spot and all(p.kode in ada_data for p in blank_spot) and len(blank_spot) >= 8 else
           "belum_dapat_dinilai" if not blank_spot else "belum_memenuhi"),
          "config/pasar.csv (kolom blank_spot)",
          "" if blank_spot else "Delapan wilayah blank spot belum ditandai di config/pasar.csv.", satuan=""),
        i("A1", "Kinerja model AI", "Varian dengan sMAPE ≥10% lebih baik dari baseline",
          persen(ringkasan_model.get("lolos_smape", 0), dinilai), 100,
          _status(persen(ringkasan_model.get("lolos_smape", 0), dinilai), 100, ">="), "Halaman Mutu Model"),
        i("A2", "Kinerja model AI", "Varian dengan bias absolut ≤5%", persen(ringkasan_model.get("lolos_bias", 0), dinilai),
          100, _status(persen(ringkasan_model.get("lolos_bias", 0), dinilai), 100, ">="), "Halaman Mutu Model"),
        i("A3", "Kinerja model AI", "F1-score deteksi anomali", evaluasi.get("f1"), tk["f1_min"],
          _status(evaluasi.get("f1"), tk["f1_min"], ">="), evaluasi.get("sumber_label", ""), satuan=""),
        i("A4", "Kinerja model AI", "Recall anomali prioritas", evaluasi.get("recall"), tk["recall_min"],
          _status(evaluasi.get("recall"), tk["recall_min"], ">="), evaluasi.get("sumber_label", ""), satuan=""),
        i("A5", "Kinerja model AI", "False positive rate", evaluasi.get("false_positive_rate"), tk["fpr_maks"],
          _status(evaluasi.get("false_positive_rate"), tk["fpr_maks"], "<="), evaluasi.get("sumber_label", ""), satuan=""),
        i("A6", "Kinerja model AI", "Selisih kinerja antarsegmen (maks.)", stabilitas.get("gap_persen"), 20,
          ("belum_memenuhi" if stabilitas.get("lebih_buruk_dari_baseline") else
           _status(stabilitas.get("gap_persen"), 20, "<=")), "Backtest per kelompok & kondisi hari raya",
          ("Segmen lebih buruk dari baseline: " + ", ".join(stabilitas["lebih_buruk_dari_baseline"]))
          if stabilitas.get("lebih_buruk_dari_baseline") else stabilitas.get("catatan", "")),
        i("L1", "Keandalan layanan", "Uptime dashboard (30 hari)", uptime.get("uptime_persen"), 99.5,
          _status(uptime.get("uptime_persen"), 99.5, ">="), "Workflow Uptime (cabang log-uptime)", uptime.get("catatan", "")),
        i("D1", "Adopsi perubahan", "Tingkat adopsi SOP/dashboard", None, "35% → 95%", "diukur_manual",
          "Log penggunaan, survei kesiapan",
          "GitHub Pages tidak menyediakan log akses; ukur lewat survei kesiapan & berita acara evaluasi."),
        i("K1", "Komunikasi & partisipasi", "Kepuasan pengguna (Indeks Kepuasan Masyarakat)", layanan.get("ikm"), 76.61,
          _status(layanan.get("ikm"), 76.61, ">="), "Survei kepuasan (Issue Forms)", layanan.get("catatan_ikm", ""), satuan=""),
        i("K2", "Komunikasi & partisipasi", "Pengaduan data yang sudah ditanggapi", layanan.get("pengaduan_ditanggapi_persen"),
          100, _status(layanan.get("pengaduan_ditanggapi_persen"), 100, ">="), "Pengaduan (Issue Forms)",
          layanan.get("catatan_pengaduan", "")),
        i("T1", "Pemanfaatan oleh TPID", "Sinyal prioritas ditindaklanjuti", persen(ditindak, len(anomali_tinggi)),
          tk["tindak_lanjut_sinyal_persen"], _status(persen(ditindak, len(anomali_tinggi)), tk["tindak_lanjut_sinyal_persen"], ">="),
          "GitHub Issues / buku tindak lanjut"),
        i("T2", "Pemanfaatan oleh TPID", "Perbaikan waktu respons tindak lanjut vs acuan", respons.get("perbaikan_persen"), 20,
          _status(respons.get("perbaikan_persen"), 20, ">="), "Riwayat status sinyal", respons.get("catatan", "")),
        i("I1", "Integritas & pengawasan", "Sinyal berisiko tinggi yang sudah diverifikasi manusia",
          persen(ditanggapi, len(anomali_tinggi)), 100, _status(persen(ditanggapi, len(anomali_tinggi)), 100, ">="),
          "Status sinyal"),
        i("I2", "Integritas & pengawasan", "Model proyeksi yang dipakai sudah disetujui manusia",
          persen(sum(1 for s in persetujuan.values() if s == "disetujui"), len(persetujuan)), 100,
          _status(persen(sum(1 for s in persetujuan.values() if s == "disetujui"), len(persetujuan)), 100, ">="),
          "data/persetujuan_model/"),
    ]
    return daftar

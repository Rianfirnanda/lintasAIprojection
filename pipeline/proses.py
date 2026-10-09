"""Orkestrasi pipeline end-to-end dan publikasi JSON untuk dashboard statis (GitHub Pages)."""

from __future__ import annotations

import csv
import json
import logging
import math
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

import numpy as np

from . import (VERSI, agregasi, analisis, demo, kinerja, kualitas, laporan, layanan, masukan, notifikasi, pengguna,
               sinyal as modul_sinyal, tindak_lanjut)
from .konfigurasi import Konfigurasi
from . import firebase as modul_firebase
from . import firestore_sinkron
from . import berita
from . import konektor_resmi
from . import kebijakan as modul_kebijakan

log = logging.getLogger(__name__)
HARI_SERI_PUBLIKASI = 400


def _bersih(obj):
    """Ubah NaN/numpy menjadi tipe JSON yang aman."""
    if isinstance(obj, dict):
        return {str(k): _bersih(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_bersih(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        return None if math.isnan(obj) or math.isinf(obj) else round(float(obj), 4)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


def _tulis_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_bersih(data), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _nilai_list(arr: np.ndarray, pembulatan: int = 0) -> list:
    return [None if np.isnan(x) else round(float(x), pembulatan) for x in arr]


def tentukan_mode_demo(konf: Konfigurasi, folder_masuk: Path, paksa: str | None) -> bool:
    mode = (paksa or konf.pengaturan.get("mode_demo", "otomatis")).lower()
    if mode in ("ya", "on", "true"):
        return True
    if mode in ("tidak", "off", "false"):
        return False
    return not masukan.ada_data_harga(folder_masuk)


def baca_keputusan_sumber(akar: Path) -> dict[str, dict]:
    """Keputusan terima/tolak analis atas kandidat AI Data Finder (data/sumber/keputusan/*.csv), terbaru yang berlaku."""
    hasil: dict[str, dict] = {}
    for path in sorted((akar / "data" / "sumber" / "keputusan").glob("*.csv")):
        with path.open(newline="", encoding="utf-8-sig") as f:
            for b in csv.DictReader(f):
                if b.get("id_kandidat") and b.get("keputusan") in ("terima", "tolak"):
                    hasil[b["id_kandidat"]] = {k: (b.get(k) or "").strip() for k in ("keputusan", "alasan", "penilai", "tanggal")}
    return hasil


def terapkan_keputusan_sumber(kandidat: dict, keputusan: dict[str, dict]) -> list[dict]:
    """Tandai kandidat yang sudah diputuskan analis, lalu kembalikan kandidat yang diterima sebagai baris daftar sumber
    (status "diterima": sudah dinilai layak, tetapi datanya belum diambil)."""
    from . import pencari_data

    pencari_data.beri_id(kandidat)
    diterima: dict[str, dict] = {}
    for p in kandidat.get("pencarian", []):
        for k in (p.get("hasil") or {}).get("kandidat") or []:
            kp = keputusan.get(k["id"])
            if not kp:
                continue
            k["keputusan"] = kp
            k["status_verifikasi"] = "diterima" if kp["keputusan"] == "terima" else "ditolak"
            kunci = k.get("url") or k["id"]
            if kp["keputusan"] == "terima" and kunci not in diterima:
                diterima[kunci] = {
                    "kode": f"AI-{k['id'][:6].upper()}", "nama": k.get("nama_sumber") or k.get("url") or "-",
                    "kelompok": "AI_FINDER", "metode_akses": k.get("metode_akses") or "web",
                    "frekuensi": k.get("frekuensi_pembaruan") or "-", "url": k.get("url") or "",
                    "lisensi": k.get("lisensi_atau_ketentuan") or "", "status": "diterima", "prioritas": 99,
                    "catatan": f"Diterima {kp['penilai'] or 'analis'} {kp['tanggal']}"
                               + (f": {kp['alasan']}" if kp["alasan"] else "") + ". Datanya belum diambil.",
                    "jumlah_observasi": 0,
                }
    return list(diterima.values())


def jalankan(konf: Konfigurasi, keluaran: Path, mode_demo: str | None = None, sinkron_github: bool = True,
             kirim_notifikasi: bool = True) -> dict:
    akar = konf.akar
    folder_masuk = akar / "data" / "masuk"
    pakai_demo = tentukan_mode_demo(konf, folder_masuk, mode_demo)
    info_demo = None
    tmp = None
    if pakai_demo:
        tmp = Path(tempfile.mkdtemp(prefix="demo-harga-"))
        folder_demo = tmp / "data" / "masuk"
        info_demo = demo.buat(konf, folder_demo)
        hasil_masuk = masukan.baca_semua(folder_demo, konf, akar_relatif=tmp)
        # konteks nyata (mis. cuaca dari konektor) tetap dibaca bila ada
        nyata = masukan.baca_semua(folder_masuk, konf, akar_relatif=akar)
        hasil_masuk.konteks.extend(k for k in nyata.konteks if k.kode_sumber != "BD-CUACA")
        hasil_masuk.batch.extend(b for b in nyata.batch if b.jenis == "konteks")
    else:
        hasil_masuk = masukan.baca_semua(folder_masuk, konf, akar_relatif=akar)
    log.info("berkas: %d, observasi: %d, konteks: %d, ditolak: %d", len(hasil_masuk.batch), len(hasil_masuk.observasi),
             len(hasil_masuk.konteks), len(hasil_masuk.penolakan))

    # Quality gate
    keputusan = {} if pakai_demo else kualitas.baca_keputusan(akar / "data" / "validasi")
    hasil_qc = kualitas.jalankan(hasil_masuk.observasi, konf, keputusan)
    dipakai = hasil_qc.dipakai()

    # Integrasi -> deret harian
    harian = agregasi.harian_wilayah(dipakai, konf)
    harian_pasar = agregasi.harian_pasar(dipakai)
    target = konf.wilayah_target
    tanggal_target = [t for (w, _), per in harian.items() if w == target for t in per]
    tanggal_data = max(tanggal_target) if tanggal_target else None

    # Analisis per varian (dengan persetujuan manusia atas model, bila diwajibkan)
    persetujuan = kinerja.baca_persetujuan(akar / "data" / "persetujuan_model")
    wajib_setuju = konf.pengaturan["analisis"].get("wajib_persetujuan_model", False)
    hasil_varian: dict[str, analisis.HasilVarian] = {}
    seri_pembanding: dict[str, dict[str, analisis.SeriHarian]] = defaultdict(dict)
    for v in konf.varian_aktif:
        data = harian.get((target, v.kode))
        if not data:
            continue
        seri = analisis.bentuk_seri(data, akhir=tanggal_data)
        hasil_varian[v.kode] = analisis.analisis_varian(
            seri, v.kelompok, konf.hari_raya(), konf.pengaturan,
            model_disetujui=persetujuan.get(v.kode, {}).get("model"), wajib_persetujuan=wajib_setuju)
        for w in konf.wilayah:
            if w != target and harian.get((w, v.kode)):
                seri_pembanding[v.kode][w] = analisis.bentuk_seri(harian[(w, v.kode)], akhir=tanggal_data)

    # Sinyal + tindak lanjut
    indeks = modul_sinyal.IndeksKonteks(hasil_masuk.konteks)
    daftar_sinyal = modul_sinyal.bentuk_sinyal(konf, hasil_varian, seri_pembanding, indeks, hasil_qc.ketepatan, tanggal_data)
    buku, terlewat = ({}, []) if pakai_demo else tindak_lanjut.baca_buku(akar / "data" / "tindak_lanjut")
    repo = os.environ.get("GITHUB_REPOSITORY")
    url_dashboard = os.environ.get("URL_DASHBOARD") or (
        f"https://{repo.split('/')[0].lower()}.github.io/{repo.split('/')[1]}/" if repo else "")
    status_issue, pesan_github = ({}, "sinkronisasi GitHub dilewati")
    if sinkron_github:
        status_issue, pesan_github = tindak_lanjut.sinkronisasi_github(
            daftar_sinyal, konf.pengaturan, os.environ.get("GITHUB_TOKEN"), repo,
            boleh_buat=not pakai_demo, url_dashboard=url_dashboard)
    for s in daftar_sinyal:
        s["status"] = "baru"
        s["riwayat"] = []
        if s["id"] in buku:
            c = buku[s["id"]]
            s["status"], s["riwayat"] = c.status, c.riwayat
        if s["id"] in status_issue:
            gi = status_issue[s["id"]]
            s["status"], s["url_issue"] = gi["status"], gi["url"]

    titik = sum(hv.titik_dievaluasi for hv in hasil_varian.values())
    if pakai_demo:
        evaluasi = modul_sinyal.evaluasi_terhadap_kebenaran(hasil_varian, info_demo["kebenaran"], titik)
    else:
        evaluasi = modul_sinyal.evaluasi_deteksi(daftar_sinyal, {s["id"]: s["status"] for s in daftar_sinyal}, terlewat, titik)
    evaluasi["titik_dievaluasi"] = titik

    token = os.environ.get("GITHUB_TOKEN")
    klien_gh = tindak_lanjut.KlienGitHub(token, repo) if sinkron_github and token and repo else None
    cfg_kinerja = konf.pengaturan.get("kinerja", {})
    data_kinerja = {
        "layanan": layanan.kumpulkan(klien_gh, konf.hari_ini),
        "koreksi": kinerja.koreksi_supervisor(hasil_qc.observasi, konf.hari_ini),
        "respons": kinerja.waktu_respons(daftar_sinyal, buku, status_issue, konf.hari_ini,
                                         cfg_kinerja.get("jumlah_acuan_respons", 10)),
        "stabilitas": kinerja.stabilitas_segmen(hasil_varian, konf.varian),
        "uptime": kinerja.ringkas_uptime(akar / "data" / "uptime.csv", konf.hari_ini, cfg_kinerja.get("hari_uptime", 30)),
        "persetujuan": persetujuan,
        # Respons pedagang dihitung dari pencatatan asli saja; data contoh tidak punya kunjungan sungguhan.
        "respons_pedagang": kinerja.respons_pedagang(
            [] if pakai_demo else hasil_qc.observasi, [] if pakai_demo else kinerja.baca_kunjungan(akar / "data" / "kunjungan"),
            konf.hari_ini),
        "adopsi": kinerja.adopsi(akar / "data" / "adopsi.json", konf.hari_ini),
        "kebijakan": modul_kebijakan.bentuk(
            akar, daftar_sinyal, {kode: per for (w, kode), per in harian.items() if w == target}, konf.hari_ini,
            {k: v.nama for k, v in konf.varian.items()}, konf.pengaturan.get("kebijakan")),
    }

    # Publikasi
    if keluaran.exists():
        for sub in ("seri", "unduh"):
            shutil.rmtree(keluaran / sub, ignore_errors=True)
    keluaran.mkdir(parents=True, exist_ok=True)
    ringkas = publikasikan(konf, keluaran, pakai_demo, hasil_masuk, hasil_qc, harian, harian_pasar, hasil_varian,
                           seri_pembanding, daftar_sinyal, evaluasi, tanggal_data, pesan_github, data_kinerja)

    # Notifikasi (Telegram/email) dikirim setelah publikasi agar tautan dashboard & buletin sudah tersedia.
    laporan_mingguan = json.loads((keluaran / "laporan.json").read_text(encoding="utf-8")).get("mingguan", [])
    pesan_notifikasi = notifikasi.jalankan(konf, daftar_sinyal, laporan_mingguan, url_dashboard, pakai_demo) \
        if kirim_notifikasi else "notifikasi dilewati"
    meta = json.loads((keluaran / "meta.json").read_text(encoding="utf-8"))
    meta["pesan_notifikasi"] = pesan_notifikasi
    _tulis_json(keluaran / "meta.json", meta)
    ringkas["notifikasi"] = pesan_notifikasi
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    return ringkas


def publikasikan(konf, keluaran, pakai_demo, hasil_masuk, hasil_qc, harian, harian_pasar, hasil_varian,
                 seri_pembanding, daftar_sinyal, evaluasi, tanggal_data, pesan_github, data_kinerja=None) -> dict:
    data_kinerja = data_kinerja or {}
    target = konf.wilayah_target
    tk = konf.pengaturan["target_kinerja"]
    zona = ZoneInfo(konf.pengaturan.get("zona_waktu", "Asia/Jakarta"))
    status_obs = Counter(o.status for o in hasil_qc.observasi)

    # ---------- master.json
    komoditas = []
    for kode in konf.komoditas_aktif:
        vv = [v for v in konf.varian_aktif if v.kode_komoditas == kode]
        komoditas.append({"kode": kode, "nama": vv[0].komoditas, "varian": [v.kode for v in vv]})
    master = {
        "varian": [v.__dict__ for v in konf.varian.values()],
        "komoditas": komoditas,
        "wilayah": [w.__dict__ for w in konf.wilayah.values()],
        "pasar": [p.__dict__ for p in konf.pasar.values()],
        "kalender": [{"tanggal": a.tanggal, "nama": a.nama, "jenis": a.jenis, "status": a.status} for a in konf.kalender],
    }
    _tulis_json(keluaran / "master.json", master)

    # ---------- seri/<varian>.json
    batas = (tanggal_data or konf.hari_ini) - timedelta(days=HARI_SERI_PUBLIKASI)
    indeks_konteks = modul_sinyal.IndeksKonteks(hasil_masuk.konteks)
    ringkasan_varian = []
    sinyal_aktif_per_varian: dict[str, str] = {}
    for s in daftar_sinyal:
        if s["aktif"] and s.get("kode_varian") and s["jenis"] in ("anomali_harga", "proyeksi_naik", "risiko_hari_raya"):
            lama = sinyal_aktif_per_varian.get(s["kode_varian"])
            if lama is None or modul_sinyal.TINGKAT[s["keparahan"]] > modul_sinyal.TINGKAT[lama]:
                sinyal_aktif_per_varian[s["kode_varian"]] = s["keparahan"]

    for kode, hv in hasil_varian.items():
        v = konf.varian[kode]
        seri = hv.seri
        i0 = max(0, seri.indeks(batas)) if seri.tanggal[0] < batas else 0
        tanggal = seri.tanggal[i0:]
        pembanding = {}
        for w, sp in seri_pembanding.get(kode, {}).items():
            nilai = []
            for t in tanggal:
                j = sp.indeks(t)
                nilai.append(None if j < 0 or j >= sp.n or np.isnan(sp.nilai[j]) else round(float(sp.nilai[j])))
            pembanding[w] = {"nama": konf.wilayah[w].nama, "peran": konf.wilayah[w].peran, "nilai": nilai}
        # Harga rata-rata pasar tradisional Provinsi Bengkulu dari PIHPS Bank Indonesia (konektor Big Data).
        pihps = indeks_konteks.data.get((konektor_resmi.WILAYAH_PIHPS, "harga_pihps", kode), {})
        nilai_pihps = [round(pihps[t]) if t in pihps else None for t in tanggal]
        if any(x is not None for x in nilai_pihps):
            pembanding["PIHPS"] = {"nama": "Provinsi Bengkulu (PIHPS BI)", "peran": "pembanding_provinsi", "nilai": nilai_pihps}
        per_pasar = {}
        for p in konf.pasar_di(target):
            data_p = harian_pasar.get((p.kode, kode), {})
            per_pasar[p.kode] = [round(data_p[t][0]) if t in data_p else None for t in tanggal]
        tgl_anomali = [a.tanggal.isoformat() for a in hv.anomali if a.tanggal >= tanggal[0]]
        _tulis_json(keluaran / "seri" / f"{kode}.json", {
            "kode": kode, "nama": v.nama, "komoditas": v.komoditas, "satuan": v.satuan, "kelompok": v.kelompok,
            "tanggal": [t.isoformat() for t in tanggal],
            "aktual": _nilai_list(seri.nilai[i0:]), "baseline": _nilai_list(hv.baseline[i0:]),
            "rata7": _nilai_list(hv.rata7[i0:]), "proyeksi": hv.proyeksi, "pembanding": pembanding,
            "per_pasar": per_pasar, "anomali": tgl_anomali, "model_terpilih": hv.model_terpilih,
            "catatan": hv.catatan,
        })

        idx = np.where(~np.isnan(seri.nilai))[0]
        terakhir = float(seri.nilai[idx[-1]]) if len(idx) else None
        base = float(hv.baseline[idx[-1]]) if len(idx) and not np.isnan(hv.baseline[idx[-1]]) else None
        h7 = next((p for p in hv.proyeksi if p["h"] == 7), None)
        ringkasan_varian.append({
            "kode": kode, "nama": v.nama, "kode_komoditas": v.kode_komoditas, "komoditas": v.komoditas,
            "kelompok": v.kelompok, "satuan": v.satuan,
            "harga_terakhir": round(terakhir) if terakhir else None,
            "tanggal_terakhir": seri.tanggal[idx[-1]].isoformat() if len(idx) else None,
            "baseline": round(base) if base else None,
            "deviasi_persen": round((terakhir / base - 1) * 100, 2) if terakhir and base else None,
            "perubahan": hv.perubahan, "harga_acuan": hv.harga_acuan, "proyeksi_h7": h7, "model": hv.model_terpilih,
            "sinyal": sinyal_aktif_per_varian.get(kode),
        })

    # ---------- sinyal.json
    anomali = [s for s in daftar_sinyal if s["jenis"] == "anomali_harga"]
    status_count = Counter(s["status"] for s in anomali)
    prioritas = [s for s in anomali if s["keparahan"] == "tinggi"]
    ditindak = sum(1 for s in prioritas if s["status"] in ("ditindaklanjuti", "selesai"))
    _tulis_json(keluaran / "sinyal.json", {
        "sinyal": daftar_sinyal,
        "ringkasan": {
            "total": len(daftar_sinyal), "aktif": sum(1 for s in daftar_sinyal if s["aktif"]),
            "per_jenis": Counter(s["jenis"] for s in daftar_sinyal),
            "per_keparahan": Counter(s["keparahan"] for s in daftar_sinyal if s["aktif"]),
            "status_anomali": status_count,
            "prioritas_ditindaklanjuti_persen": round(ditindak / len(prioritas) * 100, 1) if prioritas else None,
            "target_tindak_lanjut_persen": tk["tindak_lanjut_sinyal_persen"],
        },
        "pesan_github": pesan_github,
    })

    # ---------- kualitas.json
    perlu = sorted(hasil_qc.perlu_validasi(), key=lambda o: o.tanggal, reverse=True)
    _tulis_json(keluaran / "kualitas.json", {
        "ringkasan": {
            "berkas": len(hasil_masuk.batch), "baris_ditolak_skema": len(hasil_masuk.penolakan),
            "duplikat_dibuang": hasil_qc.jumlah_duplikat, "per_status": status_obs,
            "rekonsiliasi_melebihi_batas": sum(1 for r in hasil_qc.rekonsiliasi if r["melebihi_batas"]),
        },
        "keterangan_tanda": kualitas.KETERANGAN_TANDA,
        "pengaturan": {"jam_batas_tepat_waktu": konf.pengaturan["jam_batas_tepat_waktu"], **konf.pengaturan["kualitas"]},
        "ketepatan": hasil_qc.ketepatan,
        "batch": [b.__dict__ for b in sorted(hasil_masuk.batch, key=lambda b: b.berkas, reverse=True)],
        "penolakan": [p.__dict__ for p in hasil_masuk.penolakan[-500:]],
        "perlu_validasi": [
            {"id": o.id, "tanggal": o.tanggal, "kode_pasar": o.kode_pasar, "kode_varian": o.kode_varian,
             "harga": o.harga, "harga_asli": o.harga_asli, "satuan_asli": o.satuan_asli, "kode_sumber": o.kode_sumber,
             "tanda": o.tanda, "berkas": o.berkas, "baris": o.baris}
            for o in perlu[:500]
        ],
        "jumlah_perlu_validasi": len(perlu),
        "rekonsiliasi": sorted(hasil_qc.rekonsiliasi, key=lambda r: (not r["melebihi_batas"], r["tanggal"]), reverse=False)[:200],
    })

    # ---------- model.json
    per_varian_model = []
    lolos_smape = lolos_bias = lolos_cakupan = dinilai = 0
    for kode, hv in hasil_varian.items():
        m = hv.metrik_model.get(hv.model_terpilih or "", {})
        entri = {
            "kode": kode, "nama": konf.varian[kode].nama, "model_terpilih": hv.model_terpilih,
            "nama_model": analisis.NAMA_MODEL.get(hv.model_terpilih or "", "-"), "metrik": hv.metrik_model,
            "perbaikan_vs_naif_persen": hv.perbaikan_vs_naif_persen,
            "cakupan_interval_persen": hv.cakupan_interval_persen, "drift": hv.drift, "catatan": hv.catatan,
            "profil_hari_raya": hv.profil_hari_raya,
            "model_rekomendasi": hv.model_rekomendasi, "status_persetujuan": hv.status_persetujuan,
            "persetujuan": {k: v for k, v in data_kinerja.get("persetujuan", {}).get(kode, {}).items() if k != "riwayat"},
            "segmen": hv.segmen,
        }
        if m:
            dinilai += 1
            entri["lolos"] = {
                "smape": hv.perbaikan_vs_naif_persen is not None and hv.perbaikan_vs_naif_persen >= tk["perbaikan_smape_persen"],
                "bias": abs(m["bias_persen"]) <= tk["bias_absolut_maks_persen"],
                "cakupan": hv.cakupan_interval_persen is not None
                and tk["cakupan_interval_min_persen"] <= hv.cakupan_interval_persen <= tk["cakupan_interval_maks_persen"],
            }
            lolos_smape += entri["lolos"]["smape"]
            lolos_bias += entri["lolos"]["bias"]
            lolos_cakupan += entri["lolos"]["cakupan"]
        per_varian_model.append(entri)
    smape_terpilih = [hv.metrik_model[hv.model_terpilih]["smape"] for hv in hasil_varian.values()
                      if hv.model_terpilih in hv.metrik_model]
    ringkasan_model = {
        "varian_dinilai": dinilai, "lolos_smape": lolos_smape, "lolos_bias": lolos_bias, "lolos_cakupan": lolos_cakupan,
        "smape_median": round(median(smape_terpilih), 2) if smape_terpilih else None,
        "model_dipakai": Counter(hv.model_terpilih for hv in hasil_varian.values() if hv.model_terpilih),
    }
    _tulis_json(keluaran / "model.json", {
        "ringkasan": ringkasan_model, "per_varian": per_varian_model, "evaluasi_anomali": evaluasi,
        "target": tk, "nama_model": analisis.NAMA_MODEL,
        "pengaturan": {"analisis": konf.pengaturan["analisis"], "sinyal": konf.pengaturan["sinyal"]},
    })

    # ---------- kinerja.json (indikator SMART Rancangan Aksi Perubahan)
    status_persetujuan = {kode: hv.status_persetujuan for kode, hv in hasil_varian.items()}
    indikator = kinerja.indikator_smart(
        konf, hasil_qc, hasil_masuk, ringkasan_model, evaluasi, daftar_sinyal, data_kinerja.get("respons", {}),
        data_kinerja.get("koreksi", {}), data_kinerja.get("stabilitas", {}), data_kinerja.get("uptime", {}),
        status_persetujuan, data_kinerja.get("layanan"),
        tambahan={"respons_pedagang": data_kinerja.get("respons_pedagang"), "adopsi": data_kinerja.get("adopsi"),
                  "kebijakan": (data_kinerja.get("kebijakan") or {}).get("ringkasan")})
    _tulis_json(keluaran / "kinerja.json", {
        "indikator": indikator,
        "koreksi_supervisor": data_kinerja.get("koreksi", {}),
        "waktu_respons": data_kinerja.get("respons", {}),
        "stabilitas_segmen": data_kinerja.get("stabilitas", {}),
        "uptime": data_kinerja.get("uptime", {}),
        "persetujuan_model": {
            "wajib": konf.pengaturan["analisis"].get("wajib_persetujuan_model", False),
            "status": status_persetujuan,
        },
        "layanan": data_kinerja.get("layanan") or {},
        "respons_pedagang": data_kinerja.get("respons_pedagang") or {},
        "adopsi": data_kinerja.get("adopsi") or {},
    })

    # ---------- kebijakan.json (rekomendasi, kebijakan dan dampaknya, rapat TPID)
    if data_kinerja.get("kebijakan"):
        _tulis_json(keluaran / "kebijakan.json", data_kinerja["kebijakan"])

    # ---------- laporan.json (mingguan, bulanan, triwulanan, semesteran, tahunan)
    kinerja_model = {"ringkasan": ringkasan_model, "evaluasi_anomali": evaluasi, "target": tk}
    _tulis_json(keluaran / "laporan.json", laporan.bentuk_semua(
        konf, {kode: per for (w, kode), per in harian.items() if w == target}, hasil_varian, daftar_sinyal,
        hasil_qc.observasi, tanggal_data,
        ekstra={
            "bulanan": {"kinerja_model": kinerja_model},
            **{jenis: {"kinerja_model": kinerja_model, "waktu_respons": data_kinerja.get("respons", {}),
                       "stabilitas_segmen": data_kinerja.get("stabilitas", {}), "indikator": indikator}
               for jenis in ("triwulanan", "semesteran", "tahunan")},
        }))

    # ---------- pasar.json
    pasar_out = []
    ketepatan_per = {p["kode_pasar"]: p for p in hasil_qc.ketepatan.get("per_pasar", [])}
    minimal = konf.pengaturan["privasi"]["min_observasi_publikasi_pasar"]
    for p in konf.pasar.values():
        terkini = []
        for v in konf.varian_aktif:
            data_p = harian_pasar.get((p.kode, v.kode))
            if data_p:
                t = max(data_p)
                harga, n = data_p[t]
                if n >= minimal:
                    terkini.append({"kode_varian": v.kode, "tanggal": t, "harga": round(harga), "n": n})
        pasar_out.append({**p.__dict__, "wilayah": konf.wilayah[p.kode_wilayah].nama,
                          "peran": konf.wilayah[p.kode_wilayah].peran, "terkini": terkini,
                          "ketepatan": ketepatan_per.get(p.kode)})
    _tulis_json(keluaran / "pasar.json", {"pasar": pasar_out})

    # ---------- sumber.json
    kandidat_path = konf.akar / "data" / "sumber" / "kandidat_ai.json"
    kandidat = json.loads(kandidat_path.read_text(encoding="utf-8")) if kandidat_path.exists() else {"pencarian": []}
    diterima = terapkan_keputusan_sumber(kandidat, baca_keputusan_sumber(konf.akar))
    jumlah_per_sumber = Counter(o.kode_sumber for o in hasil_qc.observasi)
    _tulis_json(keluaran / "sumber.json", {
        "sumber": [{**s.__dict__, "jumlah_observasi": jumlah_per_sumber.get(s.kode, 0)} for s in konf.sumber.values()] + diterima,
        "kandidat_ai": kandidat,
    })

    # ---------- berita.json (halaman Berita Lokal; hasil pencarian harian di data/berita/berita.json)
    _tulis_json(keluaran / "berita.json", berita.untuk_situs(konf))

    # ---------- ringkasan.json (dashboard utama)
    jhr = konf.pengaturan["jendela_hari_raya"]
    berikut = next((a for a in konf.kalender if a.jenis in ("hari_raya", "awal_ramadan") and a.tanggal >= konf.hari_ini), None)
    posisi = analisis.offset_hari_raya(konf.hari_ini, konf.hari_raya(), jhr["sebelum"], jhr["sesudah"])
    profil_top = []
    for kode, hv in hasil_varian.items():
        if hv.profil_hari_raya:
            puncak = max(hv.profil_hari_raya.values())
            profil_top.append({"kode": kode, "nama": konf.varian[kode].nama, "kenaikan_puncak_persen": round((puncak - 1) * 100, 1)})
    profil_top.sort(key=lambda x: x["kenaikan_puncak_persen"], reverse=True)
    aktif = [s for s in daftar_sinyal if s["aktif"]]
    ringkasan = {
        "kpi": {
            "jumlah_komoditas": len(konf.komoditas_aktif), "jumlah_varian": len(konf.varian_aktif),
            "varian_berdata": len(hasil_varian),
            "pasar_target": len(konf.pasar_di(target)),
            "kelengkapan_persen": hasil_qc.ketepatan.get("kelengkapan_persen"),
            "ketepatan_persen": hasil_qc.ketepatan.get("ketepatan_persen"),
            "target_ketepatan_persen": tk["ketepatan_waktu_persen"],
            "sinyal_aktif": len(aktif), "sinyal_tinggi": sum(1 for s in aktif if s["keparahan"] == "tinggi"),
            "perlu_validasi": status_obs.get("perlu_validasi", 0),
            "smape_median": ringkasan_model["smape_median"],
            "model_lolos_target": lolos_smape, "model_dinilai": dinilai,
        },
        "varian": ringkasan_varian,
        "hari_raya": {
            "berikutnya": {"nama": berikut.nama, "tanggal": berikut.tanggal, "status": berikut.status,
                           "hari_menuju": (berikut.tanggal - konf.hari_ini).days} if berikut else None,
            "mode_intensif": posisi is not None,
            "posisi": {"acara": posisi[1].nama, "hari": posisi[0]} if posisi else None,
            "jendela": jhr, "profil_top": profil_top[:8],
        },
        "tindak_lanjut": {"status_anomali": status_count,
                          "prioritas_ditindaklanjuti_persen": round(ditindak / len(prioritas) * 100, 1) if prioritas else None},
        "prioritas": [s["id"] for s in aktif[:8]],
    }
    _tulis_json(keluaran / "ringkasan.json", ringkasan)

    # ---------- unduh/harga_harian.csv
    (keluaran / "unduh").mkdir(parents=True, exist_ok=True)
    with (keluaran / "unduh" / "harga_harian.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tanggal", "kode_wilayah", "wilayah", "kode_varian", "varian", "satuan", "harga_median"])
        for (kode_w, kode_v), per in sorted(harian.items()):
            if kode_v not in konf.varian or not konf.varian[kode_v].aktif:
                continue
            for t in sorted(per):
                w.writerow([t.isoformat(), kode_w, konf.wilayah[kode_w].nama, kode_v, konf.varian[kode_v].nama,
                            konf.varian[kode_v].satuan, round(per[t])])

    # ---------- meta.json
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY")
    run = os.environ.get("GITHUB_RUN_ID")
    meta = {
        "dibuat": datetime.now(zona).isoformat(timespec="seconds"), "versi": VERSI, "mode_demo": pakai_demo,
        "hari_ini": konf.hari_ini, "tanggal_data_terakhir": tanggal_data,
        "wilayah_target": konf.wilayah[target].__dict__,
        "repo": repo, "url_repo": f"{server}/{repo}" if repo else None,
        "url_run": f"{server}/{repo}/actions/runs/{run}" if repo and run else None,
        "commit": os.environ.get("GITHUB_SHA"),
        "jumlah": {
            "observasi_total": len(hasil_qc.observasi), "observasi_dipakai": len(hasil_qc.dipakai()),
            "perlu_validasi": status_obs.get("perlu_validasi", 0),
            "ditolak": len(hasil_masuk.penolakan) + status_obs.get("ditolak_validator", 0),
            "duplikat": hasil_qc.jumlah_duplikat, "berkas": len(hasil_masuk.batch),
        },
        "pesan_github": pesan_github,
        "layanan": {
            "url_pengaduan": f"{server}/{repo}/issues/new?template=pengaduan-data.yml" if repo else None,
            "url_survei": f"{server}/{repo}/issues/new?template=survei-kepuasan.yml" if repo else None,
            **{k: v for k, v in konf.pengaturan.get("layanan", {}).items() if v},
        },
    }
    # Batas wilayah (GeoJSON dari BPS) opsional: bila ada di config/, ikut diterbitkan untuk peta beranda.
    batas = konf.akar / "config" / "batas_wilayah.geojson"
    meta["batas_wilayah"] = batas.exists()
    if batas.exists():
        shutil.copyfile(batas, keluaran / "batas_wilayah.geojson")
    # Pengaturan dan skemanya diterbitkan agar panel admin bisa menampilkan nilai yang berlaku tanpa token GitHub.
    # Isinya tidak rahasia: kunci API hanya ada di GitHub Secrets.
    skema_pengaturan = konf.akar / "config" / "skema_pengaturan.json"
    if skema_pengaturan.exists():
        shutil.copyfile(skema_pengaturan, keluaran / "skema_pengaturan.json")
        _tulis_json(keluaran / "pengaturan.json", konf.pengaturan)
    # Prompt AI Data Finder untuk browser admin (tidak rahasia; kunci tidak ikut).
    from . import pencari_data
    _tulis_json(keluaran / "ai_prompt.json", pencari_data.bahan_situs())
    # Login per peran: Firebase (akun Google) bila konfigurasinya terisi lewat Secret FIREBASE_WEB_CONFIG atau
    # config/firebase.json; jika tidak, akun contoh dari config/pengguna.json. Berkas cara masuk yang tidak dipakai
    # dihapus supaya akun contoh tidak tetap terbuka saat Firebase sudah aktif.
    fb = modul_firebase.konfigurasi_web(konf.akar)
    akun = pengguna.muat(konf.akar / "config" / "pengguna.json")
    for lama in ("firebase.json", "pengguna.json"):
        (keluaran / lama).unlink(missing_ok=True)
    # Versi pengaturan dari situs yang sudah dipakai, supaya panel Pengaturan tahu isian mana yang terbaru.
    meta["pengaturan_versi"] = int(firestore_sinkron.baca_tanda(konf.akar).get("pengaturan_versi", 0))
    if fb:
        meta["login"] = "firebase"
        _tulis_json(keluaran / "firebase.json", {"konfigurasi": fb})
    elif akun and not pengguna.periksa(akun):
        meta["login"] = "contoh"
        _tulis_json(keluaran / "pengguna.json", {"garam": akun["garam"], "akun": akun["akun"]})
    else:
        meta["login"] = "tanpa"
    _tulis_json(keluaran / "meta.json", meta)
    return {"meta": meta, "kpi": ringkasan["kpi"], "evaluasi_anomali": evaluasi, "ringkasan_model": ringkasan_model}

"""Bahan Dasbor Analitik: tabel varian dengan proyeksi 7/14/30 hari, status validasi, diagnostik, jejak data, dan versi.

Semua angka berasal dari hasil analisis yang sama dengan halaman lain. Yang belum punya data sungguhan ditandai
"menunggu data" (None), tidak dikarang.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np

from . import analisis

HORIZON_TAMPIL = (7, 14, 30)
SEED = None  # semua model deterministik (tanpa komponen acak); dicatat di jejak versi


def hash_json(obj) -> str:
    teks = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(teks.encode("utf-8")).hexdigest()


def kepercayaan(validasi: dict) -> str:
    """Tinggi: semua syarat protokol validasi lolos. Sedang: hanya satu syarat gagal. Rendah: lebih dari satu gagal atau tanpa model."""
    if not validasi:
        return "rendah"
    if validasi.get("status") == "valid":
        return "tinggi"
    return "sedang" if len(validasi.get("gagal", [])) == 1 and not validasi.get("belum_dinilai") else "rendah"


def _ubah(prediksi: float | None, acuan: float | None) -> float | None:
    return round((prediksi / acuan - 1) * 100, 2) if prediksi and acuan else None


def proyeksi_horizon(hv: analisis.HasilVarian, harga_aktual: float | None) -> dict:
    hasil = {}
    for h in HORIZON_TAMPIL:
        p = next((x for x in hv.proyeksi if x["h"] == h), None)
        hasil[str(h)] = None if p is None else {
            "tanggal": p["tanggal"], "prediksi": p["prediksi"], "bawah": p["bawah"], "atas": p["atas"],
            "perubahan_persen": _ubah(p["prediksi"], harga_aktual)}
    return hasil


def pendorong(hv: analisis.HasilVarian, harga_aktual: float | None, acara_berikut: dict | None) -> list[dict]:
    """Faktor yang terukur dari data sendiri (bukan SHAP): perubahan terkini, rezim volatilitas, pola hari raya, pergeseran distribusi."""
    hasil = []
    for nama, kunci in (("Perubahan 7 hari terakhir", "mingguan"), ("Perubahan 30 hari terakhir", "bulanan")):
        nilai = hv.perubahan.get(kunci)
        if nilai is not None:
            hasil.append({"nama": nama, "nilai": nilai, "satuan": "%", "arah": "naik" if nilai > 0 else "turun" if nilai < 0 else "datar"})
    dg = hv.diagnostik or {}
    if dg.get("rezim_volatilitas"):
        hasil.append({"nama": "Rezim volatilitas 30 hari", "nilai": dg["rezim_volatilitas"], "satuan": None, "arah": None})
    if dg.get("kekuatan_musiman") is not None:
        hasil.append({"nama": "Kekuatan pola mingguan", "nilai": dg["kekuatan_musiman"], "satuan": None, "arah": None})
    if hv.profil_hari_raya:
        puncak = max(hv.profil_hari_raya.values())
        hasil.append({"nama": "Kenaikan puncak menjelang hari raya (riwayat)", "nilai": round((puncak - 1) * 100, 1), "satuan": "%",
                      "arah": "naik" if puncak > 1 else "turun"})
    if acara_berikut:
        hasil.append({"nama": f"Hari menuju {acara_berikut['nama']}", "nilai": acara_berikut["hari_menuju"], "satuan": "hari", "arah": None})
    if dg.get("psi") is not None:
        hasil.append({"nama": "Pergeseran pola harga (PSI)", "nilai": dg["psi"], "satuan": None,
                      "arah": "bergeser" if dg.get("patahan_struktural") else "stabil"})
    return hasil


def rekomendasi_netral(nama: str, harga_aktual: float | None, hv: analisis.HasilVarian, proyeksi: dict, status: str) -> str:
    """Kalimat netral berbasis aturan. Tidak menyarankan kebijakan; hanya apa yang perlu dipantau/diperiksa."""
    p30 = proyeksi.get("30")
    if not harga_aktual or not p30:
        return f"{nama}: proyeksi belum dapat disusun karena data belum cukup."
    arah = p30["perubahan_persen"]
    if status != "valid":
        awal = "Model belum lolos protokol validasi (Eksperimen), jadi angka ini bahan pertimbangan, bukan angka resmi. "
    else:
        awal = ""
    if arah is None:
        return awal + "Perubahan 30 hari belum dapat dihitung."
    if abs(arah) < 1:
        return awal + f"Harga diperkirakan relatif stabil dalam 30 hari ({arah:+.1f}%). Cukup dipantau rutin."
    kata = "naik" if arah > 0 else "turun"
    tindak = "perlu dipantau lebih sering dan dicek ke pasar" if arah > 0 else "perlu dicek apakah penurunan wajar (pasokan/musim)"
    return awal + f"Harga diperkirakan {kata} {abs(arah):.1f}% dalam 30 hari (rentang 80%: Rp{p30['bawah']:,} sampai Rp{p30['atas']:,}); {tindak}.".replace(",", ".")


def kartu_model(konf, v, hv: analisis.HasilVarian, harga: float | None) -> dict:
    """Kartu model per varian: tujuan, data, cara prakiraan, hasil uji, dan keterbatasan (disusun dari fakta yang ada)."""
    w = konf.wilayah[konf.wilayah_target]
    ho = hv.holdout
    batas = []
    if w.peran != "target":
        batas.append(f"Harga yang dipakai adalah {w.nama} (sementara), bukan harga Kabupaten Bengkulu Tengah.")
    batas.append("Harga hanya tercatat pada hari kerja; akhir pekan dan hari libur tidak punya harga.")
    batas.append("Cara prakiraan hanya memakai riwayat harga dan kalender hari raya. Cuaca, kebijakan, dan harga wilayah lain belum ikut dihitung.")
    if hv.validasi.get("status") != "valid":
        gagal = hv.validasi.get("gagal", []) + hv.validasi.get("belum_dinilai", [])
        batas.append("Belum memenuhi protokol validasi" + (f": {', '.join(gagal)}." if gagal else "."))
    if ho:
        batas.append(f"Uji akhir memakai {ho['jumlah_origin']} titik awal yang saling tumpang tindih; angka cakupan rentang peka terhadap jumlah titik yang sedikit.")
    if hv.diagnostik.get("patahan_struktural"):
        batas.append("Pola harga 90 hari terakhir bergeser jauh dari sebelumnya; prakiraan lebih tidak pasti.")
    if hv.jumlah_obs < 730:
        batas.append(f"Riwayat baru {hv.jumlah_obs} hari harga (protokol meminta minimal 730).")
    return {
        "tujuan": f"Prakiraan harga {v.nama} 7, 14, dan 30 hari ke depan beserta rentang {int(konf.pengaturan['analisis']['tingkat_interval'] * 100)}%.",
        "data": {"wilayah": w.nama, "sumber": "PIHPS Bank Indonesia" if w.peran != "target" else "data harga yang masuk ke sistem",
                 "dari": hv.seri.tanggal[0].isoformat(), "sampai": hv.seri.tanggal[-1].isoformat(), "jumlah_hari_berharga": hv.jumlah_obs,
                 "kelengkapan_persen": hv.kelengkapan_persen, "harga_terakhir": round(harga) if harga else None},
        "model": {"dipakai": hv.model_terpilih, "nama": analisis.NAMA_MODEL.get(hv.model_terpilih or "", "-"),
                  "kandidat": [analisis.NAMA_MODEL[m] for m in hv.metrik_model],
                  "cara_memilih": "Cara sederhana jadi juara dahulu; mesin belajar atau gabungan hanya menggantikan bila lolos gerbang Champion vs Challenger "
                                  "dan tidak kalah dari cara naif pada uji Diebold-Mariano di 90 hari terakhir."},
        "uji": {"status": hv.validasi.get("status"), "syarat": hv.validasi.get("syarat", []),
                "smape_uji_akhir": ho["smape"] if ho else None, "cakupan_uji_akhir": ho["cakupan_persen"] if ho else None},
        "keterbatasan": batas,
    }


def perbarui_registry(akar: Path, hasil: dict) -> dict:
    """Registri model: keadaan terkini tiap varian dan riwayat pergantian model/status. Hanya perubahan yang dicatat di riwayat."""
    path = akar / "data" / "registry" / "model_registry.json"
    try:
        lama = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except ValueError:
        lama = {}
    riwayat = list(lama.get("riwayat", []))
    g = hasil["garis_data"]
    versi = {"versi_data": g["versi_data"], "versi_konfigurasi": g["versi_konfigurasi"], "commit": g["commit"]}
    terkini = {}
    for x in hasil["registry"]:
        sebelum = (lama.get("terkini") or {}).get(x["kode"])
        terkini[x["kode"]] = {"model": x["model"], "status": x["status"], "smape_uji_akhir": x["smape_holdout"],
                              "data_hingga": x["data_hingga"], **versi}
        if not sebelum or (sebelum.get("model"), sebelum.get("status")) != (x["model"], x["status"]):
            riwayat.append({"kode": x["kode"], "tanggal_data": hasil["dibuat_untuk"], "model": x["model"], "status": x["status"],
                            "model_sebelumnya": sebelum.get("model") if sebelum else None,
                            "status_sebelumnya": sebelum.get("status") if sebelum else None, **versi})
    keluar = {"riwayat": riwayat[-1000:], "terkini": terkini}
    teks = json.dumps(keluar, ensure_ascii=False, indent=1, sort_keys=True)
    if not path.exists() or path.read_text(encoding="utf-8") != teks:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(teks, encoding="utf-8")
    return keluar


def bentuk(konf, hasil_varian: dict, hasil_qc, hasil_masuk, tanggal_data: date | None, pakai_demo: bool, daftar_sinyal: list,
           acara_berikut: dict | None, seri_pembanding: dict, ringkasan_model: dict) -> dict:
    tk = konf.pengaturan["target_kinerja"]
    varian = []
    for kode, hv in hasil_varian.items():
        v = konf.varian[kode]
        idx = np.where(~np.isnan(hv.seri.nilai))[0]
        harga = float(hv.seri.nilai[idx[-1]]) if len(idx) else None
        tgl = hv.seri.tanggal[idx[-1]].isoformat() if len(idx) else None
        pr = proyeksi_horizon(hv, harga)
        status = (hv.validasi or {}).get("status", "eksperimen")
        ho = hv.holdout or {}
        m = hv.metrik_model.get(hv.model_terpilih or "", {})
        varian.append({
            "kode": kode, "nama": v.nama, "komoditas": v.komoditas, "kelompok": v.kelompok, "satuan": v.satuan,
            "harga_aktual": round(harga) if harga else None, "tanggal_aktual": tgl, "proyeksi": pr,
            "perubahan_30h_persen": (pr.get("30") or {}).get("perubahan_persen"),
            "model": hv.model_terpilih, "nama_model": analisis.NAMA_MODEL.get(hv.model_terpilih or "", "-"),
            "jenis_model": "challenger" if hv.model_terpilih in analisis.MODEL_CHALLENGER else "baseline" if hv.model_terpilih else None,
            "status": status, "kepercayaan": kepercayaan(hv.validasi), "validasi": hv.validasi,
            "holdout": {k: ho.get(k) for k in ("hari", "jumlah_origin", "n", "smape", "mae", "mase", "bias_persen", "akurasi_arah", "cakupan_persen",
                                                 "smape_naif", "perbaikan_vs_naif_persen", "menang_origin_vs_naif", "uji_dm", "per_horizon", "titik_h7")} if ho else None,
            "seleksi": {k: m.get(k) for k in ("smape", "mae", "mase", "bias_persen", "n")} if m else None,
            "diagnostik": hv.diagnostik, "drift": hv.drift, "kelengkapan_persen": hv.kelengkapan_persen, "jumlah_obs": hv.jumlah_obs,
            "tanggal_awal": hv.seri.tanggal[0].isoformat(),
            "pendorong": pendorong(hv, harga, acara_berikut),
            "rekomendasi": rekomendasi_netral(v.nama, harga, hv, pr, status),
            "kartu_model": kartu_model(konf, v, hv, harga),
            "catatan": hv.catatan,
        })

    n_valid = sum(1 for x in varian if x["status"] == "valid")
    status_obs = Counter(o.status for o in hasil_qc.observasi)
    kode_sumber = {o.kode_sumber for o in hasil_qc.dipakai()}
    harga_batch = sorted((b for b in hasil_masuk.batch if b.jenis == "harga"), key=lambda b: b.berkas)
    versi_data = hash_json([[b.berkas, b.sha256] for b in harga_batch])
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo, run = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_RUN_ID")
    tertinggal = (konf.hari_ini - tanggal_data).days if tanggal_data else None
    pembanding_tersedia = sorted({w for per in seri_pembanding.values() for w in per})

    kpi = {
        "varian_berdata": len(varian), "varian_aktif": len(konf.varian_aktif),
        "varian_valid": n_valid, "varian_eksperimen": len(varian) - n_valid,
        "sumber_aktif": len(kode_sumber), "sumber_terdaftar": len(konf.sumber),
        "hari_tertinggal": tertinggal, "kesegaran": None if tertinggal is None else "segar" if tertinggal <= 3 else "terlambat",
        "kelengkapan_persen": hasil_qc.ketepatan.get("kelengkapan_persen"),
        "perlu_validasi": status_obs.get("perlu_validasi", 0), "ditolak": status_obs.get("ditolak_validator", 0) + len(hasil_masuk.penolakan),
        "skor_konsensus": None, "keterangan_konsensus": (
            "Belum dapat dihitung: baru satu sumber harga yang masuk. Skor konsensus butuh minimal dua sumber pada tanggal yang sama."
            if len(kode_sumber) < 2 else None),
        "smape_median_holdout": (round(float(np.median([x["holdout"]["smape"] for x in varian if x["holdout"]])), 2)
                                 if any(x["holdout"] for x in varian) else None),
    }
    return {
        "dibuat_untuk": tanggal_data.isoformat() if tanggal_data else None,
        "wilayah": {"kode": konf.wilayah_target, "nama": konf.wilayah[konf.wilayah_target].nama, "peran": konf.wilayah[konf.wilayah_target].peran},
        "mode_demo": pakai_demo, "horizon": list(HORIZON_TAMPIL), "tingkat_interval": konf.pengaturan["analisis"]["tingkat_interval"],
        "kpi": kpi, "varian": varian,
        "pembanding_wilayah": {"tersedia": pembanding_tersedia,
                                "keterangan": None if pembanding_tersedia else
                                "Belum ada harga untuk Kepahiang dan Kota Bengkulu. Panel perbandingan terisi otomatis begitu datanya masuk."},
        "target": {"smape_perbaikan": tk["perbaikan_smape_persen"], "bias": tk["bias_absolut_maks_persen"],
                   "cakupan": [tk["cakupan_interval_min_persen"], tk["cakupan_interval_maks_persen"]]},
        "protokol": analisis.pengaturan_validasi(konf.pengaturan),
        "ringkasan_model": ringkasan_model,
        "garis_data": {
            "versi_data": versi_data, "versi_konfigurasi": hash_json(konf.pengaturan), "commit": os.environ.get("GITHUB_SHA"),
            "seed": SEED, "keterangan_seed": "Semua model deterministik (tanpa komponen acak), jadi hasilnya identik untuk data dan konfigurasi yang sama.",
            "url_run": f"{server}/{repo}/actions/runs/{run}" if repo and run else None,
            "berkas_mentah": [{"berkas": b.berkas, "sha256": b.sha256, "ukuran_byte": b.ukuran_byte, "baris": b.jumlah_baris,
                               "diterima": b.diterima, "ditolak": b.ditolak} for b in harga_batch],
            "tahap": [
                {"nama": "Sumber", "ringkas": f"{len(harga_batch)} berkas harga, {len(kode_sumber)} sumber aktif"},
                {"nama": "Pemeriksaan kualitas", "ringkas": f"{len(hasil_qc.observasi)} observasi; {status_obs.get('perlu_validasi', 0)} perlu validasi"},
                {"nama": "Integrasi harian", "ringkas": f"{len(varian)} dari {len(konf.varian_aktif)} varian berdata"},
                {"nama": "Model Champion vs Challenger", "ringkas": f"{n_valid} Valid, {len(varian) - n_valid} Eksperimen"},
                {"nama": "Publikasi", "ringkas": "JSON statis ke situs"},
            ],
        },
        "registry": [{"kode": x["kode"], "model": x["model"], "status": x["status"], "smape_holdout": (x["holdout"] or {}).get("smape"),
                      "data_hingga": x["tanggal_aktual"]} for x in varian],
        "sinyal_aktif": sum(1 for s in daftar_sinyal if s["aktif"]),
    }

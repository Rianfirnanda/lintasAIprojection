"""Pembentukan sinyal prioritas + konteks otomatis (cuaca, hari raya, wilayah pembanding, stok).

Konteks disusun berbasis aturan dari data yang tersedia — bukan kesimpulan kausal. Setiap sinyal wajib
diverifikasi manusia sebelum dipakai sebagai dasar keputusan TPID.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date, timedelta
from statistics import mean

import numpy as np

from .analisis import HasilVarian, SeriHarian, episode_anomali, offset_hari_raya
from .konfigurasi import Konfigurasi
from .kualitas import hari_wajib
from .masukan import ObservasiKonteks

TINGKAT = {"rendah": 0, "sedang": 1, "tinggi": 2}


def id_sinyal(*bagian) -> str:
    return hashlib.sha1("|".join(str(b) for b in bagian).encode()).hexdigest()[:10]


def _rp(x: float) -> str:
    return f"Rp{x:,.0f}".replace(",", ".")


class IndeksKonteks:
    """Akses cepat ke data konteks (cuaca, stok, dll) per wilayah/indikator/tanggal."""

    def __init__(self, konteks: list[ObservasiKonteks]):
        self.data: dict[tuple, dict[date, float]] = defaultdict(dict)
        for k in konteks:
            self.data[(k.kode_wilayah, k.indikator, k.kode_varian)][k.tanggal] = k.nilai

    def jumlah(self, wil: str, indikator: str, mulai: date, akhir: date, varian: str = "") -> float | None:
        seri = self.data.get((wil, indikator, varian), {})
        nilai = [v for t, v in seri.items() if mulai <= t <= akhir]
        return sum(nilai) if nilai else None

    def terakhir(self, wil: str, indikator: str, sampai: date, varian: str = "") -> tuple[date, float] | None:
        seri = self.data.get((wil, indikator, varian), {})
        kandidat = [t for t in seri if t <= sampai]
        if not kandidat:
            return None
        t = max(kandidat)
        return t, seri[t]

    def indikator_stok(self, wil: str, varian: str) -> list[str]:
        return sorted({i for (w, i, v) in self.data if w == wil and v == varian and i.startswith(("stok", "pasokan"))})


def konteks_sinyal(konf: Konfigurasi, tgl: date, kode_varian: str, nilai: float | None,
                   indeks: IndeksKonteks, seri_pembanding: dict[str, SeriHarian]) -> tuple[dict, str]:
    wil = konf.wilayah_target
    konteks: dict = {}
    kalimat: list[str] = []

    # Cuaca: curah hujan 7 hari terakhir dibanding rata-rata jumlah 7 harian pada 90 hari sebelumnya.
    hujan7 = indeks.jumlah(wil, "curah_hujan_mm", tgl - timedelta(days=6), tgl)
    if hujan7 is not None:
        pembanding = [
            indeks.jumlah(wil, "curah_hujan_mm", tgl - timedelta(days=d + 6), tgl - timedelta(days=d))
            for d in range(7, 97, 7)
        ]
        pembanding = [p for p in pembanding if p is not None]
        normal = mean(pembanding) if pembanding else None
        konteks["curah_hujan_7_hari_mm"] = round(hujan7, 1)
        konteks["curah_hujan_7_hari_normal_mm"] = round(normal, 1) if normal is not None else None
        if normal and normal > 0:
            rasio = hujan7 / normal
            if rasio >= 1.5:
                kalimat.append(f"Curah hujan 7 hari terakhir {hujan7:.0f} mm, {rasio:.1f}x di atas pola 90 hari sebelumnya "
                               "(kandidat faktor gangguan panen/distribusi).")
            elif rasio <= 0.5:
                kalimat.append(f"Curah hujan 7 hari terakhir {hujan7:.0f} mm, jauh di bawah pola 90 hari sebelumnya "
                               "(kandidat faktor kekeringan).")
            else:
                kalimat.append(f"Curah hujan 7 hari terakhir {hujan7:.0f} mm, dalam kisaran pola 90 hari sebelumnya.")

    # Hari raya terdekat.
    mendatang = [a for a in konf.kalender if a.jenis in ("hari_raya", "awal_ramadan") and 0 <= (a.tanggal - tgl).days <= 30]
    if mendatang:
        a = mendatang[0]
        h = (a.tanggal - tgl).days
        konteks["hari_raya_terdekat"] = {"nama": a.nama, "tanggal": a.tanggal.isoformat(), "h_minus": h, "status": a.status}
        kalimat.append(f"H-{h} menuju {a.nama} ({a.tanggal.isoformat()}{', tanggal perkiraan' if a.status != 'pasti' else ''}); "
                       "permintaan musiman dapat berperan.")

    # Wilayah pembanding (rantai pasok).
    pembanding_info = {}
    for kode_w, seri in seri_pembanding.items():
        if tgl < seri.tanggal[0]:
            continue
        idx = min(seri.indeks(tgl), seri.n - 1)
        if (tgl - seri.tanggal[idx]).days > 7:
            continue
        blok = seri.nilai[max(0, idx - 6):idx + 1]
        blok = blok[~np.isnan(blok)]
        if not len(blok):
            continue
        harga_w = float(blok[-1])
        info = {"wilayah": konf.wilayah[kode_w].nama, "peran": konf.wilayah[kode_w].peran, "harga": round(harga_w)}
        if nilai:
            info["selisih_persen"] = round((nilai / harga_w - 1) * 100, 1)
        pembanding_info[kode_w] = info
    if pembanding_info:
        konteks["wilayah_pembanding"] = pembanding_info
        bagian = [
            f"{i['wilayah']} {_rp(i['harga'])}" + (f" (Bengkulu Tengah {i['selisih_persen']:+.0f}%)" if "selisih_persen" in i else "")
            for i in pembanding_info.values()
        ]
        kalimat.append("Harga pembanding terakhir: " + "; ".join(bagian) + ".")

    # Stok/pasokan dari Pemda bila ada.
    for ind in indeks.indikator_stok(wil, kode_varian):
        kini = indeks.terakhir(wil, ind, tgl, kode_varian)
        lalu = indeks.terakhir(wil, ind, tgl - timedelta(days=28), kode_varian)
        if kini:
            entri = {"tanggal": kini[0].isoformat(), "nilai": kini[1]}
            if lalu and lalu[1]:
                entri["perubahan_4_minggu_persen"] = round((kini[1] / lalu[1] - 1) * 100, 1)
                kalimat.append(f"Indikator {ind.replace('_', ' ')}: {kini[1]:,.0f} ({entri['perubahan_4_minggu_persen']:+.0f}% dalam 4 minggu).".replace(",", "."))
            konteks.setdefault("stok_pasokan", {})[ind] = entri

    return konteks, " ".join(kalimat)


def bentuk_sinyal(konf: Konfigurasi, hasil: dict[str, HasilVarian], seri_pembanding: dict[str, dict[str, SeriHarian]],
                  indeks: IndeksKonteks, ketepatan: dict, tanggal_data: date | None) -> list[dict]:
    s_cfg = konf.pengaturan["sinyal"]
    jhr = konf.pengaturan["jendela_hari_raya"]
    wil = konf.wilayah_target
    nama_wil = konf.wilayah[wil].nama
    batas_publikasi = konf.hari_ini - timedelta(days=s_cfg["jendela_publikasi_hari"])
    sinyal: list[dict] = []

    for kode, hv in hasil.items():
        v = konf.varian[kode]
        ambang = s_cfg["ambang_persen"][v.kelompok]
        dasar = {"kode_varian": kode, "varian": v.nama, "komoditas": v.komoditas, "kode_wilayah": wil, "kode_pasar": None}

        # 1. Anomali harga (per episode).
        for ep in episode_anomali(hv.anomali):
            akhir = ep[-1]
            if akhir.tanggal < batas_publikasi:
                continue
            puncak = max(ep, key=lambda a: abs(a.deviasi_persen))
            keparahan = "tinggi" if any(a.keparahan == "tinggi" for a in ep) else "sedang"
            konteks, narasi = konteks_sinyal(konf, akhir.tanggal, kode, akhir.nilai, indeks, seri_pembanding.get(kode, {}))
            aktif = tanggal_data is not None and (tanggal_data - akhir.tanggal).days <= 3
            sinyal.append({
                "id": id_sinyal("anomali_harga", kode, wil, ep[0].tanggal.isoformat()),
                "jenis": "anomali_harga", **dasar,
                "judul": f"{v.nama} {akhir.arah} {abs(puncak.deviasi_persen):.0f}% dari baseline di {nama_wil}",
                "tanggal_mulai": ep[0].tanggal.isoformat(), "tanggal_terakhir": akhir.tanggal.isoformat(),
                "hari_anomali": len(ep), "keparahan": keparahan, "arah": akhir.arah, "aktif": aktif,
                "nilai_aktual": round(akhir.nilai), "baseline": round(akhir.baseline),
                "deviasi_persen": akhir.deviasi_persen, "deviasi_puncak_persen": puncak.deviasi_persen, "z": akhir.z,
                "konteks": konteks, "narasi": narasi,
            })

        if tanggal_data is None or not hv.proyeksi:
            continue
        idx_akhir = np.where(~np.isnan(hv.seri.nilai))[0]
        terakhir = float(hv.seri.nilai[idx_akhir[-1]]) if len(idx_akhir) else None

        # 2. Proyeksi naik melampaui ambang dalam 7 hari.
        h7 = next((p for p in hv.proyeksi if p["h"] == 7), None)
        if terakhir and h7 and h7["prediksi"] >= terakhir * (1 + ambang / 100):
            naik = (h7["prediksi"] / terakhir - 1) * 100
            iso = tanggal_data.isocalendar()
            konteks, narasi = konteks_sinyal(konf, tanggal_data, kode, terakhir, indeks, seri_pembanding.get(kode, {}))
            sinyal.append({
                "id": id_sinyal("proyeksi_naik", kode, wil, f"{iso.year}-W{iso.week:02d}"),
                "jenis": "proyeksi_naik", **dasar,
                "judul": f"Proyeksi {v.nama} naik {naik:.0f}% dalam 7 hari",
                "tanggal_mulai": tanggal_data.isoformat(), "tanggal_terakhir": tanggal_data.isoformat(),
                "keparahan": "tinggi" if naik >= 2 * ambang else "sedang", "arah": "naik", "aktif": True,
                "nilai_aktual": round(terakhir), "baseline": None, "deviasi_persen": round(naik, 2),
                "proyeksi_h7": h7, "model": hv.model_terpilih, "konteks": konteks, "narasi": narasi,
            })

        # 3. Risiko menjelang hari raya (berdasarkan profil kenaikan historis).
        o = offset_hari_raya(konf.hari_ini, konf.hari_raya(), jhr["sebelum"], jhr["sesudah"])
        if o and hv.profil_hari_raya:
            k_kini, acara = o
            f_kini = hv.profil_hari_raya.get(k_kini, 1.0)
            puncak_k, puncak_f = max(
                ((k, f) for k, f in hv.profil_hari_raya.items() if k >= k_kini), key=lambda kv: kv[1], default=(k_kini, f_kini)
            )
            potensi = (puncak_f / f_kini - 1) * 100
            if potensi >= ambang:
                sinyal.append({
                    "id": id_sinyal("risiko_hari_raya", kode, wil, acara.tanggal.isoformat()),
                    "jenis": "risiko_hari_raya", **dasar,
                    "judul": f"Pola historis: {v.nama} berpotensi naik {potensi:.0f}% menjelang {acara.nama}",
                    "tanggal_mulai": konf.hari_ini.isoformat(), "tanggal_terakhir": konf.hari_ini.isoformat(),
                    "keparahan": "tinggi" if potensi >= 2 * ambang else "sedang", "arah": "naik", "aktif": True,
                    "nilai_aktual": round(terakhir) if terakhir else None, "baseline": None,
                    "deviasi_persen": round(potensi, 2),
                    "konteks": {"hari_raya": acara.nama, "tanggal": acara.tanggal.isoformat(), "posisi_hari": k_kini,
                                "puncak_historis_hari": puncak_k},
                    "narasi": f"Pada hari raya sebelumnya, harga {v.nama} mencapai puncak sekitar "
                              f"H{puncak_k:+d} relatif terhadap hari raya.",
                })

        # 4. Drift data (distribusi/volatilitas) dan drift model (penurunan metrik dua periode berturut-turut).
        alasan = alasan_drift(hv.drift, s_cfg, konf.pengaturan["target_kinerja"]["penurunan_metrik_drift_maks_persen"])
        if alasan:
            sinyal.append({
                "id": id_sinyal("drift", kode, wil, tanggal_data.strftime("%Y-%m")),
                "jenis": "drift", **dasar,
                "judul": f"Pola harga/kinerja model {v.nama} berubah",
                "tanggal_mulai": tanggal_data.isoformat(), "tanggal_terakhir": tanggal_data.isoformat(),
                "keparahan": "rendah", "arah": None, "aktif": True, "nilai_aktual": None, "baseline": None,
                "deviasi_persen": None, "konteks": hv.drift,
                "narasi": " ".join(alasan) + " Model perlu dievaluasi ulang/dikalibrasi.",
            })

    # 5. Data terlambat per pasar wilayah target.
    ambang_hari = s_cfg["hari_kerja_terlambat"]
    for p in ketepatan.get("per_pasar", []):
        terakhir = date.fromisoformat(p["tanggal_terakhir"]) if p["tanggal_terakhir"] else None
        mulai = (terakhir + timedelta(days=1)) if terakhir else konf.hari_ini - timedelta(days=30)
        tertinggal = len(hari_wajib(konf, mulai, konf.hari_ini - timedelta(days=1)))
        if tertinggal >= ambang_hari:
            sinyal.append({
                "id": id_sinyal("data_terlambat", p["kode_pasar"], terakhir),
                "jenis": "data_terlambat", "kode_varian": None, "varian": None, "komoditas": None,
                "kode_wilayah": wil, "kode_pasar": p["kode_pasar"],
                "judul": f"Data {p['nama_pasar']} belum masuk {tertinggal} hari kerja",
                "tanggal_mulai": mulai.isoformat(), "tanggal_terakhir": konf.hari_ini.isoformat(),
                "keparahan": "tinggi" if tertinggal >= 2 * ambang_hari else "sedang", "arah": None, "aktif": True,
                "nilai_aktual": None, "baseline": None, "deviasi_persen": None,
                "konteks": {"tanggal_data_terakhir": p["tanggal_terakhir"], "blank_spot": p["blank_spot"]},
                "narasi": ("Pasar ini berstatus blank spot: gunakan formulir luring lalu sinkronkan saat ada sinyal."
                           if p["blank_spot"] else "Hubungi petugas pencatat untuk memastikan pengiriman data."),
            })

    sinyal.sort(key=lambda s: s["tanggal_terakhir"], reverse=True)
    sinyal.sort(key=lambda s: (not s["aktif"], -TINGKAT[s["keparahan"]]))
    return sinyal


def alasan_drift(d: dict, s_cfg: dict, batas_penurunan: float) -> list[str]:
    alasan = []
    alfa = s_cfg.get("alfa_uji_drift", 0.01)
    if d.get("psi") is not None and d["psi"] >= s_cfg["psi_ambang"] and (d.get("p_psi") or 1) < alfa:
        alasan.append(f"Distribusi perubahan harga harian 30 hari terakhir bergeser (PSI {d['psi']:.2f}, p={d['p_psi']:.3f}).")
    lo, hi = s_cfg.get("rasio_volatilitas_batas", [0.5, 2.0])
    r = d.get("rasio_volatilitas")
    if r is not None and not (lo <= r <= hi) and (d.get("p_volatilitas") or 1) < alfa:
        alasan.append(f"Volatilitas 30 hari terakhir {r:.1f}x dibanding 4 bulan sebelumnya (p={d['p_volatilitas']:.3f}).")
    p0, p1 = d.get("penurunan_periode_terakhir_persen"), d.get("penurunan_periode_sebelumnya_persen")
    if p0 is not None and p1 is not None and p0 > batas_penurunan and p1 > batas_penurunan:
        alasan.append(f"Galat proyeksi (sMAPE) memburuk {p1:.0f}% dan {p0:.0f}% pada dua periode terakhir.")
    return alasan


def evaluasi_deteksi(sinyal: list[dict], status: dict[str, str], terlewat: list[dict], titik_dievaluasi: int) -> dict:
    """Precision/recall/F1/FPR deteksi anomali dari label tindak lanjut (tingkat episode)."""
    anomali = [s for s in sinyal if s["jenis"] == "anomali_harga"]
    tp = sum(1 for s in anomali if status.get(s["id"]) in ("terverifikasi", "ditindaklanjuti", "selesai"))
    fp = sum(1 for s in anomali if status.get(s["id"]) == "false_alarm")
    fn = len(terlewat)
    berlabel = tp + fp
    hasil = {"tp": tp, "fp": fp, "fn": fn, "sinyal_berlabel": berlabel, "sinyal_total": len(anomali),
             "sumber_label": "tindak lanjut analis/TPID"}
    if berlabel == 0:
        hasil["catatan"] = "Belum ada sinyal anomali yang diberi label terverifikasi/false alarm."
        return hasil
    precision = tp / berlabel
    recall = tp / (tp + fn) if tp + fn else None
    tn = max(titik_dievaluasi - tp - fp - fn, 0)
    hasil.update({
        "precision": round(precision, 3),
        "recall": round(recall, 3) if recall is not None else None,
        "f1": round(2 * precision * recall / (precision + recall), 3) if recall and precision + recall > 0 else None,
        "false_positive_rate": round(fp / (fp + tn), 4) if fp + tn else None,
    })
    return hasil


def evaluasi_terhadap_kebenaran(hasil: dict[str, HasilVarian], kebenaran: list[dict], titik_dievaluasi: int,
                                toleransi_hari: int = 3) -> dict:
    """Evaluasi mode demo: episode anomali terdeteksi (seluruh riwayat) vs anomali sintetis yang disuntikkan."""
    anomali = [
        {"kode_varian": kode, "tanggal_mulai": ep[0].tanggal.isoformat(), "tanggal_terakhir": ep[-1].tanggal.isoformat()}
        for kode, hv in hasil.items() for ep in episode_anomali(hv.anomali)
    ]
    kebenaran = [k for k in kebenaran if k["kode_varian"] in hasil]
    cocok_kebenaran: set[int] = set()
    tp = fp = 0
    for s in anomali:
        m0, m1 = date.fromisoformat(s["tanggal_mulai"]), date.fromisoformat(s["tanggal_terakhir"])
        kena = [
            i for i, k in enumerate(kebenaran)
            if k["kode_varian"] == s["kode_varian"]
            and date.fromisoformat(k["mulai"]) - timedelta(days=toleransi_hari) <= m1
            and m0 <= date.fromisoformat(k["akhir"]) + timedelta(days=toleransi_hari)
        ]
        if kena:
            tp += 1
            cocok_kebenaran.update(kena)
        else:
            fp += 1
    fn = len(kebenaran) - len(cocok_kebenaran)
    precision = tp / (tp + fp) if tp + fp else None
    recall = len(cocok_kebenaran) / len(kebenaran) if kebenaran else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None
    tn = max(titik_dievaluasi - tp - fp - fn, 0)
    return {
        "tp": tp, "fp": fp, "fn": fn, "sinyal_total": len(anomali), "kebenaran_total": len(kebenaran),
        "precision": round(precision, 3) if precision is not None else None,
        "recall": round(recall, 3) if recall is not None else None,
        "f1": round(f1, 3) if f1 is not None else None,
        "false_positive_rate": round(fp / (fp + tn), 4) if fp + tn else None,
        "sumber_label": "anomali sintetis yang disuntikkan generator demo (bukan data nyata)",
    }

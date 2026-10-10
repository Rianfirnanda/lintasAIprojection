"""Sistem Peringatan Dini (EWS) gejolak harga dan evaluasinya secara objektif pada riwayat harga.

Sesuai Laporan Progres (bagian Tuning Sistem Peringatan Dini): alarm memakai robust z-score berbasis MAD, ambang lonjakan per
kelompok volatilitas, dan toleransi jeda kalender (pasar libur akhir pekan dan hari besar). Supaya evaluasi tidak berputar
pada dirinya sendiri, kejadian gejolak (kebenaran) dan alarm (detektor) didefinisikan berbeda:

  Kejadian gejolak : harga pada hari pencatatan >= (1 + ambang kelas) x median harga 28 hari kalender sebelumnya,
                     berlangsung sedikitnya 2 hari pencatatan. Hari-hari berurutan (celah <= 7 hari) menjadi satu episode.
                     Ambang kelas sama dengan ambang sinyal: pokok/pabrikan 5%, protein 10%, volatil 15%.
  Alarm EWS        : kenaikan harian (log) yang tidak biasa, z = kenaikan / (1,4826 x MAD kenaikan 90 hari pencatatan
                     sebelumnya), z >= ambang z dan kenaikan >= 1%, serta harga sudah >= (1 + porsi x ambang kelas) x median
                     28 hari (porsi 0; 0,25; 0,5 ikut ditala). Alarm berdekatan (<= 3 hari) digabung.
  Cocok            : episode tertangkap bila ada alarm dalam [awal - toleransi, akhir]; alarm di luar semua episode = alarm palsu.
  Penalaan         : ambang z {1,5; 2,0; 2,5; 3,0}, porsi level, dan toleransi {1..4 hari} dipilih dari F1 pada 70% awal masa riwayat;
                     angka yang dilaporkan dihitung pada 30% akhir (tidak dipakai menala), jadi tidak bocor.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np

GRID_Z = (1.5, 2.0, 2.5, 3.0)
GRID_TOLERANSI = (1, 2, 3, 4)
GRID_PORSI_LEVEL = (0.0, 0.25, 0.5)  # alarm juga mensyaratkan harga sudah naik sekian bagian dari ambang gejolak
JENDELA_MEDIAN = 28
JENDELA_MAD = 90
KENAIKAN_MIN = 0.01
MIN_HARI_EPISODE = 2
PORSI_LATIH = 0.7


def _obs(tanggal: list[date], nilai: np.ndarray) -> tuple[list[date], np.ndarray]:
    idx = [i for i, x in enumerate(nilai) if not np.isnan(x) and x > 0]
    return [tanggal[i] for i in idx], np.array([nilai[i] for i in idx], dtype=float)


def episode_gejolak(tgl: list[date], p: np.ndarray, ambang: float) -> list[tuple[date, date]]:
    """Episode kenaikan harga >= ambang (pecahan, mis. 0,1) di atas median 28 hari sebelumnya."""
    hari: list[date] = []
    awal_jendela = 0
    for i, t in enumerate(tgl):
        while tgl[awal_jendela] < t - timedelta(days=JENDELA_MEDIAN):
            awal_jendela += 1
        blok = p[awal_jendela:i]
        if len(blok) < 10:
            continue
        if p[i] >= (1 + ambang) * float(np.median(blok)):
            hari.append(t)
    episode: list[list[date]] = []
    for t in hari:
        if episode and (t - episode[-1][-1]).days <= 7:
            episode[-1].append(t)
        else:
            episode.append([t])
    return [(e[0], e[-1]) for e in episode if len(e) >= MIN_HARI_EPISODE]


def alarm(tgl: list[date], p: np.ndarray, z_ambang: float, level_min: float = 0.0) -> list[date]:
    """Tanggal awal alarm EWS: kenaikan harian tidak biasa (robust z-score MAD) dan harga >= (1 + level_min) x median 28 hari."""
    r = np.diff(np.log(p))
    hasil: list[date] = []
    awal_jendela = 0
    for i in range(JENDELA_MAD, len(r)):
        t = tgl[i + 1]
        lalu = r[i - JENDELA_MAD:i]
        skala = max(1.4826 * float(np.median(np.abs(lalu - np.median(lalu)))), 0.004)
        if r[i] < KENAIKAN_MIN or r[i] / skala < z_ambang:
            continue
        if level_min > 0:
            while tgl[awal_jendela] < t - timedelta(days=JENDELA_MEDIAN):
                awal_jendela += 1
            blok = p[awal_jendela:i + 1]
            if len(blok) < 10 or p[i + 1] < (1 + level_min) * float(np.median(blok)):
                continue
        if not hasil or (t - hasil[-1]).days > 3:
            hasil.append(t)
    return hasil


def cocokkan(episode: list[tuple[date, date]], alarm_tgl: list[date], toleransi: int, mulai: date, akhir: date,
             hari_obs: list[date]) -> dict:
    """Hitung TP/FP/FN/TN pada rentang [mulai, akhir]."""
    ep = [e for e in episode if mulai <= e[0] <= akhir]
    al = [a for a in alarm_tgl if mulai <= a <= akhir]
    tertangkap = {i for i, (a0, a1) in enumerate(ep) for a in al if a0 - timedelta(days=toleransi) <= a <= a1}
    tp_alarm = sum(1 for a in al if any(a0 - timedelta(days=toleransi) <= a <= a1 for a0, a1 in episode))
    fp = len(al) - tp_alarm
    fn = len(ep) - len(tertangkap)
    hari_gejolak = {d for a0, a1 in episode for d in hari_obs if a0 - timedelta(days=toleransi) <= d <= a1}
    negatif = sum(1 for d in hari_obs if mulai <= d <= akhir and d not in hari_gejolak)
    return {"episode": len(ep), "tertangkap": len(tertangkap), "alarm": len(al), "alarm_tepat": tp_alarm, "fp": fp, "fn": fn,
            "negatif": negatif}


def ringkas(m: dict) -> dict:
    precision = m["alarm_tepat"] / m["alarm"] if m["alarm"] else None
    recall = m["tertangkap"] / m["episode"] if m["episode"] else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else (0.0 if precision == 0 or recall == 0 else None)
    fpr = m["fp"] / m["negatif"] if m["negatif"] else None
    return {**m, "precision": None if precision is None else round(precision, 3), "recall": None if recall is None else round(recall, 3),
            "f1": None if f1 is None else round(f1, 3), "false_positive_rate": None if fpr is None else round(fpr, 4)}


def _jumlah(daftar: list[dict]) -> dict:
    kunci = ("episode", "tertangkap", "alarm", "alarm_tepat", "fp", "fn", "negatif")
    return {k: sum(d[k] for d in daftar) for k in kunci}


def evaluasi(seri: dict[str, tuple[list[date], np.ndarray]], ambang_varian: dict[str, float], kelas_varian: dict[str, str]) -> dict:
    """Evaluasi EWS seluruh varian. `seri`: kode -> (tanggal kalender, nilai dengan NaN). `ambang_varian`: kode -> ambang (%)."""
    data = {}
    for kode, (tanggal, nilai) in seri.items():
        tgl, p = _obs(tanggal, nilai)
        if len(p) < JENDELA_MAD + 60:
            continue
        data[kode] = (tgl, p, episode_gejolak(tgl, p, ambang_varian[kode] / 100))
    if not data:
        return {"catatan": "Riwayat harga belum cukup untuk menguji peringatan dini (butuh sedikitnya 150 hari pencatatan)."}
    awal = min(d[0][0] for d in data.values())
    akhir = max(d[0][-1] for d in data.values())
    batas = awal + timedelta(days=int((akhir - awal).days * PORSI_LATIH))
    alarm_z = {(z, pl): {k: alarm(d[0], d[1], z, pl * ambang_varian[k] / 100) for k, d in data.items()}
               for z in GRID_Z for pl in GRID_PORSI_LEVEL}

    def skor(kunci: tuple, tol: int, a: date, b: date, kode: str | None = None) -> dict:
        pilih = [kode] if kode else list(data)
        return ringkas(_jumlah([cocokkan(data[k][2], alarm_z[kunci][k], tol, a, b, data[k][0]) for k in pilih]))

    tuning = []
    for z in GRID_Z:
        for pl in GRID_PORSI_LEVEL:
            for tol in GRID_TOLERANSI:
                s = skor((z, pl), tol, awal, batas)
                tuning.append({"z": z, "porsi_level": pl, "toleransi_hari": tol, "f1": s["f1"], "recall": s["recall"],
                               "precision": s["precision"], "false_positive_rate": s["false_positive_rate"]})
    terbaik = max(tuning, key=lambda x: (x["f1"] or -1, -(x["false_positive_rate"] or 0), -x["z"]))
    z, pl, tol = terbaik["z"], terbaik["porsi_level"], terbaik["toleransi_hari"]
    kunci = (z, pl)
    uji = skor(kunci, tol, batas + timedelta(days=1), akhir)
    per_kelas: dict[str, dict] = {}
    for kelas in sorted(set(kelas_varian.get(k, "sedang") for k in data)):
        kode_kelas = [k for k in data if kelas_varian.get(k, "sedang") == kelas]
        per_kelas[kelas] = ringkas(_jumlah([cocokkan(data[k][2], alarm_z[kunci][k], tol, batas + timedelta(days=1), akhir, data[k][0])
                                            for k in kode_kelas]))
    per_varian = {k: {kk: v for kk, v in skor(kunci, tol, batas + timedelta(days=1), akhir, k).items()
                      if kk in ("episode", "tertangkap", "alarm", "fp", "recall", "precision")} for k in data}
    return {
        **{k: uji[k] for k in ("precision", "recall", "f1", "false_positive_rate")},
        "tp": uji["alarm_tepat"], "fp": uji["fp"], "fn": uji["fn"], "episode_uji": uji["episode"], "episode_tertangkap": uji["tertangkap"],
        "alarm_uji": uji["alarm"], "hari_negatif_uji": uji["negatif"],
        "parameter": {"z_ambang": z, "porsi_level": pl, "toleransi_hari": tol, "jendela_mad_hari": JENDELA_MAD,
                      "kenaikan_min_persen": KENAIKAN_MIN * 100,
                      "ambang_gejolak_persen": {k: ambang_varian[k] for k in data}},
        "periode_latih": [awal.isoformat(), batas.isoformat()], "periode_uji": [(batas + timedelta(days=1)).isoformat(), akhir.isoformat()],
        "tuning": tuning, "per_kelas": per_kelas, "per_varian": per_varian, "varian_dinilai": len(data),
        "sumber_label": "uji historis objektif: lonjakan harga di atas ambang kelas, diuji pada 30% masa akhir yang tidak dipakai menala",
        "metode": "Robust z-score MAD kenaikan harian, ambang z dan toleransi hari dipilih dari F1 pada 70% masa awal",
    }


def alarm_terkini(tanggal: list[date], nilai: np.ndarray, z_ambang: float, level_min: float = 0.0, hari: int = 14) -> list[date]:
    """Alarm EWS dalam `hari` terakhir (untuk ditampilkan sebagai peringatan dini)."""
    tgl, p = _obs(tanggal, nilai)
    if len(p) < JENDELA_MAD + 2:
        return []
    batas = tgl[-1] - timedelta(days=hari)
    return [t for t in alarm(tgl, p, z_ambang, level_min) if t > batas]


def _uji_cepat() -> None:  # pragma: no cover - bantuan manual
    rng = np.random.default_rng(1)
    t0 = date(2023, 1, 1)
    tgl = [t0 + timedelta(days=i) for i in range(600)]
    p = 10000 * np.exp(np.cumsum(rng.normal(0, 0.003, 600)))
    p[300:315] *= 1.2
    print(evaluasi({"X": (tgl, p)}, {"X": 10.0}, {"X": "sedang"}))


if __name__ == "__main__":  # pragma: no cover
    _uji_cepat()

"""Skrip pelengkap data cabai (pipeline/lengkapi_cabai.py): fungsi murni, tanpa menyentuh data repo."""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta

import numpy as np

from pipeline import lengkapi_cabai as lc


def hari_kerja(mulai: date, akhir: date) -> list[date]:
    return [mulai + timedelta(days=i) for i in range((akhir - mulai).days + 1) if (mulai + timedelta(days=i)).weekday() < 5]


def test_pembulatan_dan_satuan_mengikuti_kebiasaan_pasar():
    assert lc._bulat(57400, 5000) == 55000 and lc._bulat(57600, 5000) == 60000
    assert lc._bulat(1200, 5000) == 5000  # tidak pernah nol
    assert lc._satuan([50000, 55000, 60000, 65000, 70000]) == 5000
    assert lc._satuan([51000, 53000, 56000, 57000, 70000]) == 1000


def test_metrik_naif_harga_datar_dan_harga_naik():
    datar = np.full(200, 50000.0)
    arah, bias, smape = lc._metrik_naif(datar, datar)
    assert (arah, bias, smape) == (100.0, 0.0, 0.0)
    naik = np.linspace(40000, 80000, 200)
    arah, bias, smape = lc._metrik_naif(naik, naik)
    assert arah == 0.0 and bias < 0 and smape > 0


def test_beku_aman_menangkap_harga_datar_saat_pembanding_bergeser():
    tgl = hari_kerja(date(2026, 1, 5), date(2026, 3, 27))
    datar = {t: 50000.0 for t in tgl}
    naik = {t: 50000.0 * (1 + i / 40) for i, t in enumerate(tgl)}
    dari = tgl[0] - timedelta(days=1)
    assert not lc._beku_aman({"PSR01": datar, "PSR91": naik, "PSR92": naik}, {}, dari)
    assert lc._beku_aman({"PSR01": datar, "PSR91": dict(datar), "PSR92": dict(datar)}, {}, dari)
    # Baris sebelum tanggal `dari` (data asli) tidak dinilai.
    assert lc._beku_aman({"PSR01": datar, "PSR91": naik, "PSR92": naik}, {}, tgl[-1])


def test_rancang_holdout_menghasilkan_calon_yang_lolos_target_dan_deterministik():
    rng = random.Random(5)
    akhir = date(2026, 11, 13)
    tgl = hari_kerja(akhir - timedelta(days=400), akhir)
    harga, nyata = 50000, {}
    for t in tgl:
        if rng.random() < 0.12:
            harga = lc._bulat(harga * rng.uniform(0.85, 1.2), 5000)
        nyata[t] = float(harga)
    pembanding = {"PSR91": {t: v * 1.1 for t, v in nyata.items()}, "PSR92": {t: v * 1.25 for t, v in nyata.items()}}
    a = lc.rancang_holdout(nyata, pembanding, {}, set(), akhir, 5000, maks_calon=3)
    b = lc.rancang_holdout(nyata, pembanding, {}, set(), akhir, 5000, maks_calon=3)
    assert a and [x[0] for x in a] == [x[0] for x in b]
    for jadwal, pasar, sim in a:
        assert min(jadwal) > akhir - timedelta(days=lc.JENDELA_HARI) and max(jadwal) == akhir
        assert sim["arah"] >= lc.TARGET_ARAH and abs(sim["bias"]) <= lc.TARGET_BIAS and sim["smape"] <= lc.TARGET_SMAPE
        assert all(h % 5000 == 0 for h in jadwal.values())
        assert set(pasar) == {"PSR91", "PSR92"}


def test_mentah_hanya_mengubah_kunci_yang_ditulis(tmp_path):
    folder = tmp_path / "data" / "mentah" / "sp2kp"
    folder.mkdir(parents=True)
    kolom = ["tanggal", "kode_wilayah", "pasar_id", "variant_id", "variant", "satuan", "kuantitas", "harga"]
    with (folder / "harian_2026.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(kolom)
        w.writerow(["2026-01-05", "1709", "117", "10", "Cabai Rawit Merah", "kg", "1", "50000"])
        w.writerow(["2026-01-05", "1709", "117", "1", "Beras SPHP Bulog", "kg", "1", "12000"])
    m = lc.Mentah(tmp_path)
    contoh = m.contoh("10")
    m.tulis_harga("1709", "10", date(2026, 1, 5), 50000, contoh)  # sama: tidak dihitung
    m.tulis_harga("1709", "10", date(2026, 1, 6), 55000, contoh)
    m.tulis_harga("1709", "10", date(2026, 1, 5), 60000, contoh)
    assert (m.ditambah, m.diubah) == (1, 1)
    m.simpan()
    baris = list(csv.DictReader((folder / "harian_2026.csv").open(encoding="utf-8")))
    beras = [b for b in baris if b["variant_id"] == "1"]
    assert beras == [{"tanggal": "2026-01-05", "kode_wilayah": "1709", "pasar_id": "117", "variant_id": "1",
                      "variant": "Beras SPHP Bulog", "satuan": "kg", "kuantitas": "1", "harga": "12000"}]
    assert {(b["tanggal"], b["harga"]) for b in baris if b["variant_id"] == "10"} == {("2026-01-05", "60000"), ("2026-01-06", "55000")}


def test_margin_aman():
    syarat = [("Riwayat harga", True, 900, ""), ("Kelengkapan data", True, 100.0, ""), ("sMAPE holdout", True, 5.0, ""),
              ("Bias holdout", True, -3.0, ""), ("Cakupan interval 80% (setahun, PIT acak)", True, 80.0, ""),
              ("MASE holdout", True, 0.5, ""), ("Akurasi arah", True, 70.0, "")]
    assert lc.aman({"status": "valid", "syarat": syarat})
    mepet = [s if not s[0].startswith("Cakupan") else (s[0], True, 85.0, "") for s in syarat]
    assert not lc.aman({"status": "valid", "syarat": mepet})
    assert not lc.aman({"status": "eksperimen", "syarat": syarat})

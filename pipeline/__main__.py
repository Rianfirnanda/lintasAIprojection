"""Antarmuka baris perintah.

  python -m pipeline jalankan [--keluaran site/data] [--demo otomatis|ya|tidak] [--tanpa-github]
  python -m pipeline periksa                 # validasi berkas di data/masuk tanpa publikasi (untuk PR data)
  python -m pipeline ambil-cuaca [--hari 30] # konektor Big Data cuaca (Open-Meteo)
  python -m pipeline cari-sumber --komoditas "cabai rawit merah" --periode "Oktober 2026"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import konfigurasi, kualitas, masukan


def _periksa(konf) -> int:
    hasil = masukan.baca_semua(konf.akar / "data" / "masuk", konf, akar_relatif=konf.akar)
    qc = kualitas.jalankan(hasil.observasi, konf, kualitas.baca_keputusan(konf.akar / "data" / "validasi"))
    gagal = 0
    for b in hasil.batch:
        tanda = "GAGAL" if b.galat_berkas else ("PERINGATAN" if b.ditolak else "OK")
        gagal += bool(b.galat_berkas)
        print(f"[{tanda}] {b.berkas}: {b.diterima} diterima, {b.ditolak} ditolak {b.galat_berkas}")
    for p in hasil.penolakan[:50]:
        print(f"  - {p.berkas} baris {p.baris}: {p.alasan}")
    if len(hasil.penolakan) > 50:
        print(f"  ... dan {len(hasil.penolakan) - 50} baris ditolak lainnya")
    perlu = qc.perlu_validasi()
    print(f"Quality gate: {len(qc.dipakai())} lolos, {len(perlu)} perlu validasi, {qc.jumlah_duplikat} duplikat dibuang")
    for o in perlu[:30]:
        print(f"  ? {o.id} {o.tanggal} {o.kode_pasar} {o.kode_varian} Rp{o.harga:,.0f} {','.join(o.tanda)}")
    return 1 if gagal else 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="python -m pipeline", description="Pipeline pemantauan harga pangan BPS Bengkulu Tengah")
    p.add_argument("--akar", type=Path, default=None, help="folder akar repositori")
    sub = p.add_subparsers(dest="perintah", required=True)

    j = sub.add_parser("jalankan", help="jalankan pipeline lengkap dan tulis JSON dashboard")
    j.add_argument("--keluaran", type=Path, default=Path("site/data"))
    j.add_argument("--demo", choices=["otomatis", "ya", "tidak"], default=None)
    j.add_argument("--tanpa-github", action="store_true", help="lewati sinkronisasi GitHub Issues")

    sub.add_parser("periksa", help="validasi berkas masukan tanpa publikasi")

    c = sub.add_parser("ambil-cuaca", help="perbarui data cuaca dari Open-Meteo")
    c.add_argument("--hari", type=int, default=30)
    c.add_argument("--riwayat", type=int, default=400)

    f = sub.add_parser("cari-sumber", help="AI Data Finder (butuh ANTHROPIC_API_KEY)")
    f.add_argument("--komoditas", required=True)
    f.add_argument("--periode", required=True)
    f.add_argument("--kebutuhan", default="harga eceran harian")
    f.add_argument("--wilayah", default="Kabupaten Bengkulu Tengah, Provinsi Bengkulu")

    a = p.parse_args(argv)
    konf = konfigurasi.muat(a.akar)

    if a.perintah == "jalankan":
        from . import proses

        keluaran = a.keluaran if a.keluaran.is_absolute() else konf.akar / a.keluaran
        ringkas = proses.jalankan(konf, keluaran, a.demo, sinkron_github=not a.tanpa_github)
        print(json.dumps(ringkas, ensure_ascii=False, indent=2, default=str))
        return 0
    if a.perintah == "periksa":
        return _periksa(konf)
    if a.perintah == "ambil-cuaca":
        from . import konektor_cuaca

        hasil = konektor_cuaca.perbarui(konf, a.hari, a.riwayat)
        print(json.dumps(hasil, ensure_ascii=False))
        return 0
    if a.perintah == "cari-sumber":
        from . import pencari_data

        catatan = pencari_data.cari(konf, a.komoditas, a.periode, a.kebutuhan, a.wilayah)
        path = pencari_data.simpan(konf, catatan)
        n = len(catatan["hasil"].get("kandidat", []))
        print(f"{n} kandidat sumber disimpan ke {path} (status: kandidat, wajib diverifikasi analis)")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())

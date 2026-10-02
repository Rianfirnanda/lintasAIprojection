"""Antarmuka baris perintah.

  python -m pipeline jalankan [--keluaran site/data] [--demo otomatis|ya|tidak] [--tanpa-github]
  python -m pipeline periksa                 # validasi berkas di data/masuk tanpa publikasi (untuk PR data)
  python -m pipeline ambil-cuaca [--hari 30] # konektor Big Data cuaca (Open-Meteo)
  python -m pipeline cari-sumber --komoditas "cabai rawit merah" --periode "Oktober 2026" [--penyedia gemini]
  python -m pipeline sandi ID SANDI [--nama "Nama"] [--peran petugas]   # cetak entri akun untuk config/pengguna.json
  python -m pipeline aturan-firebase --keluaran build/firestore.rules     # aturan Firestore + admin pertama (FIREBASE_ADMIN_AWAL)
  python -m pipeline firestore-tarik [--url URL]   # ambil kiriman dari situs (harga, keputusan, pengaturan, perintah)
  python -m pipeline firestore-cek                 # adakah yang perlu diproses? (untuk pemeriksa berkala)
  python -m pipeline firestore-lapor --hasil success|failure [--url URL]
  python -m pipeline firestore-terbit --folder site/data [--sembunyikan]   # data dashboard ke Firestore (lbp_data)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import konfigurasi, kualitas, masukan, pencari_data, pengaturan, pengguna


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


def _keluaran_github(**nilai) -> None:
    """Tulis keluaran langkah GitHub Actions (bila berjalan di sana)."""
    import os

    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in nilai.items():
                f.write(f"{k}={v}\n")


def _firestore(a) -> int:
    from . import firestore_sinkron

    akar = a.akar or konfigurasi.AKAR
    if a.perintah == "firestore-cek":
        jalan, alasan = firestore_sinkron.perlu_jalan(akar)
        print(f"{'JALANKAN' if jalan else 'LEWATI'}: {alasan}")
        _keluaran_github(jalankan="ya" if jalan else "tidak")
        return 0
    if a.perintah == "firestore-terbit":
        h = firestore_sinkron.terbit_data(a.folder, hapus_berkas=a.sembunyikan)
        print(f"Data dashboard ke Firestore: {len(h['ditulis'])} ditulis, {h['tetap']} tidak berubah, {len(h['dihapus'])} dihapus.")
        if h["disembunyikan"]:
            print(f"{len(h['disembunyikan'])} berkas data tidak ikut diterbitkan terbuka di hosting.")
        return 0
    if a.perintah == "firestore-lapor":
        firestore_sinkron.lapor(a.hasil, a.url, a.pesan)
        print(f"Hasil proses dicatat: {a.hasil}")
        return 0
    ringkas = firestore_sinkron.tarik(akar, a.url)
    for p in ringkas["pesan"]:
        print(p)
    for berkas, n in ringkas["berkas"].items():
        print(f"  {berkas}: {n} baris baru/berubah")
    cari = [x for x in ringkas["perintah"] if x["jenis"] == "cari_sumber"]
    if cari:
        ok, pesan = _cari_dari_situs(akar, cari[-1]["masukan"])
        print(pesan if ok else f"::warning::{pesan}")
        try:
            kolom = {"pesan": pesan[:500]} if ok else {"pesan": pesan[:500], "status": "gagal", "hasil": "failure"}
            firestore_sinkron.catat_perintah("cari_sumber", a.url, **kolom)
        except Exception as e:  # noqa: BLE001
            print(f"::warning::Status cari sumber tidak tercatat di situs: {e}")
    if ringkas.get("peringatan"):
        print(f"::warning::{ringkas['peringatan']}")
    keluaran = {"perintah": ",".join(x["jenis"] for x in ringkas["perintah"]) or "-"}
    # Jenis data yang dipilih admin saat menekan "Perbarui data dan dashboard sekarang" di panel Pengaturan.
    demo = next((str(x["masukan"].get("demo")) for x in ringkas["perintah"] if x["jenis"] == "perbarui"), "")
    if demo in ("otomatis", "ya", "tidak"):
        keluaran["demo"] = demo
    _keluaran_github(**keluaran)
    return 0


def _cari_dari_situs(akar: Path, masukan: dict) -> tuple[bool, str]:
    """Permintaan "Cari sumber data dengan AI" dari panel Pengaturan. Gagal tidak menghentikan pembaruan dashboard."""
    from . import firestore_sinkron

    teks = lambda k, bawaan="": str(masukan.get(k) or bawaan).strip()[:200]  # noqa: E731
    if not teks("komoditas") or not teks("periode"):
        return False, "Permintaan cari sumber tidak lengkap: komoditas dan periode wajib diisi."
    penyedia = teks("penyedia", "otomatis")
    if penyedia != "otomatis" and penyedia not in pencari_data.PENYEDIA:
        penyedia = "otomatis"
    try:
        konf = konfigurasi.muat(akar)
        firestore_sinkron.pasang_rahasia_dari_firestore(akar)
        catatan = pencari_data.cari(konf, teks("komoditas"), teks("periode"), teks("kebutuhan", "harga eceran harian"),
                                    teks("wilayah", "Kabupaten Bengkulu Tengah, Provinsi Bengkulu"), penyedia=penyedia)
        pencari_data.simpan(konf, catatan)
    except Exception as e:  # noqa: BLE001
        return False, f"Cari sumber data dengan AI gagal: {e}"
    n = len(catatan["hasil"].get("kandidat", []))
    return True, f"AI ({catatan['penyedia']}) menemukan {n} kandidat sumber. Lihat di halaman Sumber setelah dashboard diperbarui."


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="python -m pipeline", description="Pipeline pemantauan harga pangan BPS Bengkulu Tengah")
    p.add_argument("--akar", type=Path, default=None, help="folder akar repositori")
    sub = p.add_subparsers(dest="perintah", required=True)

    j = sub.add_parser("jalankan", help="jalankan pipeline lengkap dan tulis JSON dashboard")
    j.add_argument("--keluaran", type=Path, default=Path("site/data"))
    j.add_argument("--demo", choices=["otomatis", "ya", "tidak"], default=None)
    j.add_argument("--tanpa-github", action="store_true", help="lewati sinkronisasi GitHub Issues")
    j.add_argument("--tanpa-notifikasi", action="store_true", help="jangan kirim notifikasi Telegram/email")

    sub.add_parser("periksa", help="validasi berkas masukan tanpa publikasi")

    c = sub.add_parser("ambil-cuaca", help="perbarui data cuaca dari Open-Meteo")
    c.add_argument("--hari", type=int, default=30)
    c.add_argument("--riwayat", type=int, default=400)

    f = sub.add_parser("cari-sumber", help="AI Data Finder (Gemini, Groq, Cerebras, OpenRouter, Mistral, GitHub Models, Claude)")
    f.add_argument("--komoditas", required=True)
    f.add_argument("--periode", required=True)
    f.add_argument("--kebutuhan", default="harga eceran harian")
    f.add_argument("--wilayah", default="Kabupaten Bengkulu Tengah, Provinsi Bengkulu")
    f.add_argument("--penyedia", choices=["otomatis", *pencari_data.PENYEDIA], default=None,
                   help="bawaan: ai.penyedia di config/pengaturan.json")

    w = sub.add_parser("sandi", help="buat entri akun (sandi berhash) untuk config/pengguna.json")
    w.add_argument("id")
    w.add_argument("sandi")
    w.add_argument("--nama", default=None)
    w.add_argument("--peran", choices=pengguna.PERAN, default="petugas")

    r = sub.add_parser("aturan-firebase", help="tulis firestore.rules dengan daftar admin pertama dari FIREBASE_ADMIN_AWAL")
    r.add_argument("--keluaran", type=Path, required=True)

    t = sub.add_parser("firestore-tarik", help="ambil kiriman dari situs (Firestore) ke berkas di repositori")
    t.add_argument("--url", default="", help="alamat proses GitHub Actions, untuk ditampilkan di situs")
    sub.add_parser("firestore-cek", help="periksa apakah ada kiriman atau perintah baru di Firestore")
    tb = sub.add_parser("firestore-terbit", help="tulis data dashboard ke Firestore supaya situs membacanya langsung")
    tb.add_argument("--folder", type=Path, default=Path("site/data"))
    tb.add_argument("--sembunyikan", action="store_true", help="hapus berkas data non-publik dari folder setelah tertulis")
    lp = sub.add_parser("firestore-lapor", help="catat hasil proses di Firestore")
    lp.add_argument("--hasil", required=True)
    lp.add_argument("--url", default="")
    lp.add_argument("--pesan", default="")

    a = p.parse_args(argv)
    if a.perintah.startswith("firestore-"):
        return _firestore(a)
    if a.perintah == "sandi":
        data = pengguna.muat((a.akar or konfigurasi.AKAR) / "config" / "pengguna.json") or {}
        garam = data.get("garam") or "lintas-ai-bengkulu-tengah"
        print(json.dumps(pengguna.entri_akun(garam, a.id, a.nama or a.id, a.peran, a.sandi), ensure_ascii=False, indent=2))
        return 0
    if a.perintah == "aturan-firebase":
        import os

        from . import firebase

        akar = a.akar or konfigurasi.AKAR
        try:
            emails = firebase.daftar_admin_awal(os.environ.get("FIREBASE_ADMIN_AWAL"))
            teks = firebase.aturan_dengan_admin((akar / "firestore.rules").read_text(encoding="utf-8"), emails)
        except ValueError as e:
            print(f"GAGAL: {e}", file=sys.stderr)
            return 2
        a.keluaran.parent.mkdir(parents=True, exist_ok=True)
        a.keluaran.write_text(teks, encoding="utf-8")
        print(f"Aturan Firestore ditulis ke {a.keluaran} dengan {len(emails)} admin pertama.")
        return 0
    try:
        konf = konfigurasi.muat(a.akar)
    except ValueError as e:  # pengaturan salah: tampilkan pesan yang jelas, bukan jejak kesalahan panjang
        print(f"GAGAL: {e}", file=sys.stderr)
        return 2

    if a.perintah in ("jalankan", "cari-sumber"):
        from . import firestore_sinkron

        firestore_sinkron.pasang_rahasia_dari_firestore(konf.akar)
    if a.perintah == "jalankan":
        from . import proses

        keluaran = a.keluaran if a.keluaran.is_absolute() else konf.akar / a.keluaran
        ringkas = proses.jalankan(konf, keluaran, a.demo, sinkron_github=not a.tanpa_github,
                                  kirim_notifikasi=not a.tanpa_notifikasi)
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
        catatan = pencari_data.cari(konf, a.komoditas, a.periode, a.kebutuhan, a.wilayah, penyedia=a.penyedia)
        path = pencari_data.simpan(konf, catatan)
        n = len(catatan["hasil"].get("kandidat", []))
        print(f"Penyedia: {catatan['penyedia']} ({catatan['model']}); dilewati: {catatan['penyedia_dilewati'] or '-'}")
        print(f"{n} kandidat sumber disimpan ke {path} (status: kandidat, wajib diverifikasi analis)")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())

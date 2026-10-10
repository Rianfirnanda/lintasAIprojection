"""Antarmuka baris perintah.

  python -m pipeline jalankan [--keluaran site/data] [--demo otomatis|ya|tidak] [--tanpa-github]
  python -m pipeline periksa                 # validasi berkas di data/masuk tanpa publikasi (untuk PR data)
  python -m pipeline ambil-cuaca [--hari 30] # konektor Big Data cuaca (Open-Meteo)
  python -m pipeline ambil-resmi             # konektor Big Data resmi: prakiraan BMKG dan harga PIHPS Bank Indonesia
  python -m pipeline berita [--tanpa-ai]      # berita lokal: cari, baca, ambil harga, ringkas (juga jalan otomatis tiap hari)
  python -m pipeline cari-sumber --komoditas "cabai rawit merah" --periode "Oktober 2026" [--penyedia gemini]
  python -m pipeline sandi ID SANDI [--nama "Nama"] [--peran petugas]   # cetak entri akun untuk config/pengguna.json
  python -m pipeline aturan-firebase --keluaran build/firestore.rules     # aturan Firestore + admin pertama (FIREBASE_ADMIN_AWAL)
  python -m pipeline firestore-tarik [--url URL]   # ambil kiriman dari situs (harga, keputusan, pengaturan, perintah)
  python -m pipeline firestore-cek                 # adakah yang perlu diproses? (untuk pemeriksa berkala)
  python -m pipeline firestore-jaga --menit 340 [--lanjutkan]   # penjaga antrean (antrean.yml)
  python -m pipeline firestore-lapor --hasil success|failure [--url URL]
  python -m pipeline firestore-terbit --folder site/data [--sembunyikan]   # data dashboard ke Firestore (lbp_data)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import berita, konfigurasi, kualitas, masukan, pencari_data, pengaturan, pengguna


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
    if a.perintah == "firestore-jaga":
        from . import penjaga

        n = penjaga.jaga(akar, a.menit)
        print(f"Penjaga selesai: {n} kali menjalankan pengolahan.")
        if a.lanjutkan:
            penjaga.jalankan_alur("antrean.yml")
            print("Penjaga berikutnya dijalankan.")
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
    if ringkas.get("kandidat_situs"):
        n = _kandidat_dari_situs(akar, ringkas["kandidat_situs"])
        print(f"{n} hasil AI Data Finder dari situs digabung ke kandidat sumber.")
    for pesan in _ai_harian(akar):
        print(pesan)
    # "Cari berita lokal sekarang" dari panel Pengaturan mengabaikan jadwal harian; tanpa permintaan, berita jalan sekali sehari.
    diminta_berita = any(x["jenis"] == "berita" for x in ringkas["perintah"])
    pesan_berita = _berita_harian(akar, paksa=diminta_berita)
    for pesan in pesan_berita:
        print(pesan)
    if diminta_berita:
        gagal = not pesan_berita or pesan_berita[0].startswith("::warning::")
        try:
            kolom = {"pesan": (pesan_berita[0] if pesan_berita else "Berita lokal tidak dijalankan (Firebase belum aktif).")[:500]}
            if gagal:
                kolom.update(status="gagal", hasil="failure")
            firestore_sinkron.catat_perintah("berita", a.url, **kolom)
        except Exception as e:  # noqa: BLE001
            print(f"::warning::Status berita tidak tercatat di situs: {e}")
    if ringkas.get("peringatan"):
        print(f"::warning::{ringkas['peringatan']}")
    keluaran = {"perintah": ",".join(x["jenis"] for x in ringkas["perintah"]) or "-"}
    # Jenis data yang dipilih admin saat menekan "Perbarui data dan dashboard sekarang" di panel Pengaturan.
    demo = next((str(x["masukan"].get("demo")) for x in ringkas["perintah"] if x["jenis"] == "perbarui"), "")
    if demo in ("otomatis", "ya", "tidak"):
        keluaran["demo"] = demo
    _keluaran_github(**keluaran)
    return 0


def _log_ai(sumber: str, komoditas: str, periode: str, catatan: dict | None = None, galat: Exception | None = None,
            oleh: str = "") -> None:
    """Catat proses AI Data Finder (berhasil atau gagal) ke Log proses AI di situs."""
    from . import firestore_sinkron

    if not firestore_sinkron.aktif():
        return
    langkah = (catatan or {}).get("log") or getattr(galat, "langkah", None) or []
    if galat is not None:
        langkah = [*langkah, {"waktu": "", "teks": f"Gagal: {galat}"[:400], "jenis": "galat"}]
    firestore_sinkron.tulis_log_ai({
        "sumber": sumber, "komoditas": komoditas[:120], "periode": periode[:60], "langkah": langkah[:80],
        "hasil": "gagal" if galat is not None else "berhasil",
        "penyedia": (catatan or {}).get("penyedia") or "", "model": (catatan or {}).get("model") or "",
        "jumlah_kandidat": len(((catatan or {}).get("hasil") or {}).get("kandidat", [])),
        "pencarian_web": (catatan or {}).get("pencarian_web") or "", "oleh_email": oleh, "oleh_uid": "",
    })


def _kandidat_dari_situs(akar: Path, daftar: list[dict]) -> int:
    """Hasil AI Data Finder dari browser admin: cek apakah alamatnya bisa dibuka, lalu gabung ke kandidat sumber."""
    konf = konfigurasi.muat(akar)
    n = 0
    for d in daftar:
        try:
            hasil = pencari_data.normalisasi_hasil(json.loads(d.get("hasil") or "{}"))
        except ValueError:
            continue
        url_cari = [str(u) for u in d.get("url_pencarian") or []]
        for k in hasil["kandidat"]:
            k["url_ada_di_hasil_pencarian"] = pencari_data._cocok(k["url"], url_cari) if d.get("punya_pencarian_web") else None
            pencari_data.terapkan_periksa(k, pencari_data.periksa_url(k["url"]))
            k["status_verifikasi"] = "kandidat"
        p = d.get("permintaan") or {}
        waktu = d.get("diperbarui")
        pencari_data.simpan(konf, {
            "waktu": waktu.isoformat() if hasattr(waktu, "isoformat") else str(waktu or ""),
            "permintaan": {k: str(p.get(k, ""))[:400] for k in ("komoditas", "periode", "kebutuhan", "wilayah", "prompt")},
            "penyedia": d.get("penyedia") or "", "punya_pencarian_web": bool(d.get("punya_pencarian_web")),
            "pencarian_web": d.get("pencarian_web") or None, "penyedia_dilewati": list(d.get("penyedia_dilewati") or [])[:20],
            "model": d.get("model") or "", "request_id": None, "hasil": hasil, "url_hasil_pencarian": sorted(set(url_cari)),
            "dari": "situs", "oleh": d.get("oleh_email") or "",
        })
        n += 1
    return n


BULAN_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
            "November", "Desember"]


def _berita_harian(akar: Path, paksa: bool = False) -> list[str]:
    """Berita lokal harian: sekali sehari mulai pukul 07.00 WIB. Hasil ditulis ke data/berita/berita.json (ikut dikirim ke
    repositori oleh alur kerja) dan prosesnya tercatat di Log proses AI. Gagal tidak menghentikan pembaruan dashboard.
    `paksa` (permintaan dari panel Pengaturan) menjalankannya sekarang walaupun hari ini sudah dicari."""
    from datetime import datetime, timezone

    from . import firestore_sinkron

    if not firestore_sinkron.aktif():
        return []
    try:
        db = firestore_sinkron.klien()
        sekarang = datetime.now(timezone.utc)
        if not paksa and not firestore_sinkron.berita_jatuh_tempo(akar, db, sekarang):
            return []
        konf = konfigurasi.muat(akar)
        hari = sekarang.astimezone(firestore_sinkron.WIB)
        # Catat dulu supaya penjaga tidak memicu ulang walaupun pencarian gagal; hasilnya ada di log.
        firestore_sinkron.catat_berita_harian(db, hari.date().isoformat())
        firestore_sinkron.pasang_rahasia_dari_firestore(akar)
    except Exception as e:  # noqa: BLE001
        return [f"::warning::Berita lokal harian tidak bisa dimulai: {e}"]
    periode = f"{BULAN_ID[hari.month - 1]} {hari.year}"
    try:
        hasil = berita.jalankan(konf)
        berita.simpan(konf, hasil)
        baru = hasil["statistik"]["berita_baru"]
        firestore_sinkron.catat_berita_harian(db, hari.date().isoformat(), baru, "berhasil")
        _log_ai("berita", "Berita lokal", periode, catatan={"log": hasil["log"], "penyedia": hasil["statistik"]["penyedia_ai"],
                                                          "model": hasil["statistik"]["model_ai"],
                                                          "hasil": {"kandidat": [b for b in hasil["berita"] if b.get("baru")]}})
        return [f"Berita lokal harian: {baru} berita baru, {hasil['statistik']['kandidat_harga_baru']} kandidat harga "
                f"({hasil['kesimpulan'][0]['metode']})."]
    except Exception as e:  # noqa: BLE001
        try:
            firestore_sinkron.catat_berita_harian(db, hari.date().isoformat(), 0, "gagal")
        except Exception:  # noqa: BLE001
            pass
        _log_ai("berita", "Berita lokal", periode, galat=e)
        return [f"::warning::Berita lokal harian gagal: {e}"]


def _ai_harian(akar: Path) -> list[str]:
    """AI Data Finder harian: beberapa komoditas bergilir, sekali sehari mulai pukul 08.00 WIB."""
    from datetime import datetime, timezone

    from . import firestore_sinkron

    if not firestore_sinkron.aktif():
        return []
    try:
        db = firestore_sinkron.klien()
        sekarang = datetime.now(timezone.utc)
        if not firestore_sinkron.ai_harian_jatuh_tempo(akar, db, sekarang):
            return []
        konf = konfigurasi.muat(akar)
        jumlah = int(konf.pengaturan.get("ai", {}).get("harian_jumlah", 2))
        daftar = list(dict.fromkeys(v.komoditas for v in sorted(konf.varian_aktif, key=lambda v: v.kode_komoditas)))
        status = firestore_sinkron.status_ai_harian(db)
        mulai = int(status.get("indeks", 0)) % max(1, len(daftar))
        pilih = [daftar[(mulai + i) % len(daftar)] for i in range(min(jumlah, len(daftar)))]
        hari = sekarang.astimezone(firestore_sinkron.WIB)
        periode = f"{BULAN_ID[hari.month - 1]} {hari.year}"
        # Catat dulu supaya penjaga tidak memicu ulang walaupun pencarian gagal; hasilnya ada di log.
        firestore_sinkron.catat_ai_harian(db, hari.date().isoformat(), (mulai + len(pilih)) % len(daftar), pilih)
        firestore_sinkron.pasang_rahasia_dari_firestore(akar)
    except Exception as e:  # noqa: BLE001
        return [f"::warning::AI Data Finder harian tidak bisa dimulai: {e}"]
    pesan = []
    for komoditas in pilih:
        try:
            catatan = pencari_data.cari(konf, komoditas, periode)
            pencari_data.simpan(konf, catatan)
            _log_ai("harian", komoditas, periode, catatan=catatan)
            pesan.append(f"AI harian {komoditas}: {len(catatan['hasil']['kandidat'])} kandidat ({catatan['penyedia']}).")
        except Exception as e:  # noqa: BLE001
            _log_ai("harian", komoditas, periode, galat=e)
            pesan.append(f"::warning::AI harian {komoditas} gagal: {e}")
    return pesan


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
        _log_ai("mesin", teks("komoditas"), teks("periode"), catatan=catatan, oleh=str(masukan.get("diminta_oleh", "")))
    except Exception as e:  # noqa: BLE001
        _log_ai("mesin", teks("komoditas"), teks("periode"), galat=e)
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

    r = sub.add_parser("ambil-resmi", help="ambil prakiraan cuaca BMKG dan harga PIHPS Bank Indonesia")
    r.add_argument("--riwayat-hari", type=int, default=None,
                   help="hanya PIHPS: ambil riwayat sejauh sekian hari ke belakang (mis. 1460 = 4 tahun), walau data sudah ada")

    sub.add_parser("probe-sumber", help="penjajakan sumber harga tingkat kabupaten/kota (jalankan di GitHub Actions)")
    pl = sub.add_parser("probe-lanjut", help="penjajakan lanjutan: SP2KP, Tableau, Bapanas, data terbuka daerah, BPS, PIHPS 5 tahun")
    pl.add_argument("--tahap", type=int, default=1)

    sub.add_parser("pihps-ke-harga", help="salin harga PIHPS Provinsi Bengkulu menjadi berkas harga utama sementara")

    f = sub.add_parser("cari-sumber", help="AI Data Finder (Gemini, Groq, Cerebras, OpenRouter, Mistral, Claude)")
    f.add_argument("--komoditas", required=True)
    f.add_argument("--periode", required=True)
    f.add_argument("--kebutuhan", default="harga eceran harian")
    f.add_argument("--wilayah", default="Kabupaten Bengkulu Tengah, Provinsi Bengkulu")
    f.add_argument("--penyedia", choices=["otomatis", *pencari_data.PENYEDIA], default=None,
                   help="bawaan: ai.penyedia di config/pengaturan.json")

    b = sub.add_parser("berita", help="berita lokal: cari, baca, ambil harga dari isinya, ringkas (hasil di data/berita/berita.json)")
    b.add_argument("--tanpa-ai", action="store_true", help="jangan pakai AI; ringkasan dan kesimpulan disusun otomatis")

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
    jg = sub.add_parser("firestore-jaga", help="periksa Firestore terus-menerus dan jalankan pengolahan bila ada kiriman")
    jg.add_argument("--menit", type=float, default=340)
    jg.add_argument("--lanjutkan", action="store_true", help="jalankan penjaga berikutnya saat waktu habis")
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

    if a.perintah in ("jalankan", "cari-sumber", "berita"):
        from . import firestore_sinkron

        firestore_sinkron.pasang_rahasia_dari_firestore(konf.akar)
    if a.perintah == "berita":
        hasil = berita.jalankan(konf, tanpa_ai=a.tanpa_ai)
        path = berita.simpan(konf, hasil)
        st = hasil["statistik"]
        for baris in hasil["log"]:
            print(f"[{baris['jenis']}] {baris['teks']}")
        print(f"{st['berita_baru']} berita baru, {st['total_arsip']} di arsip, {st['kandidat_harga_baru']} kandidat harga. Disimpan ke {path}")
        print("Kesimpulan:", hasil["kesimpulan"][0]["ringkas"])
        return 0
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
    if a.perintah == "ambil-resmi":
        from . import konektor_resmi

        if a.riwayat_hari:
            hasil = {"pihps": konektor_resmi.perbarui_pihps(konf, hari_riwayat=a.riwayat_hari, paksa_riwayat=True),
                     "pihps_kota": konektor_resmi.perbarui_pihps_kota(konf, hari_riwayat=a.riwayat_hari, paksa_riwayat=True)}
        else:
            hasil = konektor_resmi.perbarui(konf)
        print(json.dumps(hasil, ensure_ascii=False))
        return 0
    if a.perintah == "probe-sumber":
        from . import probe_sumber

        hasil = probe_sumber.jalankan(konf.akar)
        for k in ("pihps", "bapanas", "lain"):
            for r in hasil[k]:
                print(f"[{k}] {r['status']} {r['byte']}B wilayah={r['wilayah_disebut']} {r['url'][:110]}")
        return 0
    if a.perintah == "probe-lanjut":
        from . import probe_lanjut

        if a.tahap == 3:
            hasil = probe_lanjut.jalankan_tahap3(konf.akar)
            for r in hasil["sp2kp"]["coba"] + hasil["lain"]:
                print(f"[tahap3] {r['status']} {r['byte']}B {r['url'][:140]}")
            return 0
        if a.tahap == 2:
            hasil = probe_lanjut.jalankan_tahap2(konf.akar)
            for r in hasil["sp2kp"]["coba"] + hasil["daerah"]:
                print(f"[tahap2] {r['status']} {r['byte']}B {r['url'][:120]} {r.get('jumlah', '')}")
            return 0
        hasil = probe_lanjut.jalankan(konf.akar)
        sp = hasil["sp2kp"]
        print(f"[sp2kp] {sp['chunk']} potongan JS, {len(sp['api'])} alamat API, {len(sp['tableau'])} tampilan Tableau")
        for k in ("sp2kp_coba", "tableau", "ckan", "pihps", "lain"):
            for r in hasil[k]:
                print(f"[{k}] {r['status']} {r['byte']}B wilayah={r['wilayah_disebut']} {r['url'][:120]}")
        b = hasil["bapanas"]
        print(f"[bapanas] kunci={b['kunci_ditemukan']} tcp={b['tcp']}")
        for r in b["coba"]:
            print(f"[bapanas] {r['status']} {r['detik']}s {r.get('galat', '')} {r['url'][:120]}")
        print(f"[bps] {hasil['bps'].get('status')}")
        return 0
    if a.perintah == "pihps-ke-harga":
        from . import pihps_harga

        hasil = pihps_harga.ke_harga(konf)
        print(json.dumps(hasil, ensure_ascii=False))
        return 1 if hasil["galat"] else 0
    if a.perintah == "cari-sumber":
        from . import firestore_sinkron

        firestore_sinkron.pasang_rahasia_dari_firestore(konf.akar)  # kunci yang diisi lewat situs
        catatan = pencari_data.cari(konf, a.komoditas, a.periode, a.kebutuhan, a.wilayah, penyedia=a.penyedia)
        path = pencari_data.simpan(konf, catatan)
        n = len(catatan["hasil"].get("kandidat", []))
        print(f"Penyedia: {catatan['penyedia']} ({catatan['model']}); dilewati: {catatan['penyedia_dilewati'] or '-'}")
        print(f"{n} kandidat sumber disimpan ke {path} (status: kandidat, wajib diverifikasi analis)")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())

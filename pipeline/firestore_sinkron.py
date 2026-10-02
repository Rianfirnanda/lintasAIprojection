"""Jembatan Firestore: pekerjaan harian yang diisi lewat situs diambil mesin pengolah (GitHub Actions).

Yang diisi orang lewat situs (tanpa membuka GitHub):
  lbp_harga               harga dari petugas atau berkas unggahan operator  -> data/masuk/harga/situs/situs_YYYY-MM.csv
  lbp_validasi            keputusan cek data                                 -> data/validasi/situs.csv
  lbp_tindak_lanjut       tindak lanjut peringatan                           -> data/tindak_lanjut/situs.csv
  lbp_persetujuan_model   persetujuan model proyeksi                         -> data/persetujuan_model/situs.csv
  lbp_kunjungan           kunjungan pedagang yang gagal (menolak, dst.)      -> data/kunjungan/situs_YYYY-MM.csv
  lbp_kebijakan           kebijakan atau intervensi TPID                     -> data/kebijakan/situs.csv
  lbp_rapat               rapat TPID yang membahas data                      -> data/rapat/situs.csv
  lbp_keputusan_rekomendasi  persetujuan rekomendasi langkah               -> data/keputusan_rekomendasi/situs.csv
  lbp_pengguna            hanya dihitung ringkas (akun aktif, pemakaian)     -> data/adopsi.json
  lbp_pengaturan/utama    pengaturan sistem                                  -> config/pengaturan.json
  lbp_rahasia/{NAMA}      kunci API dan notifikasi (hanya dibaca mesin, langsung dipakai, tidak ditulis ke berkas)
  lbp_perintah/{jenis}    permintaan "jalankan sekarang" dari panel Pengaturan

Arah sebaliknya (terbit_data): hasil olahan untuk dashboard (site/data) ditulis ke koleksi lbp_data, satu dokumen per
berkas. Situs membacanya langsung dari Firestore dan langsung tahu bila ada data baru, dan berkas yang memuat harga tidak
perlu lagi diterbitkan terbuka di hosting.

Kiriman disalin ke berkas CSV di repositori supaya tetap ada jejak audit dan pipeline membaca data dengan cara yang
sama seperti sebelumnya. Batas yang sudah diambil disimpan di data/firestore_tanda.json, jadi setiap kali jalan hanya
kiriman baru yang dibaca (hemat kuota gratis Firestore).

Mesin masuk dengan akun layanan (GOOGLE_APPLICATION_CREDENTIALS), atau ke emulator bila FIRESTORE_EMULATOR_HOST diisi.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import pengaturan as modul_pengaturan

log = logging.getLogger(__name__)

BERKAS_TANDA = Path("data") / "firestore_tanda.json"

KOLOM_HARGA = ["tanggal", "kode_pasar", "kode_varian", "harga", "satuan", "kode_sumber", "petugas", "responden",
               "id_klien", "waktu_input", "catatan"]

# koleksi -> (folder relatif, kolom CSV, kolom kunci). Kunci "id" berarti ID dokumen Firestore.
KIRIMAN = {
    "lbp_harga": (Path("data/masuk/harga/situs"), KOLOM_HARGA, "id_klien"),
    "lbp_validasi": (Path("data/validasi"), ["id_observasi", "keputusan", "alasan", "validator", "tanggal_validasi"], "id_observasi"),
    "lbp_tindak_lanjut": (Path("data/tindak_lanjut"),
                          ["id", "id_sinyal", "status", "catatan", "petugas", "tanggal", "kode_varian", "tanggal_kejadian"], "id"),
    "lbp_persetujuan_model": (Path("data/persetujuan_model"),
                              ["id", "kode_varian", "model", "keputusan", "penyetuju", "tanggal", "catatan"], "id"),
    "lbp_kunjungan": (Path("data/kunjungan"),
                      ["id", "tanggal", "kode_pasar", "responden", "status", "alasan", "petugas", "waktu_input"], "id"),
    "lbp_kebijakan": (Path("data/kebijakan"),
                      ["id", "tanggal_mulai", "tanggal_selesai", "jenis", "kode_varian", "tujuan", "uraian", "id_rekomendasi",
                       "pencatat"], "id"),
    "lbp_rapat": (Path("data/rapat"),
                  ["id", "tanggal", "jenis", "agenda", "keputusan", "jumlah_sinyal", "peserta", "tautan_notulen", "pencatat"], "id"),
    "lbp_keputusan_rekomendasi": (Path("data/keputusan_rekomendasi"),
                                  ["id_rekomendasi", "keputusan", "catatan", "penyetuju", "tanggal"], "id_rekomendasi"),
}
# Koleksi yang langsung memicu pembaruan (keputusan dan catatan); harga dan kunjungan dikumpulkan dulu (lihat perlu_jalan).
KIRIMAN_SEGERA = ("lbp_validasi", "lbp_tindak_lanjut", "lbp_persetujuan_model", "lbp_kebijakan", "lbp_rapat",
                  "lbp_keputusan_rekomendasi")

JENIS_PERINTAH = ("perbarui", "cari_sumber")


# ---------------------------------------------------------------- sambungan

def klien():
    """Klien Firestore dari akun layanan atau emulator. Pustakanya hanya dipasang saat Firebase dipakai."""
    from google.cloud import firestore  # noqa: PLC0415

    proyek = os.environ.get("FIREBASE_PROYEK") or os.environ.get("GCLOUD_PROJECT")
    if not proyek and os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            proyek = json.loads(Path(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]).read_text(encoding="utf-8"))["project_id"]
        except (OSError, ValueError, KeyError):
            proyek = None
    return firestore.Client(project=proyek)


def aktif() -> bool:
    """Firestore dipakai bila mesin punya kredensial (atau emulator) dan tidak dimatikan."""
    if os.environ.get("LBP_FIRESTORE", "1") in ("0", "tidak"):
        return False
    return bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get("FIRESTORE_EMULATOR_HOST"))


# ---------------------------------------------------------------- tanda batas

def baca_tanda(akar: Path) -> dict:
    path = akar / BERKAS_TANDA
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def tulis_tanda(akar: Path, tanda: dict) -> None:
    path = akar / BERKAS_TANDA
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tanda, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _waktu(x) -> datetime | None:
    if x is None:
        return None
    if isinstance(x, datetime):
        return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(x))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _iso(d: datetime) -> str:
    return d.astimezone(timezone.utc).isoformat(timespec="microseconds")


# ---------------------------------------------------------------- CSV

def _teks(nilai) -> str:
    if nilai is None:
        return ""
    if isinstance(nilai, bool):
        return "ya" if nilai else "tidak"
    if isinstance(nilai, float):
        return str(int(nilai)) if nilai.is_integer() else repr(nilai)
    if isinstance(nilai, (list, tuple)):
        return ";".join(_teks(x) for x in nilai)
    return str(nilai).replace("\r\n", " ").replace("\n", " ").replace("\r", " ").strip()


def baris_csv(koleksi: str, id_dok: str, data: dict) -> dict[str, str]:
    """Satu dokumen Firestore menjadi satu baris CSV dengan kolom templat yang sudah dipakai pipeline."""
    _, kolom, _ = KIRIMAN[koleksi]
    baris = {k: _teks(data.get(k)) for k in kolom}
    if "id" in kolom:
        baris["id"] = id_dok
    if koleksi == "lbp_harga":
        baris["id_klien"] = baris["id_klien"] or id_dok
        baris["kode_pasar"] = baris["kode_pasar"].upper()
        baris["kode_varian"] = baris["kode_varian"].upper()
    if koleksi == "lbp_validasi":
        baris["id_observasi"] = baris["id_observasi"] or id_dok
    if koleksi == "lbp_keputusan_rekomendasi":
        baris["id_rekomendasi"] = baris["id_rekomendasi"] or id_dok
    if koleksi == "lbp_kebijakan":
        baris["kode_varian"] = baris["kode_varian"].upper()
    return baris


def berkas_tujuan(koleksi: str, baris: dict) -> Path:
    folder, _, _ = KIRIMAN[koleksi]
    if koleksi in ("lbp_harga", "lbp_kunjungan"):
        bulan = baris["tanggal"][:7] if len(baris["tanggal"]) >= 7 else "tanpa-tanggal"
        return folder / f"situs_{bulan}.csv"
    return folder / "situs.csv"


def gabung_csv(path: Path, kolom: list[str], kunci: str, baru: list[dict]) -> int:
    """Tambahkan atau perbarui baris (berdasarkan `kunci`) di berkas CSV. Mengembalikan jumlah baris yang berubah."""
    lama: dict[str, dict] = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8-sig") as f:
            for b in csv.DictReader(f):
                lama[b.get(kunci, "")] = {k: b.get(k, "") or "" for k in kolom}
    berubah = 0
    for b in baru:
        if lama.get(b[kunci]) != b:
            berubah += 1
        lama[b[kunci]] = b  # dict menjaga urutan: baris lama tetap di tempatnya, yang baru di akhir
    if not berubah:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=kolom, lineterminator="\n")
    w.writeheader()
    w.writerows(lama.values())
    path.write_text(buf.getvalue(), encoding="utf-8")
    return berubah


def simpan_kiriman(akar: Path, koleksi: str, dokumen: list[tuple[str, dict]]) -> dict[str, int]:
    """Tulis dokumen ke berkas CSV. Mengembalikan {berkas relatif: jumlah baris berubah}."""
    _, kolom, kunci = KIRIMAN[koleksi]
    per_berkas: dict[Path, list[dict]] = {}
    for id_dok, data in dokumen:
        b = baris_csv(koleksi, id_dok, data)
        per_berkas.setdefault(berkas_tujuan(koleksi, b), []).append(b)
    hasil = {}
    for rel, daftar in sorted(per_berkas.items()):
        n = gabung_csv(akar / rel, kolom, kunci, daftar)
        if n:
            hasil[rel.as_posix()] = n
    return hasil


# ---------------------------------------------------------------- pengaturan

def _rapikan(nilai, tingkat: int = 0) -> str:
    """Sama dengan rapikan() di site/assets/pengaturan-inti.js, supaya berkas dari situs dan dari panel sama persis."""
    tab = "  "
    skalar = lambda x: not isinstance(x, (dict, list))  # noqa: E731
    if isinstance(nilai, list):
        if all(skalar(x) for x in nilai):
            return "[" + ", ".join(_json(x) for x in nilai) + "]"
        isi = ",\n".join(tab * (tingkat + 1) + _rapikan(x, tingkat + 1) for x in nilai)
        return f"[\n{isi}\n{tab * tingkat}]"
    if isinstance(nilai, dict):
        if not nilai:
            return "{}"
        tanpa_bersarang = all(skalar(v) or (isinstance(v, list) and all(skalar(x) for x in v)) for v in nilai.values())
        if tingkat > 0 and tanpa_bersarang:
            satu = "{" + ", ".join(f"{_json(k)}: {_rapikan(v, tingkat + 1)}" for k, v in nilai.items()) + "}"
            if len(satu) <= 80:
                return satu
        isi = ",\n".join(f"{tab * (tingkat + 1)}{_json(k)}: {_rapikan(v, tingkat + 1)}" for k, v in nilai.items())
        return f"{{\n{isi}\n{tab * tingkat}}}"
    return _json(nilai)


def _json(x) -> str:
    if isinstance(x, float) and math.isfinite(x) and x.is_integer():
        x = int(x)
    return json.dumps(x, ensure_ascii=False)


def tulis_pengaturan(data: dict) -> str:
    return _rapikan(data) + "\n"


def _urut_seperti(acuan: dict, data: dict) -> dict:
    """Firestore tidak menjaga urutan kunci. Susun ulang mengikuti berkas lama supaya perbedaan di git tetap kecil."""
    if not isinstance(acuan, dict) or not isinstance(data, dict):
        return data
    urut = [k for k in acuan if k in data] + [k for k in data if k not in acuan]
    return {k: _urut_seperti(acuan.get(k), data[k]) if isinstance(data[k], dict) else data[k] for k in urut}


def _lengkapi(acuan, data):
    """Isian yang belum ada di simpanan situs (misalnya isian baru setelah pembaruan sistem) diambil dari berkas sekarang."""
    if not isinstance(acuan, dict) or not isinstance(data, dict):
        return data
    return {**acuan, **{k: _lengkapi(acuan.get(k), v) for k, v in data.items()}}


def terapkan_pengaturan(akar: Path, dok: dict | None, versi_terapan: int) -> tuple[int, str]:
    """Tulis pengaturan dari situs ke config/pengaturan.json bila versinya lebih baru dan isinya sah.

    Mengembalikan (versi yang kini tercatat, pesan). Versi yang ditolak tetap dicatat supaya tidak diulang terus;
    admin cukup menyimpan lagi dengan isian yang benar.
    """
    if not dok or not isinstance(dok.get("versi"), int) or dok["versi"] <= versi_terapan:
        return versi_terapan, ""
    versi = dok["versi"]
    isi = dok.get("isi")
    folder = akar / "config"
    path = folder / "pengaturan.json"
    lama = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(isi, dict):
        return versi, f"Pengaturan versi {versi} dari situs kosong, tidak dipakai."
    isi = _urut_seperti(lama, _lengkapi(lama, isi))
    masalah = modul_pengaturan.periksa(isi, modul_pengaturan.muat_skema(folder) or {"kolom": []})
    if masalah:
        return versi, f"Pengaturan versi {versi} dari situs tidak dipakai karena belum sah: {masalah[0][1]}"
    teks = tulis_pengaturan(isi)
    if path.read_text(encoding="utf-8") != teks:
        path.write_text(teks, encoding="utf-8")
        return versi, f"Pengaturan versi {versi} dari situs dipakai (diubah oleh {dok.get('diubah_oleh', '?')})."
    return versi, ""


# ---------------------------------------------------------------- rahasia

def nama_rahasia(akar: Path) -> list[str]:
    """Kunci yang boleh diisi lewat situs: semua kunci di skema selain kunci Firebase."""
    skema = modul_pengaturan.muat_skema(akar / "config") or {}
    return [r["nama"] for r in skema.get("rahasia", []) if not r["nama"].startswith("FIREBASE_")]


def terapkan_rahasia(nilai: dict[str, str], env: dict | None = None) -> list[str]:
    """Pasang kunci dari situs ke lingkungan proses. Kunci dari situs menggantikan GitHub Secret yang sama."""
    env = os.environ if env is None else env
    terpasang = []
    for nama, v in sorted(nilai.items()):
        if isinstance(v, str) and v.strip():
            env[nama] = v.strip()
            terpasang.append(nama)
    return terpasang


def muat_rahasia(db, akar: Path) -> dict[str, str]:
    boleh = set(nama_rahasia(akar))
    hasil = {}
    for d in db.collection("lbp_rahasia").stream():
        if d.id in boleh:
            hasil[d.id] = (d.to_dict() or {}).get("nilai", "")
    return hasil


def pasang_rahasia_dari_firestore(akar: Path) -> list[str]:
    """Dipanggil sebelum pipeline/AI jalan. Gagal membaca bukan alasan berhenti: GitHub Secrets tetap dipakai."""
    if not aktif():
        return []
    try:
        terpasang = terapkan_rahasia(muat_rahasia(klien(), akar))
    except Exception as e:  # noqa: BLE001
        log.warning("kunci dari situs tidak bisa dibaca, memakai GitHub Secrets: %s", e)
        return []
    if terpasang:
        log.info("kunci dari situs dipakai: %s", ", ".join(terpasang))
    return terpasang


# ---------------------------------------------------------------- ambil, cek, lapor

def _baru_sejak(db, koleksi: str, sejak: datetime | None, batas: int | None = None):
    q = db.collection(koleksi)
    if sejak is not None:
        q = q.where("diperbarui", ">", sejak)
    q = q.order_by("diperbarui")
    if batas:
        q = q.limit(batas)
    return [(d.id, d.to_dict() or {}) for d in q.stream()]


def _status(db) -> dict:
    d = db.collection("lbp_status").document("pipeline").get()
    return (d.to_dict() or {}) if d.exists else {}


def tarik(akar: Path, url_proses: str = "", db=None) -> dict:
    """Ambil semua kiriman baru dari situs, tulis ke berkas, terapkan pengaturan, dan ambil perintah yang menunggu."""
    db = db or klien()
    tanda = baca_tanda(akar)
    sekarang = datetime.now(timezone.utc)
    ringkas: dict = {"berkas": {}, "pesan": [], "perintah": []}

    db.collection("lbp_status").document("pipeline").set(
        {"status": "berjalan", "mulai": sekarang, "url": url_proses}, merge=True)

    for koleksi in KIRIMAN:
        dokumen = _baru_sejak(db, koleksi, _waktu(tanda.get(koleksi)))
        if not dokumen:
            continue
        ringkas["berkas"].update(simpan_kiriman(akar, koleksi, dokumen))
        terakhir = max((_waktu(d.get("diperbarui")) for _, d in dokumen if d.get("diperbarui")), default=None)
        if terakhir:
            tanda[koleksi] = _iso(terakhir)
        ringkas["pesan"].append(f"{len(dokumen)} kiriman baru dari {koleksi}")

    dok = db.collection("lbp_pengaturan").document("utama").get()
    versi, pesan = terapkan_pengaturan(akar, dok.to_dict() if dok.exists else None, int(tanda.get("pengaturan_versi", 0)))
    tanda["pengaturan_versi"] = versi
    if pesan:
        ringkas["pesan"].append(pesan)
        if "tidak dipakai" in pesan:
            ringkas["peringatan"] = pesan

    for jenis in JENIS_PERINTAH:
        ref = db.collection("lbp_perintah").document(jenis)
        snap = ref.get()
        data = snap.to_dict() if snap.exists else None
        if data and data.get("status") == "menunggu":
            ref.update({"status": "berjalan", "mulai": sekarang, "url": url_proses})
            ringkas["perintah"].append({"jenis": jenis, "masukan": data.get("masukan") or {},
                                        "diminta_oleh": data.get("diminta_oleh", "")})

    try:
        akun = [(d.id, d.to_dict() or {}) for d in db.collection("lbp_pengguna").stream()]
        if akun and tulis_adopsi(akar, ringkas_adopsi(akun, sekarang)):
            ringkas["berkas"]["data/adopsi.json"] = 1
    except Exception as e:  # noqa: BLE001  pemakaian hanya pelengkap indikator; jangan gagalkan pengambilan kiriman
        log.warning("ringkasan pemakaian akun tidak bisa dibuat: %s", e)

    tulis_tanda(akar, tanda)
    return ringkas


def ringkas_adopsi(akun: list[tuple[str, dict]], sekarang: datetime, hari: int = 30) -> dict:
    """Angka ringkas pemakaian sistem (Tabel 23 Rancangan): tanpa nama, email, atau ID akun."""
    aktif = [d for _, d in akun if d.get("status") == "aktif"]
    batas = sekarang - timedelta(days=hari)
    pakai = [d for d in aktif if (_waktu(d.get("terakhir_aktif")) or datetime.min.replace(tzinfo=timezone.utc)) >= batas]
    per_peran: dict[str, dict] = {}
    for d in aktif:
        p = per_peran.setdefault(d.get("peran") or "-", {"akun": 0, "aktif_30_hari": 0})
        p["akun"] += 1
        p["aktif_30_hari"] += d in pakai
    mulai = min((_waktu(d.get("dibuat")) for d in aktif if _waktu(d.get("dibuat"))), default=None)
    return {"akun_aktif": len(aktif), "aktif_30_hari": len(pakai), "per_peran": dict(sorted(per_peran.items())),
            "mulai": mulai.date().isoformat() if mulai else None, "periode_hari": hari}


def tulis_adopsi(akar: Path, data: dict) -> bool:
    """Tulis data/adopsi.json bila isinya berubah. Mengembalikan True bila berkas ditulis."""
    path = akar / "data" / "adopsi.json"
    teks = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == teks:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(teks, encoding="utf-8")
    return True


def perlu_jalan(akar: Path, db=None, sekarang: datetime | None = None, jeda_harga_menit: int = 0) -> tuple[bool, str]:
    """Untuk pemeriksa berkala: apakah ada yang perlu diproses sekarang?

    Semua kiriman baru langsung diproses supaya dashboard secepat mungkin mengikuti. `jeda_harga_menit` (bawaan 0)
    bisa dipakai untuk menahan harga baru sampai sekian menit setelah proses terakhir selesai.
    """
    db = db or klien()
    sekarang = sekarang or datetime.now(timezone.utc)
    tanda = baca_tanda(akar)
    status = _status(db)
    mulai = _waktu(status.get("mulai"))
    if status.get("status") == "berjalan" and mulai and sekarang - mulai < timedelta(minutes=30):
        return False, "proses lain sedang berjalan"
    for jenis in JENIS_PERINTAH:
        snap = db.collection("lbp_perintah").document(jenis).get()
        if snap.exists and (snap.to_dict() or {}).get("status") == "menunggu":
            return True, f"ada permintaan {jenis}"
    dok = db.collection("lbp_pengaturan").document("utama").get()
    if dok.exists and int((dok.to_dict() or {}).get("versi", 0)) > int(tanda.get("pengaturan_versi", 0)):
        return True, "ada pengaturan baru"
    for koleksi in KIRIMAN_SEGERA:
        if _baru_sejak(db, koleksi, _waktu(tanda.get(koleksi)), batas=1):
            return True, f"ada kiriman baru di {koleksi}"
    if any(_baru_sejak(db, k, _waktu(tanda.get(k)), batas=1) for k in ("lbp_harga", "lbp_kunjungan")):
        selesai = _waktu(status.get("selesai"))
        if selesai and sekarang - selesai < timedelta(minutes=jeda_harga_menit):
            return False, f"ada harga baru, diproses setelah jeda {jeda_harga_menit} menit"
        return True, "ada harga baru"
    return False, "tidak ada yang baru"


def lapor(hasil: str, url_proses: str = "", pesan: str = "", db=None) -> None:
    """Catat hasil proses di lbp_status/pipeline dan tutup perintah yang diambil proses ini."""
    db = db or klien()
    sekarang = datetime.now(timezone.utc)
    berhasil = hasil == "success"
    db.collection("lbp_status").document("pipeline").set(
        {"status": "selesai", "hasil": hasil, "selesai": sekarang, "url": url_proses, "pesan": pesan[:500]}, merge=True)
    for jenis in JENIS_PERINTAH:
        ref = db.collection("lbp_perintah").document(jenis)
        snap = ref.get()
        data = snap.to_dict() if snap.exists else None
        # Hanya perintah yang diambil proses ini; permintaan baru yang masuk sementara itu tetap menunggu.
        if data and data.get("status") == "berjalan" and data.get("url", "") == url_proses:
            ref.update({"status": "selesai" if berhasil else "gagal", "hasil": hasil, "selesai": sekarang})


def catat_perintah(jenis: str, url_proses: str, db=None, **kolom) -> None:
    """Tambahkan keterangan (mis. pesan galat) pada perintah yang sedang dikerjakan proses ini."""
    db = db or klien()
    ref = db.collection("lbp_perintah").document(jenis)
    snap = ref.get()
    if snap.exists and (snap.to_dict() or {}).get("url", "") == url_proses:
        ref.update(kolom)


# ---------------------------------------------------------------- data dashboard -> Firestore

KOLEKSI_DATA = "lbp_data"
DOK_DAFTAR = "_daftar"
# Berkas yang tetap boleh terbuka di hosting: dibutuhkan sebelum login atau tidak memuat harga.
BERKAS_PUBLIK = {"meta.json", "firebase.json", "pengguna.json", "pengaturan.json", "skema_pengaturan.json", "master.json"}
UKURAN_BAGIAN = 300_000  # karakter; paling banyak 3 bait per karakter, jadi tetap di bawah batas 1 MiB per dokumen


def id_data(rel: str) -> str:
    """seri/CMR01.json -> seri~CMR01.json (ID dokumen Firestore tidak boleh memuat garis miring)."""
    return rel.replace("/", "~")


def berkas_data(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*")
                  if p.is_file() and p.suffix in (".json", ".csv") and not p.name.startswith("."))


def terbit_data(folder: Path, db=None, hapus_berkas: bool = False) -> dict:
    """Tulis hasil olahan dashboard ke lbp_data. Hanya berkas yang isinya berubah yang ditulis (hemat kuota).

    Dokumen meta.json selalu ditulis paling akhir: situs memantau dokumen itu untuk tahu ada data baru.
    Bila `hapus_berkas`, berkas yang bukan publik dihapus dari folder setelah semuanya tertulis, supaya tidak ikut
    diterbitkan terbuka di hosting.
    """
    db = db or klien()
    kol = db.collection(KOLEKSI_DATA)
    lama = ((kol.document(DOK_DAFTAR).get().to_dict() or {}).get("berkas") or {})
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    versi = str(meta.get("dibuat", ""))
    sekarang = datetime.now(timezone.utc)
    daftar, ditulis = {}, []
    semua = berkas_data(folder)
    for rel in [r for r in semua if r != "meta.json"] + (["meta.json"] if "meta.json" in semua else []):
        teks = (folder / rel).read_text(encoding="utf-8")
        kunci = hashlib.sha256(teks.encode("utf-8")).hexdigest()
        bagian = [teks[i:i + UKURAN_BAGIAN] for i in range(0, len(teks), UKURAN_BAGIAN)] or [""]
        id_ = id_data(rel)
        daftar[id_] = {"nama": rel, "hash": kunci, "bagian": len(bagian)}
        sebelum = lama.get(id_) or {}
        if sebelum.get("hash") == kunci and rel != "meta.json":
            continue
        for i, isi in enumerate(bagian[1:], start=2):
            kol.document(f"{id_}@{i}").set({"isi": isi})
        for i in range(len(bagian) + 1, int(sebelum.get("bagian", 1)) + 1):
            kol.document(f"{id_}@{i}").delete()
        kol.document(id_).set({"nama": rel, "isi": bagian[0], "bagian": len(bagian), "hash": kunci, "versi": versi,
                               "diperbarui": sekarang})
        ditulis.append(rel)
    dihapus = []
    for id_, info in lama.items():
        if id_ in daftar:
            continue
        for i in range(2, int(info.get("bagian", 1)) + 1):
            kol.document(f"{id_}@{i}").delete()
        kol.document(id_).delete()
        dihapus.append(info.get("nama", id_))
    kol.document(DOK_DAFTAR).set({"berkas": daftar, "versi": versi, "diperbarui": sekarang})
    disembunyikan = []
    if hapus_berkas:
        for rel in semua:
            if rel not in BERKAS_PUBLIK:
                (folder / rel).unlink()
                disembunyikan.append(rel)
    return {"ditulis": ditulis, "dihapus": dihapus, "tetap": len(daftar) - len(ditulis), "disembunyikan": disembunyikan}

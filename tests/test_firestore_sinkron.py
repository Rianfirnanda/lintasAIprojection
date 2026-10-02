"""Jembatan Firestore: kiriman dari situs menjadi berkas yang dibaca pipeline seperti biasa."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from pipeline import firestore_sinkron as fs
from pipeline import kinerja, konfigurasi, kualitas, masukan, tindak_lanjut

from .conftest import HARI_INI

T0 = datetime(2026, 9, 28, 1, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------- Firestore tiruan (cukup untuk modul ini)

class _Snap:
    def __init__(self, id_, data):
        self.id, self._data = id_, data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return None if self._data is None else dict(self._data)


class _Ref:
    def __init__(self, simpan, id_):
        self._s, self.id = simpan, id_

    def get(self):
        return _Snap(self.id, self._s.get(self.id))

    def set(self, data, merge=False):
        self._s[self.id] = {**(self._s.get(self.id) or {}), **data} if merge else dict(data)

    def update(self, data):
        assert self.id in self._s, "update pada dokumen yang tidak ada"
        self._s[self.id].update(data)

    def delete(self):
        self._s.pop(self.id, None)


class _Kueri:
    def __init__(self, simpan, saring=(), urut=None, batas=None):
        self._s, self._saring, self._urut, self._batas = simpan, saring, urut, batas

    def where(self, kolom, op, nilai):
        assert op == ">"
        return _Kueri(self._s, (*self._saring, (kolom, nilai)), self._urut, self._batas)

    def order_by(self, kolom):
        return _Kueri(self._s, self._saring, kolom, self._batas)

    def limit(self, n):
        return _Kueri(self._s, self._saring, self._urut, n)

    def stream(self):
        hasil = [(k, v) for k, v in self._s.items() if all(k2 in v and v[k2] > n for k2, n in self._saring)]
        if self._urut:
            hasil.sort(key=lambda kv: kv[1][self._urut])
        return [_Snap(k, v) for k, v in hasil[: self._batas or None]]


class _Koleksi(_Kueri):
    def document(self, id_):
        return _Ref(self._s, id_)

    def add(self, data):
        id_ = f"auto{len(self._s) + 1}"
        self._s[id_] = dict(data)
        return None, _Ref(self._s, id_)


class DBTiruan:
    def __init__(self):
        self.data: dict[str, dict] = {}

    def collection(self, nama):
        return _Koleksi(self.data.setdefault(nama, {}))


def _harga(id_, waktu, **lain):
    return {"tanggal": "2026-09-28", "kode_pasar": "psr01", "kode_varian": "cmr01", "harga": 55000.0, "satuan": "kg",
            "kode_sumber": "PSR-ENUM", "petugas": "PTG01", "responden": "R1", "id_klien": id_,
            "waktu_input": "2026-09-28T08:00:00+07:00", "catatan": "baris\nkedua", "oleh_uid": "u1",
            "oleh_email": "petugas@contoh.go.id", "diterima": waktu, "diperbarui": waktu, **lain}


@pytest.fixture
def akar(akar_sementara):
    for sub in ("persetujuan_model",):
        (akar_sementara / "data" / sub).mkdir(parents=True, exist_ok=True)
    return akar_sementara


# ---------------------------------------------------------------- uji

def test_harga_dari_situs_terbaca_pipeline_dan_tanpa_email(akar):
    db = DBTiruan()
    db.data["lbp_harga"] = {"k1": _harga("k1", T0), "k2": _harga("k2", T0 + timedelta(seconds=5), harga=60000)}
    ringkas = fs.tarik(akar, "https://github.com/x/y/actions/runs/1", db=db)
    berkas = akar / "data/masuk/harga/situs/situs_2026-09.csv"
    assert ringkas["berkas"] == {"data/masuk/harga/situs/situs_2026-09.csv": 2}
    teks = berkas.read_text(encoding="utf-8")
    assert "petugas@contoh.go.id" not in teks and "oleh_uid" not in teks
    assert ",55000," in teks and "baris kedua" in teks

    konf = konfigurasi.muat(akar, hari_ini=HARI_INI)
    hasil = masukan.baca_semua(akar / "data" / "masuk", konf, akar_relatif=akar)
    assert hasil.penolakan == []
    assert sorted(o.harga for o in hasil.observasi) == [55000, 60000]
    assert {o.id_klien for o in hasil.observasi} == {"k1", "k2"}
    assert fs.baca_tanda(akar)["lbp_harga"].startswith("2026-09-28T01:00:05")


def test_hanya_kiriman_baru_yang_dibaca_dan_tidak_ganda(akar):
    db = DBTiruan()
    db.data["lbp_harga"] = {"k1": _harga("k1", T0)}
    fs.tarik(akar, db=db)
    db.data["lbp_harga"]["k2"] = _harga("k2", T0 + timedelta(minutes=1), tanggal="2026-10-01")
    ringkas = fs.tarik(akar, db=db)
    assert ringkas["berkas"] == {"data/masuk/harga/situs/situs_2026-10.csv": 1}
    assert fs.tarik(akar, db=db)["berkas"] == {}
    sep = (akar / "data/masuk/harga/situs/situs_2026-09.csv").read_text(encoding="utf-8").splitlines()
    assert len(sep) == 2  # header + k1, tidak ditulis ulang


def test_keputusan_tindak_lanjut_dan_persetujuan_dari_situs(akar):
    db = DBTiruan()
    db.data["lbp_validasi"] = {
        "OBS1": {"id_observasi": "OBS1", "keputusan": "terima", "alasan": "dicek", "validator": "Op",
                 "tanggal_validasi": "2026-09-28", "diperbarui": T0}}
    db.data["lbp_tindak_lanjut"] = {
        "a": {"id_sinyal": "SIG-1", "status": "terverifikasi", "catatan": "cek", "petugas": "TPID", "tanggal": "2026-09-28T09:00",
              "kode_varian": "", "tanggal_kejadian": "", "diperbarui": T0}}
    db.data["lbp_persetujuan_model"] = {
        "b": {"kode_varian": "CMR01", "model": "ets", "keputusan": "setuju", "penyetuju": "Analis", "tanggal": "2026-09-28",
              "catatan": "", "diperbarui": T0}}
    fs.tarik(akar, db=db)
    assert kualitas.baca_keputusan(akar / "data" / "validasi")["OBS1"].keputusan == "terima"
    assert tindak_lanjut.baca_buku(akar / "data" / "tindak_lanjut")[0]["SIG-1"].status == "terverifikasi"
    assert kinerja.baca_persetujuan(akar / "data" / "persetujuan_model")["CMR01"]["model"] == "ets"

    # Keputusan yang diubah (dokumen sama) menggantikan baris lama, bukan menambah.
    db.data["lbp_validasi"]["OBS1"].update(keputusan="tolak", diperbarui=T0 + timedelta(hours=1))
    fs.tarik(akar, db=db)
    assert kualitas.baca_keputusan(akar / "data" / "validasi")["OBS1"].keputusan == "tolak"
    assert len((akar / "data/validasi/situs.csv").read_text(encoding="utf-8").splitlines()) == 2


def test_pengaturan_dari_situs_dipakai_bila_sah_dan_lebih_baru(akar):
    path = akar / "config/pengaturan.json"
    asli = json.loads(path.read_text(encoding="utf-8"))
    db = DBTiruan()
    isi = json.loads(json.dumps(asli))
    isi["ai"]["penyedia"] = "groq"
    # Firestore tidak menjaga urutan kunci; berkas tetap disusun seperti semula.
    db.data["lbp_pengaturan"] = {"utama": {"isi": dict(reversed(list(isi.items()))), "versi": 3, "diubah_oleh": "adm@contoh.go.id"}}
    ringkas = fs.tarik(akar, db=db)
    baru = json.loads(path.read_text(encoding="utf-8"))
    assert baru["ai"]["penyedia"] == "groq"
    assert list(baru) == list(asli)
    assert fs.baca_tanda(akar)["pengaturan_versi"] == 3
    assert any("versi 3" in p for p in ringkas["pesan"])

    # Versi lama tidak diterapkan lagi; isian tidak sah ditolak tapi tetap dicatat supaya tidak diulang terus.
    path.write_text(fs.tulis_pengaturan(asli), encoding="utf-8")
    fs.tarik(akar, db=db)
    assert json.loads(path.read_text(encoding="utf-8"))["ai"]["penyedia"] == asli["ai"]["penyedia"]
    isi["ai"]["penyedia"] = "tidak-dikenal"
    db.data["lbp_pengaturan"]["utama"] = {"isi": isi, "versi": 4}
    ringkas = fs.tarik(akar, db=db)
    assert "tidak dipakai" in ringkas["peringatan"]
    assert json.loads(path.read_text(encoding="utf-8")) == asli
    assert fs.baca_tanda(akar)["pengaturan_versi"] == 4


def test_pengaturan_lama_dari_situs_dilengkapi_isian_baru(akar):
    """Simpanan situs dari sebelum ada isian baru (misalnya model Groq) tetap sah; isian barunya diambil dari berkas."""
    path = akar / "config/pengaturan.json"
    asli = json.loads(path.read_text(encoding="utf-8"))
    isi = json.loads(json.dumps(asli))
    for k in ("model_groq", "model_cerebras", "model_openrouter", "model_mistral"):
        del isi["ai"][k]
    isi["ai"]["urutan_otomatis"] = ["groq", "github_models"]
    isi["ai"]["model_github"] = "openai/gpt-4.1-mini"
    db = DBTiruan()
    db.data["lbp_pengaturan"] = {"utama": {"isi": isi, "versi": 7, "diubah_oleh": "adm@contoh.go.id"}}
    ringkas = fs.tarik(akar, db=db)
    assert not ringkas.get("peringatan")
    baru = json.loads(path.read_text(encoding="utf-8"))
    assert baru["ai"]["urutan_otomatis"] == ["groq"] and "model_github" not in baru["ai"]  # GitHub Models sudah ditutup
    assert baru["ai"]["model_groq"] == asli["ai"]["model_groq"] and list(baru["ai"]) == list(asli["ai"])


def test_kunci_dari_situs_menggantikan_secret_dan_kunci_asing_diabaikan(akar):
    db = DBTiruan()
    db.data["lbp_rahasia"] = {"GEMINI_API_KEY": {"nilai": " kunci-situs "}, "FIREBASE_SERVICE_ACCOUNT": {"nilai": "x"},
                              "PATH": {"nilai": "/jahat"}, "SMTP_HOST": {"nilai": ""}}
    env = {"GEMINI_API_KEY": "kunci-lama", "SMTP_HOST": "smtp.lama"}
    assert fs.terapkan_rahasia(fs.muat_rahasia(db, akar), env) == ["GEMINI_API_KEY"]
    assert env == {"GEMINI_API_KEY": "kunci-situs", "SMTP_HOST": "smtp.lama"}


def test_perintah_diambil_lalu_ditutup_oleh_proses_yang_sama(akar):
    db = DBTiruan()
    db.data["lbp_perintah"] = {"perbarui": {"jenis": "perbarui", "masukan": {"demo": "otomatis"}, "status": "menunggu"}}
    url = "https://github.com/x/y/actions/runs/7"
    ringkas = fs.tarik(akar, url, db=db)
    assert [p["jenis"] for p in ringkas["perintah"]] == ["perbarui"]
    assert db.data["lbp_perintah"]["perbarui"]["status"] == "berjalan"
    assert db.data["lbp_status"]["pipeline"]["status"] == "berjalan"
    fs.lapor("success", url, db=db)
    assert db.data["lbp_perintah"]["perbarui"]["status"] == "selesai"
    assert db.data["lbp_status"]["pipeline"]["hasil"] == "success"

    # Permintaan baru yang masuk saat proses lain berjalan tidak ikut ditutup.
    db.data["lbp_perintah"]["perbarui"] = {"jenis": "perbarui", "masukan": {}, "status": "menunggu"}
    fs.lapor("failure", url, db=db)
    assert db.data["lbp_perintah"]["perbarui"]["status"] == "menunggu"


def test_pemeriksa_berkala(akar):
    db = DBTiruan()
    kini = T0 + timedelta(hours=20)  # 04.00 WIB: AI harian belum jatuh tempo
    assert fs.perlu_jalan(akar, db, kini) == (False, "tidak ada yang baru")
    db.data["lbp_harga"] = {"k1": _harga("k1", T0)}
    assert fs.perlu_jalan(akar, db, kini)[0] is True
    db.data["lbp_status"] = {"pipeline": {"status": "selesai", "selesai": kini - timedelta(minutes=10)}}
    assert fs.perlu_jalan(akar, db, kini)[0] is True  # bawaan: harga baru langsung diproses
    jalan, alasan = fs.perlu_jalan(akar, db, kini, jeda_harga_menit=60)
    assert not jalan and "jeda" in alasan
    db.data["lbp_tindak_lanjut"] = {"a": {"diperbarui": T0}}
    assert fs.perlu_jalan(akar, db, kini)[0] is True
    db.data["lbp_status"]["pipeline"] = {"status": "berjalan", "mulai": kini - timedelta(minutes=5)}
    assert fs.perlu_jalan(akar, db, kini) == (False, "proses lain sedang berjalan")
    db.data["lbp_status"]["pipeline"]["mulai"] = kini - timedelta(hours=2)  # proses macet tidak menahan selamanya
    assert fs.perlu_jalan(akar, db, kini)[0] is True
    db.data = {"lbp_perintah": {"cari_sumber": {"status": "menunggu"}}}
    assert fs.perlu_jalan(akar, db, kini) == (True, "ada permintaan cari_sumber")


def test_kebijakan_rapat_keputusan_dan_kunjungan_dari_situs(akar):
    from pipeline import kebijakan

    db = DBTiruan()
    db.data["lbp_kebijakan"] = {"k1": {"tanggal_mulai": "2026-09-20", "tanggal_selesai": "", "jenis": "operasi_pasar",
                                       "kode_varian": ["crw02", "CRW01"], "tujuan": "menurunkan_harga", "uraian": "Pasar murah",
                                       "id_rekomendasi": "R-abc", "pencatat": "TPID", "diperbarui": T0}}
    db.data["lbp_rapat"] = {"r1": {"tanggal": "2026-09-25", "jenis": "rapat_koordinasi", "agenda": "Cabai", "keputusan": "Pasar murah",
                                   "jumlah_sinyal": 2, "peserta": "BPS, Disdag", "tautan_notulen": "", "pencatat": "TPID", "diperbarui": T0}}
    db.data["lbp_keputusan_rekomendasi"] = {"R-abc": {"keputusan": "setuju", "catatan": "", "penyetuju": "Kepala", "tanggal": "2026-09-19",
                                                      "diperbarui": T0}}
    db.data["lbp_kunjungan"] = {"v1": {"tanggal": "2026-09-27", "kode_pasar": "PSR01", "responden": "R9", "status": "menolak",
                                       "alasan": "takut_pajak", "petugas": "PTG01", "waktu_input": "", "diperbarui": T0}}
    fs.tarik(akar, db=db)
    k = kebijakan.baca_kebijakan(akar)
    assert k[0]["kode_varian"] == "CRW02;CRW01" and k[0]["jenis"] == "operasi_pasar"
    assert kebijakan.baca_rapat(akar)[0]["jumlah_sinyal"] == "2"
    assert kebijakan.baca_keputusan_rekomendasi(akar)["R-abc"]["keputusan"] == "setuju"
    assert kinerja.baca_kunjungan(akar / "data" / "kunjungan")[0]["status"] == "menolak"
    assert (akar / "data/kunjungan/situs_2026-09.csv").exists()


def test_ringkasan_pemakaian_akun_tanpa_data_pribadi(akar):
    db = DBTiruan()
    kini = T0 + timedelta(days=40)
    db.data["lbp_pengguna"] = {
        "a": {"email": "a@x.id", "status": "aktif", "peran": "admin", "dibuat": T0, "terakhir_aktif": kini - timedelta(days=1)},
        "b": {"email": "b@x.id", "status": "aktif", "peran": "petugas", "dibuat": T0 + timedelta(days=2), "terakhir_aktif": kini - timedelta(days=45)},
        "c": {"email": "c@x.id", "status": "menunggu", "peran": None, "dibuat": T0},
    }
    r = fs.ringkas_adopsi([(k, v) for k, v in db.data["lbp_pengguna"].items()], kini)
    assert r["akun_aktif"] == 2 and r["aktif_30_hari"] == 1 and r["mulai"] == "2026-09-28"
    assert r["per_peran"]["petugas"] == {"akun": 1, "aktif_30_hari": 0}
    assert "x.id" not in json.dumps(r)
    assert fs.tulis_adopsi(akar, r) and not fs.tulis_adopsi(akar, r)  # tidak ditulis ulang bila sama
    hasil = kinerja.adopsi(akar / "data" / "adopsi.json", date(2026, 11, 10))
    assert hasil["persen"] == 50.0 and hasil["bulan_ke"] == 2 and hasil["target_persen"] == 35


def test_format_pengaturan_sama_dengan_panel_admin():
    from .conftest import AKAR

    teks = (AKAR / "config/pengaturan.json").read_text(encoding="utf-8")
    assert fs.tulis_pengaturan(json.loads(teks)) == teks


@pytest.mark.skipif(not os.environ.get("FIRESTORE_EMULATOR_HOST"), reason="butuh emulator Firestore")
def test_dengan_emulator_firestore(akar, monkeypatch):
    """Uji kueri sungguhan (stempel waktu server) di emulator: npm run uji:mesin."""
    pytest.importorskip("google.cloud.firestore")
    from google.cloud import firestore

    monkeypatch.setenv("GCLOUD_PROJECT", "demo-lbp")
    db = fs.klien()
    for k in ("lbp_harga", "lbp_status", "lbp_perintah"):
        for d in db.collection(k).stream():
            d.reference.delete()
    db.collection("lbp_harga").document("e1").set(_harga("e1", firestore.SERVER_TIMESTAMP))
    assert fs.perlu_jalan(akar, db)[0] is True
    assert fs.tarik(akar, "u", db=db)["berkas"] == {"data/masuk/harga/situs/situs_2026-09.csv": 1}
    fs.lapor("success", "u", db=db)
    # jam dinding sungguhan: lewat 08.00 WIB AI harian jatuh tempo sampai dicatat sudah jalan hari ini
    hari_ini = datetime.now(timezone.utc).astimezone(fs.WIB).date().isoformat()
    fs.catat_ai_harian(db, hari_ini, 0, ["cabai rawit merah"])
    assert fs.ai_harian_jatuh_tempo(akar, db, datetime.now(timezone.utc)) is False
    jalan, alasan = fs.perlu_jalan(akar, db)
    assert not jalan, alasan
    db.collection("lbp_harga").document("e2").set(_harga("e2", firestore.SERVER_TIMESTAMP))
    assert fs.tarik(akar, "u", db=db)["berkas"] == {"data/masuk/harga/situs/situs_2026-09.csv": 1}


def test_data_dashboard_ke_firestore_hanya_yang_berubah(tmp_path):
    folder = tmp_path / "data"
    (folder / "seri").mkdir(parents=True)
    (folder / "unduh").mkdir()
    (folder / "meta.json").write_text('{"dibuat": "2026-10-02T08:00:00+07:00", "login": "firebase"}', encoding="utf-8")
    (folder / "ringkasan.json").write_text('{"kpi": [1, 2]}', encoding="utf-8")
    (folder / "master.json").write_text('{"varian": []}', encoding="utf-8")
    (folder / "seri" / "CMR01.json").write_text('{"harga": [[1, 2]]}', encoding="utf-8")
    besar = "tanggal,harga\n" + "2026-10-01,55000\n" * 40_000  # lebih dari satu bagian
    (folder / "unduh" / "harga_harian.csv").write_text(besar, encoding="utf-8")
    db = DBTiruan()

    h = fs.terbit_data(folder, db=db)
    data = db.data["lbp_data"]
    assert sorted(h["ditulis"]) == ["master.json", "meta.json", "ringkasan.json", "seri/CMR01.json", "unduh/harga_harian.csv"]
    assert h["ditulis"][-1] == "meta.json"  # meta paling akhir: tanda bagi situs bahwa data baru sudah lengkap
    assert json.loads(data["seri~CMR01.json"]["isi"]) == {"harga": [[1, 2]]}
    dok = data["unduh~harga_harian.csv"]
    assert dok["bagian"] == 3 and dok["versi"] == "2026-10-02T08:00:00+07:00"
    assert dok["isi"] + data["unduh~harga_harian.csv@2"]["isi"] + data["unduh~harga_harian.csv@3"]["isi"] == besar

    # Jalan kedua tanpa perubahan: hanya meta yang ditulis ulang.
    assert fs.terbit_data(folder, db=db)["ditulis"] == ["meta.json"]

    # Berkas berubah, mengecil, dan ada yang hilang.
    (folder / "unduh" / "harga_harian.csv").write_text("tanggal,harga\n", encoding="utf-8")
    (folder / "seri" / "CMR01.json").unlink()
    h = fs.terbit_data(folder, db=db, hapus_berkas=True)
    assert h["ditulis"] == ["unduh/harga_harian.csv", "meta.json"] and h["dihapus"] == ["seri/CMR01.json"]
    assert "seri~CMR01.json" not in data and "unduh~harga_harian.csv@2" not in data and "unduh~harga_harian.csv@3" not in data
    # Berkas berisi harga tidak ikut diterbitkan terbuka; meta dan master tetap.
    assert sorted(h["disembunyikan"]) == ["ringkasan.json", "unduh/harga_harian.csv"]
    assert sorted(fs.berkas_data(folder)) == ["master.json", "meta.json"]


def test_ai_harian_jatuh_tempo_sekali_sehari_mulai_jam_delapan(akar):
    db = DBTiruan()
    pagi = datetime(2026, 10, 2, 0, 30, tzinfo=timezone.utc)   # 07.30 WIB
    siang = datetime(2026, 10, 2, 2, 0, tzinfo=timezone.utc)   # 09.00 WIB
    assert not fs.ai_harian_jatuh_tempo(akar, db, pagi)
    assert fs.ai_harian_jatuh_tempo(akar, db, siang)
    assert fs.perlu_jalan(akar, db, siang) == (True, "AI Data Finder harian")
    fs.catat_ai_harian(db, "2026-10-02", 2, ["Beras", "Cabai"])
    assert not fs.ai_harian_jatuh_tempo(akar, db, siang)
    assert fs.ai_harian_jatuh_tempo(akar, db, siang + timedelta(days=1))
    # Bisa dimatikan dari Pengaturan
    path = akar / "config/pengaturan.json"
    isi = json.loads(path.read_text(encoding="utf-8"))
    isi["ai"]["harian_aktif"] = False
    path.write_text(json.dumps(isi), encoding="utf-8")
    assert not fs.ai_harian_jatuh_tempo(akar, db, siang + timedelta(days=1))


def test_hasil_ai_dari_situs_diambil_sekali(akar):
    db = DBTiruan()
    db.data["lbp_kandidat_ai"] = {"a": {"permintaan": {"komoditas": "cabai"}, "hasil": "{}", "diperbarui": T0}}
    assert fs.tarik(akar, db=db)["kandidat_situs"][0]["permintaan"] == {"komoditas": "cabai"}
    assert "kandidat_situs" not in fs.tarik(akar, db=db)

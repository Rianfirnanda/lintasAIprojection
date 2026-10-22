"""Alat bantu pindah proyek: salin akun pengguna dan situs pengalih untuk alamat lama."""

from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import migrasi
from pipeline.__main__ import main

AKAR = Path(__file__).resolve().parents[1]


def akun_google(uid, email, sub, **lain):
    return {"localId": uid, "email": email, "emailVerified": True, "displayName": email.split("@")[0],
            "createdAt": "1700000000000", "lastLoginAt": "1700000500000", "validSince": "1700000000",
            "providerUserInfo": [{"providerId": "google.com", "rawId": sub, "email": email, "federatedId": sub}], **lain}


def tulis_kunci(path: Path, proyek: str) -> Path:
    path.write_text(json.dumps({"type": "service_account", "project_id": proyek}), encoding="utf-8")
    return path


# ---------------------------------------------------------------- Firebase tiruan

class _Jawab:
    def __init__(self, data, status=200):
        self.status_code, self._data, self.text = status, data, json.dumps(data)

    def json(self):
        return self._data


class SesiTiruan:
    """Firebase Authentication tiruan: daftar akun per proyek dan rekaman batchCreate yang diterima."""

    def __init__(self, akun: dict[str, list[dict]], tolak_indeks=(), status=200):
        self.akun, self.tolak, self.status, self.dibuat = akun, set(tolak_indeks), status, []

    def get(self, url, params=None, timeout=None):
        proyek = re.search(r"/projects/([^/]+)/", url).group(1)
        if self.status != 200:
            return _Jawab({"error": {"message": "Caller does not have permission; admin@contoh.go.id"}}, self.status)
        return _Jawab({"users": list(self.akun.get(proyek, []))})

    def post(self, url, json=None, timeout=None):
        proyek = re.search(r"/projects/([^/]+)/", url).group(1)
        self.dibuat.append((proyek, json["users"]))
        diterima = [u for i, u in enumerate(json["users"]) if i not in self.tolak]
        self.akun.setdefault(proyek, []).extend(diterima)
        return _Jawab({"error": [{"index": i, "message": "ditolak"} for i in sorted(self.tolak)]})


class _Dok:
    def __init__(self, id_, data):
        self.id, self._data = id_, data

    def to_dict(self):
        return dict(self._data)


class _Koleksi:
    def __init__(self, db, nama):
        self.db, self.nama = db, nama

    def list_documents(self):
        return [SimpleNamespace(id=i) for i in self.db.data.get(self.nama, {})]

    def stream(self):
        return [_Dok(i, d) for i, d in self.db.data.get(self.nama, {}).items()]

    def document(self, id_):
        return (self.nama, id_)


class _Batch:
    def __init__(self, db):
        self.db, self.tulisan = db, []

    def set(self, ref, data):
        self.tulisan.append((ref, data))

    def commit(self):
        self.db.commit += 1
        for (nama, id_), data in self.tulisan:
            self.db.data.setdefault(nama, {})[id_] = data


class DbTiruan:
    def __init__(self, data=None):
        self.data, self.commit = data or {}, 0

    def collection(self, nama):
        return _Koleksi(self, nama)

    def batch(self):
        return _Batch(self)


# ---------------------------------------------------------------- akun login

def test_rekam_impor_berbentuk_sama_dengan_firebase_admin():
    u = akun_google("uidA", "a@contoh.id", "111", customAttributes='{"x":1}')
    u["providerUserInfo"].append({"providerId": "password", "rawId": "a@contoh.id"})
    r = migrasi.rekam_impor(u)
    assert r == {"localId": "uidA", "email": "a@contoh.id", "displayName": "a", "customAttributes": '{"x":1}',
                 "emailVerified": True, "disabled": False, "createdAt": 1700000000000, "lastLoginAt": 1700000500000,
                 "providerUserInfo": [{"rawId": "111", "providerId": "google.com", "email": "a@contoh.id"}]}


def test_rencana_akun_melewati_yang_sudah_ada_dan_yang_sudah_masuk_lebih_dulu():
    lama = [akun_google("uidA", "a@contoh.id", "111"), akun_google("uidB", "b@contoh.id", "222"),
            akun_google("uidC", "C@contoh.id", "333"), akun_google("uidD", "d@contoh.id", "444")]
    baru = [akun_google("uidB", "b@contoh.id", "222"),            # sudah disalin sebelumnya
            akun_google("uidC2", "c@contoh.id", "333"),           # orang C sudah masuk ke situs baru lebih dulu
            akun_google("uidX", "lain@contoh.id", "444")]         # akun Google D dipakai akun lain di proyek baru
    rekaman, lewati, jumlah = migrasi.rencana_akun(lama, baru)
    assert [r["localId"] for r in rekaman] == ["uidA"]
    assert lewati == {"uidC", "uidD"}
    assert jumlah == {"lama": 4, "dipindah": 0, "sudah_ada": 1, "bentrok": 2, "gagal": 0}


def test_daftar_akun_membaca_semua_halaman():
    class Sesi:
        def __init__(self):
            self.token = []

        def get(self, url, params=None, timeout=None):
            self.token.append(params.get("nextPageToken"))
            if "nextPageToken" not in params:
                return _Jawab({"users": [{"localId": "a"}], "nextPageToken": "t2"})
            return _Jawab({"users": [{"localId": "b"}]})

    s = Sesi()
    assert [u["localId"] for u in migrasi.daftar_akun(s, "p")] == ["a", "b"]
    assert s.token == [None, "t2"]


def test_galat_izin_memberi_saran_dan_tidak_membocorkan_email(tmp_path):
    sesi = SesiTiruan({}, status=403)
    with pytest.raises(RuntimeError) as e:
        migrasi.salin_akun(tulis_kunci(tmp_path / "l.json", "lama"), tulis_kunci(tmp_path / "b.json", "baru"),
                           sesi_fn=lambda k: sesi, klien_fn=lambda k: DbTiruan())
    assert "Firebase Authentication Viewer" in str(e.value) and "@" not in str(e.value)


# ---------------------------------------------------------------- koleksi Firestore

def test_salin_koleksi_tidak_menimpa_dan_menulis_bertahap(monkeypatch):
    monkeypatch.setattr(migrasi, "MAKS_TULIS", 2)
    db_lama = DbTiruan({"lbp_jejak": {f"j{i}": {"aksi": "setujui", "n": i} for i in range(5)}})
    db_baru = DbTiruan({"lbp_jejak": {"j0": {"aksi": "sudah diubah di situs baru"}}})
    jumlah = migrasi.salin_koleksi(db_lama, db_baru, "lbp_jejak", lewati={"j4"})
    assert jumlah == {"disalin": 3, "sudah_ada": 1, "dilewati": 1}
    assert db_baru.data["lbp_jejak"]["j0"] == {"aksi": "sudah diubah di situs baru"}
    assert sorted(db_baru.data["lbp_jejak"]) == ["j0", "j1", "j2", "j3"]
    assert db_baru.commit == 2


def test_salin_akun_alur_lengkap(tmp_path, capsys):
    sesi = SesiTiruan({"lama": [akun_google("uidA", "a@contoh.id", "111"), akun_google("uidB", "b@contoh.id", "222"),
                                akun_google("uidC", "c@contoh.id", "333")],
                       "baru": [akun_google("uidC2", "c@contoh.id", "333")]},
                      tolak_indeks=[1])  # akun kedua yang dimasukkan (uidB) ditolak proyek baru
    db = {"lama": DbTiruan({"lbp_pengguna": {u: {"status": "aktif", "peran": "petugas"} for u in ("uidA", "uidB", "uidC")},
                            "lbp_akses": {"pendaftaran": {"otomatis": True}, "peran": {"halaman": {"tpid": ["harga"]}}},
                            "lbp_jejak": {"j1": {"aksi": "setujui"}}}),
          "baru": DbTiruan({"lbp_pengguna": {"uidC2": {"status": "menunggu"}}})}
    hasil = migrasi.salin_akun(tulis_kunci(tmp_path / "l.json", "lama"), tulis_kunci(tmp_path / "b.json", "baru"),
                               sesi_fn=lambda k: sesi, klien_fn=lambda k: db[k["project_id"]])
    assert hasil["akun"] == {"lama": 3, "dipindah": 1, "sudah_ada": 0, "bentrok": 1, "gagal": 1}
    assert [u["localId"] for u in sesi.akun["baru"]] == ["uidC2", "uidA"]
    assert set(db["baru"].data["lbp_pengguna"]) == {"uidC2", "uidA"}  # uidB (ditolak) dan uidC (bentrok) tidak disalin
    assert db["baru"].data["lbp_akses"]["pendaftaran"] == {"otomatis": True}
    assert hasil["koleksi"]["lbp_jejak"] == {"disalin": 1, "sudah_ada": 0, "dilewati": 0}
    assert not db["lama"].commit, "proyek lama hanya dibaca"
    migrasi.cetak_ringkasan(hasil)
    keluaran = capsys.readouterr().out
    assert "1 dipindah" in keluaran and "@" not in keluaran and "uid" not in keluaran


def test_salin_akun_menolak_kunci_yang_salah(tmp_path):
    with pytest.raises(ValueError, match="proyek yang sama"):
        migrasi.salin_akun(tulis_kunci(tmp_path / "l.json", "p"), tulis_kunci(tmp_path / "b.json", "p"),
                           sesi_fn=lambda k: None, klien_fn=lambda k: None)
    (tmp_path / "kosong.json").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="kosong atau bukan JSON"):
        migrasi.baca_kunci(tmp_path / "kosong.json")
    (tmp_path / "pengguna.json").write_text('{"type": "authorized_user", "project_id": "p"}', encoding="utf-8")
    with pytest.raises(ValueError, match="bukan kunci akun layanan"):
        migrasi.baca_kunci(tmp_path / "pengguna.json")


# ---------------------------------------------------------------- pengalih alamat lama

def test_pengalih_berisi_halaman_pengarah_dan_pencabut_service_worker(tmp_path):
    folder = migrasi.siapkan_pengalih(tmp_path / "p", "https://takarpangan.contoh.go.id", "lintas-benteng-proyeksi",
                                      situs_aktif="takar-pangan")
    halaman = (folder / "situs/index.html").read_text(encoding="utf-8")
    assert 'var tujuan = "https://takarpangan.contoh.go.id/".replace(/\\/$/, "") + location.pathname' in halaman
    assert 'content="4; url=https://takarpangan.contoh.go.id/"' in halaman and ">takarpangan.contoh.go.id</a>" in halaman
    assert "Takar Pangan 10•21" in halaman and "unregister" in halaman
    sw = (folder / "situs/sw.js").read_text(encoding="utf-8")
    assert "skipWaiting" in sw and "registration.unregister()" in sw and "caches.delete" in sw
    konfig = json.loads((folder / "firebase.json").read_text(encoding="utf-8"))["hosting"]
    assert konfig["site"] == "lintas-benteng-proyeksi" and konfig["public"] == "situs"
    assert konfig["rewrites"] == [{"source": "**", "destination": "/index.html"}]
    assert "redirects" not in konfig, "aturan redirects juga mengenai sw.js, padahal browser menolak sw.js yang dialihkan"
    for teks in (halaman, sw):
        assert "—" not in teks and "–" not in teks


@pytest.mark.parametrize("alamat, situs, aktif, pesan", [
    ("http://takar.contoh.go.id/", "lama-situs", "", "https"),
    ("https://takar.contoh.go.id/?a=1", "lama-situs", "", "https"),
    ("https://takar.contoh.go.id/\"><script>", "lama-situs", "", "https"),
    ("https://takar.contoh.go.id/", "https://lama-situs.web.app", "", "tidak sah"),
    ("https://takar.contoh.go.id/", "", "", "tidak sah"),
    ("https://takar.contoh.go.id/", "takar-baru", "takar-baru", "sedang dipakai"),
    ("https://lama-situs.web.app/", "lama-situs", "takar-baru", "berputar"),
])
def test_pengalih_menolak_isian_yang_berbahaya(tmp_path, alamat, situs, aktif, pesan):
    with pytest.raises(ValueError, match=pesan):
        migrasi.siapkan_pengalih(tmp_path, alamat, situs, situs_aktif=aktif)


def test_alamat_baru_mengikuti_url_dashboard_lalu_situs_firebase():
    assert migrasi.alamat_situs({"URL_DASHBOARD": " https://a.go.id/ ", "FIREBASE_HOSTING_SITE": "b"}) == "https://a.go.id/"
    assert migrasi.alamat_situs({"URL_DASHBOARD": "", "FIREBASE_HOSTING_SITE": "takar-baru"}) == "https://takar-baru.web.app/"
    assert migrasi.alamat_situs({}) == ""


def test_perintah_pengalih_dan_galat_singkat(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("URL_DASHBOARD", "https://takar-baru.web.app/")
    monkeypatch.setenv("FIREBASE_HOSTING_SITE", "takar-baru")
    assert main(["migrasi", "pengalih", "--situs", "situs-lama", "--keluaran", str(tmp_path / "p")]) == 0
    assert (tmp_path / "p/situs/sw.js").exists()
    assert main(["migrasi", "pengalih", "--situs", "takar-baru", "--keluaran", str(tmp_path / "q")]) == 2
    assert "GAGAL" in capsys.readouterr().err and not (tmp_path / "q").exists()
    assert main(["migrasi", "salin-akun", "--lama", str(tmp_path / "tidak-ada.json"), "--baru", str(tmp_path / "x.json")]) == 2


def test_alur_kerja_migrasi_aman_untuk_repositori_publik():
    teks = (AKAR / ".github/workflows/migrasi.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in teks and "schedule:" not in teks and "contents: read" in teks
    sisipan = [b.strip() for b in teks.splitlines() if "${{ inputs." in b]
    assert sisipan == ["SITUS_LAMA: ${{ inputs.situs_lama }}"], "isian formulir hanya lewat env, tidak disisipkan ke skrip"
    assert 'rm -f "$RUNNER_TEMP/akun-lama.json"' in teks and "if: always()" in teks


# ---------------------------------------------------------------- emulator (npm run uji:migrasi)

def _jwt_google(sub: str, email: str) -> str:
    bagian = [{"alg": "none", "typ": "JWT"}, {"sub": sub, "email": email, "email_verified": True,
                                              "iss": "https://accounts.google.com", "aud": "uji"}]
    return ".".join(base64.urlsafe_b64encode(json.dumps(b).encode()).decode().rstrip("=") for b in bagian) + "."


@pytest.mark.skipif(not (os.environ.get("FIRESTORE_EMULATOR_HOST") and os.environ.get("FIREBASE_AUTH_EMULATOR_HOST")),
                    reason="butuh emulator Auth dan Firestore: npm run uji:migrasi")
def test_dengan_emulator_akun_tetap_ber_uid_sama_saat_masuk_lagi(tmp_path):
    import requests

    from google.cloud import firestore

    host = os.environ["FIREBASE_AUTH_EMULATOR_HOST"]
    sesi = migrasi.sesi_auth({})
    lama, baru = "demo-lama", "demo-baru"  # emulator dijalankan dengan --project demo-baru
    for p in (lama, baru):
        requests.delete(f"http://{host}/emulator/v1/projects/{p}/accounts", timeout=10)
        requests.delete(f"http://{os.environ['FIRESTORE_EMULATOR_HOST']}/emulator/v1/projects/{p}/databases/(default)/documents",
                        timeout=10)
    sesi.post(migrasi._alamat_auth(lama, "batchCreate"), timeout=10, json={"users": [
        migrasi.rekam_impor(akun_google("uidA", "admin@contoh.id", "111")),
        migrasi.rekam_impor(akun_google("uidB", "petugas@contoh.id", "222")),
        migrasi.rekam_impor(akun_google("uidC", "tpid@contoh.id", "333"))]}).raise_for_status()
    sesi.post(migrasi._alamat_auth(baru, "batchCreate"), timeout=10, json={"users": [
        migrasi.rekam_impor(akun_google("uidC2", "tpid@contoh.id", "333"))]}).raise_for_status()

    t = datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc)
    db_lama = firestore.Client(project=lama)
    for uid, peran in (("uidA", "admin"), ("uidB", "petugas"), ("uidC", "tpid")):
        db_lama.collection("lbp_pengguna").document(uid).set({"status": "aktif", "peran": peran, "disetujui_pada": t})
    db_lama.collection("lbp_akses").document("pendaftaran").set({"otomatis": True})
    db_lama.collection("lbp_akses").document("peran").set({"halaman": {"tpid": ["harga", "laporan"]}})
    db_lama.collection("lbp_jejak").document("j1").set({"aksi": "setujui", "pada": t})
    db_baru = firestore.Client(project=baru)
    db_baru.collection("lbp_pengguna").document("uidC2").set({"status": "menunggu"})
    db_baru.collection("lbp_akses").document("peran").set({"halaman": {"tpid": ["harga"]}})

    berkas = (tulis_kunci(tmp_path / "lama.json", lama), tulis_kunci(tmp_path / "baru.json", baru))
    hasil = migrasi.salin_akun(*berkas)
    assert hasil["akun"] == {"lama": 3, "dipindah": 2, "sudah_ada": 0, "bentrok": 1, "gagal": 0}
    assert hasil["koleksi"]["lbp_pengguna"] == {"disalin": 2, "sudah_ada": 0, "dilewati": 1}
    assert hasil["koleksi"]["lbp_akses"] == {"disalin": 1, "sudah_ada": 1, "dilewati": 0}
    assert db_baru.collection("lbp_akses").document("peran").get().to_dict() == {"halaman": {"tpid": ["harga"]}}
    pengguna = db_baru.collection("lbp_pengguna").document("uidB").get().to_dict()
    assert pengguna["peran"] == "petugas" and pengguna["disetujui_pada"] == t
    assert not db_lama.collection("lbp_pengguna").document("uidC2").get().exists

    # Petugas masuk lagi dengan akun Google yang sama di situs baru: UID-nya tetap, jadi perannya langsung berlaku.
    r = requests.post(f"http://{host}/identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key=uji", timeout=10, json={
        "postBody": f"id_token={_jwt_google('222', 'petugas@contoh.id')}&providerId=google.com",
        "requestUri": "http://localhost", "returnSecureToken": True})
    assert r.status_code == 200 and r.json()["localId"] == "uidB" and not r.json().get("isNewUser")

    ulang = migrasi.salin_akun(*berkas)  # aman dijalankan ulang
    assert ulang["akun"]["dipindah"] == 0 and ulang["akun"]["sudah_ada"] == 2
    assert all(j["disalin"] == 0 for j in ulang["koleksi"].values())

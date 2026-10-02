import json

import pytest

from pipeline import firebase
from pipeline.__main__ import main
from tests.conftest import AKAR

KONF = {"apiKey": "AIza-contoh", "authDomain": "lintas-benteng.firebaseapp.com", "projectId": "lintas-benteng", "appId": "1:2:web:3"}


def test_konfigurasi_dari_env_mengalahkan_berkas(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "firebase.json").write_text(json.dumps({"konfigurasi": {**KONF, "projectId": "lain"}}))
    hasil = firebase.konfigurasi_web(tmp_path, {"FIREBASE_WEB_CONFIG": json.dumps(KONF)})
    assert hasil["projectId"] == "lintas-benteng" and "emulator" not in hasil
    # format konsol Firebase dibungkus "konfigurasi" juga diterima
    assert firebase.konfigurasi_web(tmp_path, {"FIREBASE_WEB_CONFIG": json.dumps({"konfigurasi": KONF})})["appId"] == "1:2:web:3"
    assert firebase.konfigurasi_web(tmp_path, {})["projectId"] == "lain"


def test_konfigurasi_salinan_langsung_dari_firebase_console(tmp_path):
    salinan = """// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIza-contoh",
  authDomain: 'lintas-benteng.firebaseapp.com',
  projectId: "lintas-benteng",
  storageBucket: "lintas-benteng.firebasestorage.app",
  appId: "1:2:web:3",
};"""
    hasil = firebase.konfigurasi_web(tmp_path, {"FIREBASE_WEB_CONFIG": salinan})
    assert hasil["authDomain"] == "lintas-benteng.firebaseapp.com" and hasil["storageBucket"].endswith(".app")


def test_konfigurasi_kosong_atau_salah(tmp_path):
    assert firebase.konfigurasi_web(tmp_path, {}) is None
    assert firebase.konfigurasi_web(AKAR, {}) is None  # contoh di repositori masih kosong
    with pytest.raises(ValueError, match="bukan JSON"):
        firebase.konfigurasi_web(tmp_path, {"FIREBASE_WEB_CONFIG": "{apiKey:"})
    with pytest.raises(ValueError, match="authDomain"):
        firebase.konfigurasi_web(tmp_path, {"FIREBASE_WEB_CONFIG": json.dumps({"apiKey": "a", "projectId": "p", "appId": "x"})})


def test_kolom_asing_dibuang_dan_mode_emulator(tmp_path):
    hasil = firebase.konfigurasi_web(tmp_path, {"FIREBASE_WEB_CONFIG": json.dumps({**KONF, "rahasia": "x"}), "FIREBASE_EMULATOR": "1"})
    assert "rahasia" not in hasil and hasil["emulator"]["auth"].startswith("http://127.0.0.1")


def test_daftar_admin_awal():
    assert firebase.daftar_admin_awal(" A@Contoh.go.id, b@contoh.go.id\nA@contoh.go.id ") == ["a@contoh.go.id", "b@contoh.go.id"]
    assert firebase.daftar_admin_awal("") == []
    with pytest.raises(ValueError):
        firebase.daftar_admin_awal("a@contoh.go.id, ']; allow read: if true; //")


def test_aturan_terisi_hanya_di_penanda():
    teks = (AKAR / "firestore.rules").read_text()
    hasil = firebase.aturan_dengan_admin(teks, ["a@contoh.go.id"])
    assert "['a@contoh.go.id']" in hasil and firebase.PENANDA_ADMIN not in hasil
    assert hasil.replace("['a@contoh.go.id']", firebase.PENANDA_ADMIN) == teks


def test_perintah_aturan_firebase(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FIREBASE_ADMIN_AWAL", "admin@contoh.go.id")
    assert main(["aturan-firebase", "--keluaran", str(tmp_path / "a.rules")]) == 0
    assert "'admin@contoh.go.id'" in (tmp_path / "a.rules").read_text()
    monkeypatch.setenv("FIREBASE_ADMIN_AWAL", "bukan email")
    assert main(["aturan-firebase", "--keluaran", str(tmp_path / "b.rules")]) == 2
    assert "GAGAL" in capsys.readouterr().err

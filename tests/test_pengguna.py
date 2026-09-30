"""Akun contoh, rumus sandi, dan penerbitan konfigurasi login."""

import json

import pytest

from pipeline import pengguna, proses
from tests.conftest import AKAR


def test_hash_stabil_dan_tak_peka_huruf_id():
    a = pengguna.hash_sandi("garam", "Admin", "rahasia")
    assert a == pengguna.hash_sandi("garam", " admin ", "rahasia")
    assert a != pengguna.hash_sandi("garam", "admin", "Rahasia")
    # vektor uji yang sama diperiksa di sisi browser (assets/akses.js)
    assert pengguna.hash_sandi("g", "u", "s") == "33451474dc7094004407e36feb9e083f51439ad2fd65ecf569b24b2b8c7129fd"


def test_entri_akun_menolak_peran_tak_dikenal():
    assert pengguna.entri_akun("g", "Budi", "Budi", "petugas", "x")["id"] == "budi"
    with pytest.raises(ValueError):
        pengguna.entri_akun("g", "budi", "Budi", "presiden", "x")


def test_berkas_akun_contoh_sah_dan_mencakup_semua_peran_login():
    data = json.loads((AKAR / "config" / "pengguna.json").read_text(encoding="utf-8"))
    assert pengguna.periksa(data) == []
    assert {a["peran"] for a in data["akun"]} == set(pengguna.PERAN) - {"masyarakat"}  # masyarakat tanpa login
    assert all(len(a["sandi_hash"]) == 64 for a in data["akun"])


def test_periksa_menangkap_masalah():
    assert "garam kosong" in pengguna.periksa({"garam": "", "akun": []})
    masalah = pengguna.periksa({"garam": "g", "akun": [
        {"id": "a", "peran": "x", "sandi_hash": "h"}, {"id": "a", "peran": "admin", "sandi_hash": "h"}]})
    assert any("peran tidak dikenal" in m for m in masalah) and any("id ganda" in m for m in masalah)


def test_firebase_aktif_hanya_bila_terisi():
    assert not pengguna.firebase_aktif(None)
    assert not pengguna.firebase_aktif({"konfigurasi": {"apiKey": "", "projectId": ""}})
    assert pengguna.firebase_aktif({"konfigurasi": {"apiKey": "k", "projectId": "p"}})


def test_pipeline_menerbitkan_login_contoh_lalu_firebase(konf, akar_sementara):
    (akar_sementara / "config" / "pengguna.json").write_text(
        (AKAR / "config" / "pengguna.json").read_text(encoding="utf-8"), encoding="utf-8")
    keluaran = akar_sementara / "site/data"
    proses.jalankan(konf, keluaran, sinkron_github=False)
    assert json.loads((keluaran / "meta.json").read_text())["login"] == "contoh"
    assert (keluaran / "pengguna.json").exists() and not (keluaran / "firebase.json").exists()

    (akar_sementara / "config" / "firebase.json").write_text(
        json.dumps({"konfigurasi": {"apiKey": "k", "projectId": "p", "authDomain": "p.firebaseapp.com"}}), encoding="utf-8")
    proses.jalankan(konf, keluaran, sinkron_github=False)
    assert json.loads((keluaran / "meta.json").read_text())["login"] == "firebase"
    assert (keluaran / "firebase.json").exists()

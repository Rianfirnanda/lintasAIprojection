"""Skema pengaturan, validasinya, dan jaminan bahwa nilai dalam rentang panel admin tidak merusak pipeline."""

import copy
import json
import re
import shutil
from datetime import date
from pathlib import Path

import pytest

from pipeline import __main__ as cli
from pipeline import konfigurasi, pengaturan, proses
from tests.conftest import AKAR, HARI_INI

FOLDER = AKAR / "config"
SKEMA = pengaturan.muat_skema(FOLDER)
DASAR = json.loads((FOLDER / "pengaturan.json").read_text(encoding="utf-8"))


def ubah(dasar: dict, perubahan: dict) -> dict:
    p = copy.deepcopy(dasar)
    for jalur, nilai in perubahan.items():
        bagian = jalur.split(".")
        d = p
        for b in bagian[:-1]:
            d = d[int(b)] if isinstance(d, list) else d[b]
        if isinstance(d, list):
            d[int(bagian[-1])] = nilai
        else:
            d[bagian[-1]] = nilai
    return p


def jalur_salah(perubahan: dict) -> list[str]:
    return sorted({j for j, _ in pengaturan.periksa(ubah(DASAR, perubahan), SKEMA)})


def test_pengaturan_yang_berlaku_sah():
    assert pengaturan.periksa(DASAR, SKEMA) == []
    assert pengaturan.periksa_berkas(FOLDER) == []


def test_setiap_isian_skema_ada_nilainya_dan_berlabel():
    kelompok = {k["kode"] for k in SKEMA["kelompok"]}
    jalur = set()
    for k in SKEMA["kolom"]:
        assert pengaturan.ambil(DASAR, k["jalur"])[0], k["jalur"]
        assert k["kelompok"] in kelompok and len(k["label"]) > 3
        assert k["jalur"] not in jalur, f"jalur ganda {k['jalur']}"
        jalur.add(k["jalur"])
        if k["tipe"] in ("bulat", "desimal"):
            assert k["min"] < k["maks"]
        if k["tipe"] in ("pilihan", "banyak_pilihan", "urutan"):
            assert k["pilihan"], k["jalur"]


def test_isian_yang_menyentuh_privasi_dan_struktur_tidak_bisa_diubah_lewat_panel():
    jalur = {k["jalur"] for k in SKEMA["kolom"]}
    for terlarang in ("privasi.kolom_terlarang", "privasi.min_observasi_publikasi_pasar", "wilayah_target", "zona_waktu"):
        assert terlarang not in jalur


def test_nilai_salah_ditolak_dengan_pesan_yang_menyebut_isian():
    for k in SKEMA["kolom"]:
        if k["tipe"] in ("bulat", "desimal"):
            assert jalur_salah({k["jalur"]: k["min"] - 1}) == [k["jalur"]] or k["jalur"].startswith("sinyal.rasio")
            assert jalur_salah({k["jalur"]: k["maks"] + 1}) == [k["jalur"]] or k["jalur"].startswith(("sinyal.rasio", "target_kinerja.cakupan"))
            assert k["jalur"] in jalur_salah({k["jalur"]: "abc"})
    assert jalur_salah({"ai.penyedia": "openai"}) == ["ai.penyedia"]
    assert jalur_salah({"hari_pencatatan": []}) == ["hari_pencatatan"]
    assert jalur_salah({"notifikasi.aktif": "ya"}) == ["notifikasi.aktif"]
    assert jalur_salah({"layanan.url_survei_eksternal": "javascript:alert(1)"}) == ["layanan.url_survei_eksternal"]
    with pytest.raises(ValueError, match=r"pengaturan.json tidak sah: analisis.horizon_hari: Prakiraan sampai berapa hari"):
        pengaturan.pastikan_sah(ubah(DASAR, {"analisis.horizon_hari": 3}), SKEMA)


def test_aturan_silang():
    assert jalur_salah({"sinyal.rasio_volatilitas_batas.0": 1, "sinyal.rasio_volatilitas_batas.1": 1}) == ["sinyal.rasio_volatilitas_batas.1"]
    assert jalur_salah({"target_kinerja.cakupan_interval_min_persen": 96}) == ["target_kinerja.cakupan_interval_maks_persen"]
    assert jalur_salah({"target_kinerja.cakupan_interval_min_persen": 90, "target_kinerja.cakupan_interval_maks_persen": 90}) == []


def test_muat_menolak_pengaturan_salah_dan_perintah_cli_memberi_pesan_jelas(akar_sementara, capsys):
    path = akar_sementara / "config/pengaturan.json"
    p = json.loads(path.read_text(encoding="utf-8"))
    p["analisis"]["horizon_hari"] = 0
    path.write_text(json.dumps(p), encoding="utf-8")
    with pytest.raises(ValueError, match="horizon_hari"):
        konfigurasi.muat(akar_sementara, hari_ini=HARI_INI)
    assert cli.main(["--akar", str(akar_sementara), "periksa"]) == 2
    assert "GAGAL: config/pengaturan.json tidak sah" in capsys.readouterr().err


def test_tanpa_berkas_skema_pengaturan_tidak_divalidasi(akar_sementara):
    (akar_sementara / "config/skema_pengaturan.json").unlink()
    path = akar_sementara / "config/pengaturan.json"
    p = json.loads(path.read_text(encoding="utf-8"))
    p["analisis"]["horizon_hari"] = 0
    path.write_text(json.dumps(p), encoding="utf-8")
    assert konfigurasi.muat(akar_sementara, hari_ini=HARI_INI).pengaturan["analisis"]["horizon_hari"] == 0


# ---------------------------------------------------------------- konsistensi dengan alur kerja GitHub

def teks_alur(nama: str) -> str:
    return (AKAR / ".github/workflows" / nama).read_text(encoding="utf-8")


def test_semua_secret_yang_dipakai_alur_kerja_ada_di_skema_dan_sebaliknya():
    dipakai = set()
    for berkas in (AKAR / ".github/workflows").glob("*.yml"):
        dipakai |= set(re.findall(r"secrets\.([A-Z][A-Z0-9_]*)", berkas.read_text(encoding="utf-8")))
    dipakai.discard("GITHUB_TOKEN")  # bawaan GitHub Actions, tidak perlu diisi
    tercatat = {r["nama"] for r in SKEMA["rahasia"]}
    assert dipakai == tercatat, f"beda: hanya di alur kerja {dipakai - tercatat}, hanya di skema {tercatat - dipakai}"
    for r in SKEMA["rahasia"]:
        assert re.fullmatch(r"[A-Z][A-Z0-9_]{1,79}", r["nama"]) and not r["nama"].startswith("GITHUB_")


def masukan_alur(nama: str) -> dict[str, list[str] | None]:
    """Nama input workflow_dispatch beserta daftar pilihannya (None bila bukan pilihan)."""
    baris = teks_alur(nama).splitlines()
    mulai = next(i for i, b in enumerate(baris) if b.strip() == "workflow_dispatch:")
    hasil: dict[str, list[str] | None] = {}
    sekarang = None
    for b in baris[mulai + 1:]:
        if b.strip() and not b.startswith("    ") and not b.strip().startswith("#"):
            break
        m = re.match(r"^      (\w+):\s*$", b)
        if m:
            sekarang = m.group(1)
            hasil[sekarang] = None
        o = re.match(r"^\s+options:\s*\[(.*)\]", b)
        if o and sekarang:
            hasil[sekarang] = [x.strip() for x in o.group(1).split(",")]
    return hasil


def test_alur_kerja_di_skema_cocok_dengan_berkas_workflow():
    for alur in SKEMA["alur_kerja"]:
        nyata = masukan_alur(alur["berkas"])
        assert {m["nama"] for m in alur["masukan"]} == set(nyata), alur["berkas"]
        for m in alur["masukan"]:
            if m["tipe"] == "pilihan":
                assert [p["nilai"] for p in m["pilihan"]] == nyata[m["nama"]], f"{alur['berkas']}:{m['nama']}"
                assert m["bawaan"] in nyata[m["nama"]]


def test_pilihan_ai_di_skema_sama_dengan_yang_didukung_pipeline():
    penyedia = next(k for k in SKEMA["kolom"] if k["jalur"] == "ai.penyedia")
    assert [p["nilai"] for p in penyedia["pilihan"]] == masukan_alur("ai-data-finder.yml")["penyedia"]


# ---------------------------------------------------------------- pipeline tetap jalan pada nilai batas

def jalankan_dengan(tmp_path: Path, perubahan: dict):
    shutil.copytree(FOLDER, tmp_path / "config")
    (tmp_path / "data/masuk/harga").mkdir(parents=True)
    (tmp_path / "config/pengaturan.json").write_text(json.dumps(ubah(DASAR, perubahan)), encoding="utf-8")
    konf = konfigurasi.muat(tmp_path, hari_ini=HARI_INI)
    keluaran = tmp_path / "site/data"
    proses.jalankan(konf, keluaran, sinkron_github=False, kirim_notifikasi=False)
    return keluaran


def semua_batas(sisi: str) -> dict:
    hasil = {}
    for k in SKEMA["kolom"]:
        if k["tipe"] in ("bulat", "desimal"):
            hasil[k["jalur"]] = k["min"] if sisi == "min" else k["maks"]
    # menjaga aturan silang tetap terpenuhi
    if sisi == "min":
        hasil["sinyal.rasio_volatilitas_batas.1"] = 1.0
        hasil["target_kinerja.cakupan_interval_maks_persen"] = 50
    else:
        hasil["sinyal.rasio_volatilitas_batas.0"] = 0.9
        hasil["target_kinerja.cakupan_interval_min_persen"] = 90
    return hasil


@pytest.mark.parametrize("sisi", ["min", "maks"])
def test_pipeline_jalan_bila_semua_isian_di_batas_terendah_atau_tertinggi(tmp_path, sisi):
    p = semua_batas(sisi)
    assert pengaturan.periksa(ubah(DASAR, p), SKEMA) == []
    keluaran = jalankan_dengan(tmp_path, p)
    meta = json.loads((keluaran / "meta.json").read_text(encoding="utf-8"))
    assert meta["jumlah"]["observasi_dipakai"] > 0


def test_pipeline_menerbitkan_pengaturan_dan_skema_tanpa_rahasia(tmp_path):
    keluaran = jalankan_dengan(tmp_path, {})
    terbit = json.loads((keluaran / "pengaturan.json").read_text(encoding="utf-8"))
    assert terbit == DASAR
    assert json.loads((keluaran / "skema_pengaturan.json").read_text(encoding="utf-8"))["versi"] == SKEMA["versi"]
    # nama kunci rahasia boleh ada di skema (itu hanya daftar nama), tetapi tidak ada nilai kunci di pengaturan terbit
    teks = (keluaran / "pengaturan.json").read_text(encoding="utf-8")
    assert not re.search(r"AIza[0-9A-Za-z_-]{20,}|sk-ant-|\d{6,}:[A-Za-z0-9_-]{30,}", teks)


# ---------------------------------------------------------------- halaman yang memegang token GitHub

def test_halaman_pengaturan_dikunci_dan_tanpa_pihak_ketiga():
    html = (AKAR / "site/pengaturan.html").read_text(encoding="utf-8")
    csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html).group(1)
    arah = {bagian.split()[0]: bagian.split()[1:] for bagian in csp.split(";") if bagian.strip()}
    assert arah["script-src"] == ["'self'"], "skrip hanya boleh dari situs sendiri"
    # GitHub (tanpa Firebase) atau layanan Firebase (Firestore dan login Google); 127.0.0.1 hanya untuk emulator uji.
    firebase = ["https://firestore.googleapis.com", "https://identitytoolkit.googleapis.com", "https://securetoken.googleapis.com"]
    assert arah["connect-src"] == ["'self'", "https://api.github.com", *firebase, "http://127.0.0.1:8080", "http://127.0.0.1:9099"]
    assert arah["frame-src"] == ["https://*.firebaseapp.com", "https://*.web.app"]
    assert arah["default-src"] == ["'self'"] and arah["object-src"] == ["'none'"] and arah["form-action"] == ["'none'"]
    assert not re.search(r"<script(?![^>]*\bsrc=)", html), "tanpa skrip inline"
    assert 'name="referrer" content="no-referrer"' in html
    # tidak ada alamat luar selain github.com (dan alamat Firebase di CSP) di halaman dan modul yang dimuatnya
    boleh = {"github.com", "api.github.com"}
    for berkas in ("pengaturan.html", "assets/pengaturan.js", "assets/github.js", "assets/pengaturan-inti.js", "assets/pengaturan.css",
                   "assets/pengaturan-firestore.js"):
        teks = (AKAR / "site" / berkas).read_text(encoding="utf-8")
        if berkas == "pengaturan.html":
            teks = teks.replace(csp, "")
        host = set(re.findall(r"https?://([A-Za-z0-9.-]+)", teks)) - {"www.w3.org"}
        assert host <= boleh, f"{berkas} menyebut alamat luar: {host - boleh}"


def test_halaman_pengaturan_hanya_untuk_admin():
    akses = (AKAR / "site/assets/akses.js").read_text(encoding="utf-8")
    assert "pengaturan: [\"pengaturan.html\"" in akses
    blok = {m.group(1): m.group(2) for m in re.finditer(r"^  (\w+): \{\n(.*?)^  \},", akses, re.S | re.M)}
    for peran, isi in blok.items():
        assert ('"pengaturan"' in isi) == (peran == "admin"), peran


def test_token_dan_kunci_tidak_disimpan_di_repositori_atau_dicatat():
    kode = "\n".join((AKAR / "site" / b).read_text(encoding="utf-8") for b in ("assets/pengaturan.js", "assets/github.js"))
    assert "localStorage" not in kode, "token tidak boleh ke localStorage"
    assert "console.log" not in kode
    assert re.search(r"sessionStorage\.setItem\(KUNCI_SESI", kode)

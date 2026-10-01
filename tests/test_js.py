"""Menjalankan uji JavaScript panel admin (tests_js/) dan membandingkan validator JS dengan validator Python."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline import pengaturan
from tests.conftest import AKAR
from tests.test_pengaturan import DASAR, SKEMA

NODE = shutil.which("node")


def versi_node() -> int:
    if not NODE:
        return 0
    return int(subprocess.run([NODE, "-p", "process.versions.node.split('.')[0]"], capture_output=True, text=True).stdout.strip() or 0)


# Di GitHub Actions (CI=true) Node.js wajib ada supaya uji panel admin tidak diam-diam terlewat.
# Di komputer lokal tanpa Node.js, uji ini dilewati saja.
if versi_node() < 20:
    if os.environ.get("CI"):
        pytest.fail("Uji panel admin butuh Node.js 20 atau lebih baru (tambahkan actions/setup-node di workflow)", pytrace=False)
    pytestmark = pytest.mark.skip(reason="butuh Node.js 20 atau lebih baru")


def test_uji_javascript_lulus():
    berkas = sorted(str(p) for p in (AKAR / "tests_js").glob("*.test.mjs"))
    assert berkas
    hasil = subprocess.run([NODE, "--test", *berkas], cwd=AKAR, capture_output=True, text=True, timeout=120)
    assert hasil.returncode == 0, hasil.stdout[-3000:] + hasil.stderr[-1000:]


def kasus_uji() -> list[dict]:
    kasus: list[dict] = [{}]
    for k in SKEMA["kolom"]:
        j, t = k["jalur"], k["tipe"]
        if t in ("bulat", "desimal"):
            kasus += [{j: k["min"]}, {j: k["maks"]}, {j: k["min"] - 1}, {j: k["maks"] + 1}, {j: "abc"}, {j: None}, {j: True}]
            if t == "bulat":
                kasus.append({j: k["min"] + 0.5})
        elif t == "saklar":
            kasus += [{j: True}, {j: False}, {j: "ya"}, {j: 1}, {j: None}]
        elif t in ("pilihan", "urutan"):
            kasus += [{j: p["nilai"]} for p in k["pilihan"]] + [{j: "tidak-ada"}, {j: None}, {j: 5}]
            if t == "urutan":
                kasus += [{j: []}, {j: ["gemini", "gemini"]}, {j: ["openai"]}]
        elif t == "banyak_pilihan":
            semua = [p["nilai"] for p in k["pilihan"]]
            kasus += [{j: semua}, {j: []}, {j: semua[:1]}, {j: [*semua[:1], *semua[:1]]}, {j: [99]}, {j: "semua"}, {j: [True]}]
        elif t == "teks":
            kasus += [{j: "gemini-flash-latest"}, {j: ""}, {j: "ada spasi"}, {j: "x" * 300}, {j: 5}, {j: "a/b.c:d-1"}]
        elif t == "url":
            kasus += [{j: ""}, {j: "https://contoh.go.id/x"}, {j: "http://contoh.go.id"}, {j: "ftp://x.y"}, {j: "https://a b"}, {j: "javascript:1"}, {j: 5}]
    kasus += [
        {"sinyal.rasio_volatilitas_batas.0": 1, "sinyal.rasio_volatilitas_batas.1": 1},
        {"sinyal.rasio_volatilitas_batas.0": 0.4, "sinyal.rasio_volatilitas_batas.1": 1.5},
        {"target_kinerja.cakupan_interval_min_persen": 96},
        {"target_kinerja.cakupan_interval_min_persen": 90, "target_kinerja.cakupan_interval_maks_persen": 90},
        {"analisis.horizon_hari": 0, "analisis.minimal_hari_riwayat": 1, "notifikasi.aktif": "x"},
    ]
    return kasus


def ubah(perubahan: dict) -> dict:
    from tests.test_pengaturan import ubah as _ubah
    return _ubah(DASAR, perubahan)


def test_validator_javascript_sama_dengan_validator_python(tmp_path: Path):
    kasus = kasus_uji()
    berkas = tmp_path / "kasus.json"
    berkas.write_text(json.dumps({"skema": SKEMA, "dasar": DASAR, "kasus": kasus}), encoding="utf-8")
    hasil = subprocess.run([NODE, str(AKAR / "tests_js/paritas.mjs"), str(berkas)], cwd=AKAR, capture_output=True, text=True, timeout=60)
    assert hasil.returncode == 0, hasil.stderr[-2000:]
    dari_js = json.loads(hasil.stdout)
    dari_python = [sorted({j for j, _ in pengaturan.periksa(ubah(k), SKEMA)}) for k in kasus]
    assert len(dari_js) == len(dari_python) == len(kasus)
    beda = [(k, js, py) for k, js, py in zip(kasus, dari_js, dari_python) if js != py]
    assert not beda, f"validator JS dan Python berbeda pada {len(beda)} kasus, contoh: {beda[:3]}"

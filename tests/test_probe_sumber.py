"""Penjajakan sumber data: tidak boleh melempar galat, tidak mengarang data, dan hasilnya terbaca manusia."""

from __future__ import annotations

import json

from pipeline import probe_sumber as p


def _palsu(isi: bytes, status=200, jenis="application/json"):
    return lambda url, *a, **k: {"url": url, "status": status, "jenis": jenis, "byte": len(isi), "detik": 0.1, "isi": isi}


def test_probe_mencatat_wilayah_yang_muncul_dan_bentuk_tabel(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "JEDA", 0)
    isi = json.dumps({"data": [{"level": 1, "name": "Beras"}, {"level": 2, "name": "Beras Kualitas Bawah I"}], "kota": "Kota Bengkulu"}).encode()
    hasil = p.jalankan(tmp_path, _palsu(isi))
    tabel = [r for r in hasil["pihps"] if "tipe_laporan" in r.get("catatan", "")]
    assert len(tabel) == 3 and tabel[0]["jumlah_baris"] == 2 and tabel[0]["wilayah_disebut"] == ["bengkulu", "kota bengkulu"]
    assert tabel[0]["nama_level"] == [("1", "Beras"), ("2", "Beras Kualitas Bawah I")]
    tersimpan = json.loads((tmp_path / "data/sumber/hasil_probe.json").read_text(encoding="utf-8"))
    assert set(tersimpan) == {"waktu", "pihps", "bapanas", "lain"}


def test_probe_tahan_galat_jaringan_dan_halaman_bukan_json(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "JEDA", 0)
    gagal = lambda url, *a, **k: {"url": url, "status": 0, "jenis": "", "byte": 0, "detik": 1.0, "isi": b"", "galat": "URLError: tidak terjangkau"}
    hasil = p.jalankan(tmp_path, gagal)
    assert all(r["status"] == 0 and r["galat"] for k in ("pihps", "bapanas", "lain") for r in hasil[k])
    html = b'<html><a href="/api/harga/kabupaten">x</a><a href="/tentang">y</a></html>'
    lain = p.penjajakan_lain(_palsu(html, jenis="text/html"))
    assert lain[0]["json"] is False and lain[0]["tautan_menarik"] == ["/api/harga/kabupaten"]

"""Penjajakan sumber data: tidak boleh melempar galat, tidak mengarang data, dan hasilnya terbaca manusia."""

from __future__ import annotations

import json
from datetime import date

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
    assert set(tersimpan) == {"waktu", "pihps", "bapanas", "lain", "lanjutan"}


def test_probe_tahan_galat_jaringan_dan_halaman_bukan_json(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "JEDA", 0)
    gagal = lambda url, *a, **k: {"url": url, "status": 0, "jenis": "", "byte": 0, "detik": 1.0, "isi": b"", "galat": "URLError: tidak terjangkau"}
    hasil = p.jalankan(tmp_path, gagal)
    assert all(r["status"] == 0 and r["galat"] for k in ("pihps", "bapanas", "lain") for r in hasil[k])
    assert all(h["status"] != 200 for h in hasil["lanjutan"]["halaman"])
    html = b'<html><a href="/api/harga/kabupaten">x</a><a href="/tentang">y</a></html>'
    lain = p.penjajakan_lain(_palsu(html, jenis="text/html"))
    assert lain[0]["json"] is False and lain[0]["tautan_menarik"] == ["/api/harga/kabupaten"]


def test_jelajah_halaman_menemukan_alamat_api_di_skrip(monkeypatch):
    html = b'<html><script src="/app.js"></script></html>'
    js = b'$.get("/hargapangan/WebSite/TabelHarga/GetRefRegency?ref_prov_id=" + id); fetch("https://api.contoh.go.id/api/front/kota")'

    def palsu(url, *a, **k):
        isi = js if url.endswith("app.js") else html
        return {"url": url, "status": 200, "jenis": "text/html", "byte": len(isi), "detik": 0.1, "isi": isi}
    monkeypatch.setattr(p, "JEDA", 0)
    h = p.jelajah_halaman("https://situs.contoh/halaman", palsu)
    assert any("GetRefRegency" in e for e in h["endpoint"]) and any("api.contoh.go.id" in e for e in h["endpoint"])
    assert h["skrip"][0]["url"] == "https://situs.contoh/app.js"


def test_nama_dari_json_membaca_daftar_wilayah():
    isi = json.dumps({"data": [{"id": 1, "text": "Kota Bengkulu"}, {"id": 2, "text": "Kepahiang"}]})
    assert p.nama_dari_json(isi) == ["Kota Bengkulu", "Kepahiang"]
    assert p.nama_dari_json("bukan json") == []


def test_kabupaten_pihps_memakai_nama_parameter_dari_halaman(monkeypatch):
    monkeypatch.setattr(p, "JEDA", 0)
    dipanggil = []

    def palsu(url, *a, **k):
        dipanggil.append(url)
        if "GetRefRegency" in url and "price_type_id=1" in url and "ref_prov_id=7" in url:
            isi = json.dumps({"data": [{"id": 71, "name": "Kota Bengkulu"}]})
        elif "GetRefMarket" in url and "ref_regency_id=71" in url:
            isi = json.dumps({"data": [{"id": 5, "name": "Pasar Panorama"}]})
        elif "GetGridDataDaerah" in url and "regency_id=71" in url:
            isi = json.dumps({"data": [{"level": 2, "name": "Beras Kualitas Medium I", "05/10/2026": "16,000", "06/10/2026": "-"}]})
        else:
            isi = json.dumps({"data": []})
        return {"url": url, "status": 200, "jenis": "application/json", "byte": len(isi), "detik": 0.1, "isi": isi.encode()}
    h = p.coba_kabupaten_pihps(palsu, hari=date(2026, 10, 10))
    assert h["kabupaten"] == [{"jenis_pasar": 1, "id": 71, "nama": "Kota Bengkulu", "pasar": [{"id": 5, "nama": "Pasar Panorama"}]}]
    assert h["tabel"][0]["kabupaten"] == "Kota Bengkulu" and h["tabel"][0]["varian"] == 1 and h["tabel"][0]["terisi"] == 1

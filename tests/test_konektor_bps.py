import json

from pipeline import firestore_sinkron as fs
from pipeline import konektor_bps as bps

KUNCI = "kunci-rahasia-123abc"


def _jawab(status, isi, jenis="application/json"):
    data = isi if isinstance(isi, bytes) else json.dumps(isi).encode()
    return {"url": "", "status": status, "jenis": jenis, "byte": len(data), "detik": 0.1, "isi": data, "tajuk": {}}


def _daftar(isi, halaman=1, total_halaman=1):
    return {"status": "OK", "data-availability": "available",
            "data": [{"page": halaman, "pages": total_halaman, "total": len(isi)}, isi]}


def bps_tiruan(url, *_):
    """BPS tiruan: kunci sah, beberapa variabel dan tabel, dan angka untuk satu variabel."""
    assert f"/key/{KUNCI}/" in url
    if "/domain/type/kabbyprov/prov/17/" in url:
        return _jawab(200, _daftar([{"domain_id": "1709", "domain_name": "Bengkulu Tengah"},
                                    {"domain_id": "1771", "domain_name": "Kota Bengkulu"}]))
    if "/model/var/" in url and "/domain/1771/" in url and "/keyword/inflasi/" in url:
        return _jawab(200, _daftar([{"var_id": 1, "title": "Inflasi Bulanan Kota Bengkulu", "sub_name": "Inflasi", "unit": "Persen"}]))
    if "/model/var/" in url and "/domain/1709/" in url and "/keyword/harga/" in url:
        if "/page/1/" in url:
            return _jawab(200, _daftar([{"var_id": 7, "title": "Harga Eceran Beras", "sub_name": "Harga", "unit": "Rp/kg"}], 1, 2))
        return _jawab(200, _daftar([{"var_id": 8, "title": "Harga Produsen Gabah", "sub_name": "Harga", "unit": "Rp/kg"},
                                    {"var_id": 7, "title": "Harga Eceran Beras", "sub_name": "Harga", "unit": "Rp/kg"}], 2, 2))
    if "/model/var/" in url and "/domain/1700/" in url and "/keyword/beras/" in url:  # kata kunci diabaikan BPS
        return _jawab(200, _daftar([{"var_id": 90, "title": "Jumlah Penduduk", "sub_name": "Kependudukan"}]))
    if "/model/statictable/" in url and "/domain/1709/" in url and "/keyword/harga/" in url:
        return _jawab(200, _daftar([{"table_id": 55, "title": "Rata-rata Harga Eceran Bahan Pokok", "updt_date": "2026-03-01"}]))
    if "/model/data/" in url and "/var/1/" in url:
        return _jawab(200, {"status": "OK", "data-availability": "available", "tahun": [{"val": 125, "label": "2025"}],
                            "datacontent": {"177110125101": 0.21, "177110125102": 0.35}})
    if "/model/data/" in url:
        return _jawab(200, {"status": "OK", "data-availability": "list-not-available", "datacontent": {}})
    return _jawab(200, {"status": "OK", "data-availability": "list-not-available", "data": ""})


def test_kunci_sah_memetakan_variabel_tabel_dan_contoh_angka():
    h = bps.cek(KUNCI, ambil_fn=bps_tiruan, tidur=lambda _: None)
    assert h["kunci_sah"] is True and h["kunci"] == "ada"
    assert {d["id"] for d in h["domain_bengkulu"]} == {"1709", "1771"}
    assert sorted(v["var_id"] for v in h["variabel"] if v["wilayah"] == "1709") == [7, 8]  # dua halaman, tanpa ganda
    assert all(v["var_id"] != 90 for v in h["variabel"])  # judul tanpa kata yang dicari tidak ikut
    assert h["wilayah"]["1709"] == {"nama": "Kabupaten Bengkulu Tengah", "variabel": 2, "tabel_statis": 1}
    assert h["contoh_data"][0]["judul"] == "Inflasi Bulanan Kota Bengkulu"  # inflasi diambil contohnya lebih dulu
    assert h["contoh_data"][0]["bisa_diambil"] and h["contoh_data"][0]["jumlah_angka"] == 2
    assert any(not c["bisa_diambil"] for c in h["contoh_data"])
    assert "Kunci diterima BPS" in h["pesan"] and "3 variabel dan 1 tabel" in h["pesan"]
    assert KUNCI not in json.dumps(h)


def test_kunci_ditolak_pesannya_disamarkan():
    tolak = lambda url, *_: _jawab(200, {"status": "Error", "message": f"Key {KUNCI} tidak terdaftar"})
    h = bps.cek(KUNCI, ambil_fn=tolak, tidur=lambda _: None)
    assert h["kunci_sah"] is False and "tidak terdaftar" in h["pesan"]
    assert KUNCI not in json.dumps(h)
    galat_http = lambda url, *_: _jawab(403, {"message": f"forbidden for {url}"})
    h = bps.cek(KUNCI, ambil_fn=galat_http, tidur=lambda _: None)
    assert h["kunci_sah"] is False and "HTTP 403" in h["pesan"] and KUNCI not in json.dumps(h)


def test_halaman_pelindung_situs_dan_kunci_kosong():
    waf = lambda url, *_: _jawab(200, b"<!doctype html><title>Perimeter WAF Block</title>", "text/html")
    h = bps.cek(KUNCI, ambil_fn=waf, tidur=lambda _: None)
    assert h["kunci_sah"] is False and "halaman web" in h["pesan"]
    kosong = bps.cek("  ", ambil_fn=lambda *_: (_ for _ in ()).throw(AssertionError("tidak boleh memanggil BPS")))
    assert kosong["kunci"] == "belum" and kosong["kunci_sah"] is None and "Pengaturan" in kosong["pesan"]


def test_cek_bps_cli_menyimpan_hasil_tanpa_kunci(tmp_path, monkeypatch, capsys):
    from pipeline import __main__ as m

    monkeypatch.setenv("BPS_API_KEY", KUNCI)
    monkeypatch.setattr(fs, "pasang_rahasia_dari_firestore", lambda akar: ["BPS_API_KEY"])
    asli = bps.cek
    monkeypatch.setattr(bps, "cek", lambda kunci: {**asli(kunci, ambil_fn=bps_tiruan, tidur=lambda _: None),
                                                    "galat": [f"contoh galat dengan {kunci}"]})
    assert m._cek_bps(tmp_path) == 0
    keluaran = capsys.readouterr().out
    assert "Kunci BPS: dari Pengaturan situs" in keluaran and "Kunci diterima BPS" in keluaran
    assert KUNCI not in keluaran
    tersimpan = (tmp_path / bps.BERKAS).read_text(encoding="utf-8")
    assert json.loads(tersimpan)["asal_kunci"] == "situs"


def test_kunci_dari_situs_disamarkan_di_log_github_actions(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    env = {}
    assert fs.terapkan_rahasia({"BPS_API_KEY": f" {KUNCI} ", "KOSONG": "  ", "SMTP_PORT": "587"}, env) == ["BPS_API_KEY", "SMTP_PORT"]
    assert capsys.readouterr().out.strip() == f"::add-mask::{KUNCI}"  # port pendek tidak disamarkan
    monkeypatch.delenv("GITHUB_ACTIONS")
    fs.terapkan_rahasia({"BPS_API_KEY": KUNCI}, env)
    assert capsys.readouterr().out == ""


def test_status_finder_bps_mengikuti_hasil_cek(tmp_path, monkeypatch):
    from pipeline import tata_data

    monkeypatch.delenv("BPS_API_KEY", raising=False)
    f = tata_data.finder_bps(tmp_path)
    assert "belum dipasang" in f["alasan"] and f["gerbang"][1]["lolos"] is None
    monkeypatch.setenv("BPS_API_KEY", KUNCI)
    assert "belum dicek" in tata_data.finder_bps(tmp_path)["alasan"]
    bps.simpan(tmp_path, {"waktu": "2026-10-21T03:00:00+00:00", "kunci_sah": False, "pesan": "Kunci belum bisa dipakai: Invalid key"})
    f = tata_data.finder_bps(tmp_path)
    assert "ditolak BPS saat dicek 2026-10-21: Kunci belum bisa dipakai: Invalid key" in f["alasan"] and f["gerbang"][1]["lolos"] is False
    bps.simpan(tmp_path, bps.cek(KUNCI, ambil_fn=bps_tiruan, tidur=lambda _: None, sekarang=None))
    f = tata_data.finder_bps(tmp_path)
    assert "Kunci diterima BPS" in f["alasan"] and "3 variabel dan 1 tabel" in f["alasan"] and f["gerbang"][1]["lolos"] is True

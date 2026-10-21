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
                                    {"var_id": 7, "title": "Harga Eceran Beras", "sub_name": "Harga", "unit": "Rp/kg"},
                                    {"var_id": 9, "title": "PDRB Atas Dasar Harga Berlaku", "sub_name": "PDRB"}], 2, 2))
    if "/model/var/" in url and "/domain/1700/" in url and "/keyword/beras/" in url:  # kata kunci diabaikan BPS
        return _jawab(200, _daftar([{"var_id": 90, "title": "Jumlah Penduduk", "sub_name": "Kependudukan"}]))
    if "/model/statictable/" in url and "/domain/1709/" in url and "/keyword/harga/" in url:
        return _jawab(200, _daftar([{"table_id": 55, "title": "Rata-rata Harga Eceran Bahan Pokok", "updt_date": "2026-03-01"}]))
    if "/model/th/" in url and "/var/1/" in url:
        return _jawab(200, _daftar([{"th_id": 124, "th": "2024"}, {"th_id": 125, "th": "2025"}, {"th_id": 126, "th": "2026"}]))
    if "/model/data/" in url and "/var/1/" in url:
        assert "/th/125;126/" in url  # dua tahun terakhir
        isi = {f"1771{1}0{th}{bl}": nilai for th, bl, nilai in ((125, 9, 0.1), (126, 8, 0.35), (126, 9, 0.21))}
        return _jawab(200, {"status": "OK", "data-availability": "available",
                            "vervar": [{"val": 1771, "label": "Kota Bengkulu"}], "turvar": [{"val": 0, "label": "Tidak Ada"}],
                            "tahun": [{"val": 125, "label": "2025"}, {"val": 126, "label": "2026"}],
                            "turtahun": [{"val": 8, "label": "Agustus"}, {"val": 9, "label": "September"}], "datacontent": isi})
    if "/model/data/" in url:
        return _jawab(200, {"status": "OK", "data-availability": "list-not-available", "datacontent": {}})
    return _jawab(200, {"status": "OK", "data-availability": "list-not-available", "data": ""})


def test_kunci_sah_memetakan_variabel_tabel_dan_contoh_angka():
    h = bps.cek(KUNCI, ambil_fn=bps_tiruan, tidur=lambda _: None)
    assert h["kunci_sah"] is True and h["kunci"] == "ada"
    assert {d["id"] for d in h["domain_bengkulu"]} == {"1709", "1771"}
    assert sorted(v["var_id"] for v in h["variabel"] if v["wilayah"] == "1709") == [7, 8]  # dua halaman, tanpa ganda
    assert all(v["var_id"] not in (90, 9) for v in h["variabel"])  # judul tanpa kata yang dicari dan PDRB tidak ikut
    assert h["wilayah"]["1709"] == {"nama": "Kabupaten Bengkulu Tengah", "variabel": 2, "tabel_statis": 1}
    assert h["contoh_data"][0]["judul"] == "Inflasi Bulanan Kota Bengkulu"  # inflasi diambil contohnya lebih dulu
    c = h["contoh_data"][0]
    assert c["bisa_diambil"] and c["jumlah_angka"] == 3 and c["terbaru"] == "September 2026"
    assert c["contoh"] == [{"rincian": "Kota Bengkulu", "turunan": "Tidak Ada", "tahun": "2026", "periode": "September", "nilai": 0.21}]
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
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert m._cek_bps(tmp_path) == 0
    keluaran = capsys.readouterr().out
    assert "Kunci BPS: dari Pengaturan situs" in keluaran and "Kunci diterima BPS" in keluaran
    assert KUNCI not in keluaran
    # Di GitHub Actions kunci hanya muncul di baris ::add-mask::, perintah ke runner yang tidak ikut tampil di log.
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert m._cek_bps(tmp_path) == 0
    baris_berkunci = [b for b in capsys.readouterr().out.splitlines() if KUNCI in b]
    assert baris_berkunci == [f"::add-mask::{KUNCI}"]
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


# ---------------------------------------------------------------- deret inflasi untuk dashboard

BULAN_UJI = {4: "April", 5: "Mei"}


def _data_bulanan(var_id, rincian, nilai_per_bulan, th=(125, "2025"), th2=(126, "2026"), turvar=("0", "Tidak ada")):
    """Jawaban data BPS bentuk baru: rincian di vervar, bulan di turtahun. nilai_per_bulan: {(th_id, bulan): {rincian: nilai}}."""
    isi = {}
    for (th_id, bl), per in nilai_per_bulan.items():
        for kode, nilai in per.items():
            isi[f"{kode}{var_id}{turvar[0]}{th_id}{bl}"] = nilai
    return {"status": "OK", "data-availability": "available",
            "var": [{"val": var_id, "label": f"Judul BPS {var_id}", "unit": "Persen"}],
            "vervar": [{"val": k, "label": v} for k, v in rincian.items()], "turvar": [{"val": turvar[0], "label": turvar[1]}],
            "tahun": [{"val": th[0], "label": th[1]}, {"val": th2[0], "label": th2[1]}],
            "turtahun": [{"val": b, "label": n} for b, n in BULAN_UJI.items()] + [{"val": 13, "label": "Tahunan"}],
            "datacontent": isi}


KELOMPOK = {1: "Umum", 2: "Makanan, Minuman, dan Tembakau"}
NILAI_SERI = {
    555: {(126, 4): {1: 0.12, 2: 0.4}, (126, 5): {1: 0.86, 2: 1.85}},
    556: {(126, 4): {1: 0.53, 2: -0.65}, (126, 5): {1: 1.39, 2: 1.19}},
    557: {(125, 5): {1: 1.5, 2: 2.0}, (126, 4): {1: 2.7, 2: 5.1}, (126, 5): {1: 3.01, 2: 6.07}},
}


def bps_seri_tiruan(url, *_):
    assert f"/key/{KUNCI}/" in url
    if "/model/th/" in url:
        if "/var/422/" in url:
            return _jawab(200, _daftar([]))  # variabel tanpa daftar tahun
        # th_id 127 berlabel 2024: urutan tahun dari labelnya, bukan dari nomor th_id
        return _jawab(200, _daftar([{"th_id": 127, "th": "2024"}, {"th_id": 125, "th": "2025"}, {"th_id": 126, "th": "2026"}]))
    if "/model/data/" in url:
        assert "/th/127;125;126/" in url
        var_id = int(url.split("/var/")[1].split("/")[0])
        if var_id in NILAI_SERI:
            return _jawab(200, _data_bulanan(var_id, KELOMPOK, NILAI_SERI[var_id]))
        if var_id in (559, 560):
            wil = {1771: "Kota Bengkulu", 1706: "Mukomuko", 1700: "Provinsi Bengkulu"}
            n = {(126, 5): {1771: 0.9 if var_id == 559 else 3.2, 1706: 0.5 if var_id == 559 else 2.1, 1700: 0.86 if var_id == 559 else 3.01}}
            return _jawab(200, _data_bulanan(var_id, wil, n))
        if var_id == 421:  # bentuk lama: bulan di vervar, kategori di turvar
            return _jawab(200, {"status": "OK", "var": [{"val": 421, "label": "It", "unit": ""}],
                                "vervar": [{"val": 5, "label": "Mei"}], "turvar": [{"val": 7, "label": "Gabungan"}],
                                "tahun": [{"val": 126, "label": "2026"}], "turtahun": [{"val": 0, "label": "Tahunan"}],
                                "datacontent": {"54217126" + "0": 150.0, "54217126" + "9": "-"}})
    raise AssertionError(url)


def test_ambil_seri_inflasi_dan_ringkasannya_untuk_situs():
    h = bps.ambil_seri(KUNCI, ambil_fn=bps_seri_tiruan, tidur=lambda _: None)
    assert KUNCI not in json.dumps(h)
    assert set(h["seri"]) == {"mtm", "ytd", "yoy", "mtm_wilayah", "yoy_wilayah", "it"}
    assert any("var 422" in g and "tahun" in g for g in h["galat"])
    yoy = h["seri"]["yoy"]
    assert yoy["satuan"] == "Persen" and yoy["terbaru"] == "2026-05" and yoy["judul_bps"] == "Judul BPS 557"
    assert {"periode": "2025-05", "kategori": "Umum", "nilai": 1.5} in yoy["data"]
    assert all(x["periode"][5:] in ("04", "05") for x in yoy["data"])  # baris "Tahunan" tidak ikut
    assert h["seri"]["it"]["data"] == [{"periode": "2026-05", "kategori": "Gabungan", "nilai": 150.0}]
    assert "6 dari 7 deret" in h["pesan"] and "2026-05" in h["pesan"]

    r = bps.ringkas_untuk_situs(h)
    assert r["periode"] == "2026-05" and r["wilayah"] == "Provinsi Bengkulu"
    assert r["umum"] == {"nama": "Umum", "mtm": 0.86, "ytd": 1.39, "yoy": 3.01}
    assert r["makanan"]["yoy"] == 6.07
    assert r["wilayah_ihk"]["periode"] == "2026-05"
    assert {"nama": "Mukomuko", "mtm": 0.5, "yoy": 2.1} in r["wilayah_ihk"]["daftar"]
    assert [t["periode"] for t in r["tren"]] == ["2025-05", "2026-04", "2026-05"]
    assert r["tren"][-1] == {"periode": "2026-05", "mtm": 0.86, "yoy": 3.01, "yoy_makanan": 6.07}
    assert r["ntp"] is None  # Ib tidak terambil, jadi NTP tidak dihitung
    assert bps.ringkas_untuk_situs(None) is None and bps.ringkas_untuk_situs({"seri": {}}) is None


def test_ambil_seri_berhenti_bila_permintaan_pertama_ditolak():
    panggil = []

    def tolak(url, *_):
        panggil.append(url)
        return _jawab(200, {"status": "Error", "message": f"Invalid key {KUNCI}"})

    h = bps.ambil_seri(KUNCI, ambil_fn=tolak, tidur=lambda _: None)
    assert len(panggil) == 1 and not h["seri"] and "Invalid key ***" in h["galat"][0]
    assert "belum bisa diambil" in h["pesan"] and KUNCI not in json.dumps(h)
    assert bps.ambil_seri(" ", ambil_fn=tolak)["pesan"].startswith("Kunci BPS_API_KEY belum diisi")


def test_gabung_seri_mempertahankan_deret_yang_gagal_kali_ini():
    lama = {"waktu": "2026-10-01T00:00:00+00:00", "seri": {"yoy": {"terbaru": "2026-04"}, "it": {"terbaru": "2026-03"}}}
    baru = {"waktu": "2026-10-21T00:00:00+00:00", "seri": {"mtm": {"terbaru": "2026-05"}, "yoy": {"terbaru": "2026-05"}}, "galat": ["it"]}
    g = bps.gabung_seri(lama, baru)
    assert g["waktu"] == baru["waktu"] and list(g["seri"]) == ["mtm", "yoy", "it"]
    assert g["seri"]["yoy"]["terbaru"] == "2026-05" and g["seri"]["it"]["terbaru"] == "2026-03"


def test_ntp_dihitung_dari_it_dan_ib_bulan_yang_sama():
    seri = {"mtm": {"data": [{"periode": "2026-05", "kategori": "Umum", "nilai": 0.5}]},
            "it": {"data": [{"periode": "2026-05", "kategori": "Tanaman Pangan", "nilai": 120.0},
                            {"periode": "2026-05", "kategori": "Gabungan", "nilai": 150.0}]},
            "ib": {"data": [{"periode": "2026-05", "kategori": "Tanaman Pangan", "nilai": 100.0},
                            {"periode": "2026-05", "kategori": "Gabungan", "nilai": 120.0},
                            {"periode": "2026-06", "kategori": "Gabungan", "nilai": 121.0}]}}
    n = bps.ringkas_untuk_situs({"seri": seri})["ntp"]
    assert n["periode"] == "2026-05" and n["utama"] == "Gabungan"
    assert {"nama": "Gabungan", "it": 150.0, "ib": 120.0, "ntp": 125.0} in n["subsektor"]


def test_ambil_bps_cli_melewati_bila_masih_baru_dan_tidak_menimpa_dengan_hasil_kosong(tmp_path, monkeypatch, capsys):
    from datetime import datetime, timezone

    from pipeline import __main__ as m

    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("BPS_API_KEY", KUNCI)
    monkeypatch.setattr(fs, "pasang_satu_rahasia", lambda akar, nama: True)
    asli = bps.ambil_seri
    monkeypatch.setattr(bps, "ambil_seri", lambda kunci: asli(kunci, ambil_fn=bps_seri_tiruan, tidur=lambda _: None))
    assert m._ambil_bps(tmp_path) == 0
    out = capsys.readouterr().out
    assert "dari Pengaturan situs" in out and "yoy:" in out and "Makanan, Minuman, dan Tembakau" in out and KUNCI not in out
    tersimpan = bps.baca(tmp_path, bps.BERKAS_SERI)
    assert tersimpan["seri"]["yoy"]["terbaru"] == "2026-05"

    # hasil masih baru: tidak membaca kunci dan tidak memanggil BPS
    monkeypatch.setattr(fs, "pasang_satu_rahasia", lambda *a: (_ for _ in ()).throw(AssertionError("tidak boleh membaca kunci")))
    assert m._ambil_bps(tmp_path) == 0 and "belum perlu diambil lagi" in capsys.readouterr().out

    # dipaksa tetapi BPS menolak: berkas lama tetap utuh
    monkeypatch.setattr(fs, "pasang_satu_rahasia", lambda akar, nama: False)
    monkeypatch.setattr(bps, "ambil_seri", lambda kunci: {"seri": {}, "galat": ["ditolak"], "pesan": "Deret BPS belum bisa diambil: ditolak"})
    assert m._ambil_bps(tmp_path, paksa=True) == 1
    assert bps.baca(tmp_path, bps.BERKAS_SERI)["seri"]["yoy"]["terbaru"] == "2026-05"
    assert datetime.fromisoformat(tersimpan["waktu"]) <= datetime.now(timezone.utc)

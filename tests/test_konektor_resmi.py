"""Konektor BMKG dan PIHPS (bentuk jawaban diambil dari jawaban asli kedua layanan, Oktober 2026)."""

from __future__ import annotations

import csv
from datetime import date

from pipeline import konektor_resmi, masukan, sinyal

BMKG = {"lokasi": {"adm4": "17.09.01.2001", "desa": "Taba Terunjam"}, "data": [{"cuaca": [
    [{"local_datetime": "2026-10-02 17:00:00", "t": 25, "tp": 2.7}, {"local_datetime": "2026-10-02 20:00:00", "t": 24, "tp": 3}],
    [{"local_datetime": "2026-10-03 08:00:00", "t": 27, "tp": 30.5}, {"local_datetime": "2026-10-03 11:00:00", "t": 29, "tp": 40}],
]}]}

PIHPS = {"data": [
    {"no": "I", "name": "Beras", "level": 1, "29/09/2026": "15,950"},
    {"no": 1, "name": "Beras Kualitas Bawah I", "level": 2, "29/09/2026": "15,700", "30/09/2026": "15,750"},
    {"no": 1, "name": "Daging Sapi Kualitas 1", "level": 2, "29/09/2026": "140,000", "30/09/2026": "-"},
    {"no": 1, "name": "Minyak Goreng Kemasan Bermerk 2", "level": 2, "29/09/2026": "21,000"},
    {"no": 1, "name": "Bawang Putih Ukuran Sedang", "level": 2, "29/09/2026": "38,500"},
    {"no": 1, "name": "Komoditas Baru", "level": 2, "29/09/2026": "1,000"},
]}


def test_bmkg_dijumlah_per_hari():
    b = konektor_resmi.ubah_bmkg(BMKG, "1709")
    hujan = {x["tanggal"]: x["nilai"] for x in b if x["indikator"] == "prakiraan_hujan_mm"}
    suhu = {x["tanggal"]: x["nilai"] for x in b if x["indikator"] == "prakiraan_suhu_c"}
    assert hujan == {"2026-10-02": 5.7, "2026-10-03": 70.5}
    assert suhu == {"2026-10-02": 24.5, "2026-10-03": 28.0}
    assert all(x["kode_sumber"] == "BD-BMKG" for x in b)


def test_pihps_nama_varian_dipetakan_dan_angka_dibaca(konf):
    b, tak = konektor_resmi.ubah_pihps(PIHPS, konektor_resmi.peta_varian(konf))
    nilai = {(x["kode_varian"], x["tanggal"]): x["nilai"] for x in b}
    assert nilai == {("BRS01", "2026-09-29"): 15700.0, ("BRS01", "2026-09-30"): 15750.0, ("DSP01", "2026-09-29"): 140000.0,
                     ("MGR03", "2026-09-29"): 21000.0, ("BWP01", "2026-09-29"): 38500.0}
    assert tak == ["Komoditas Baru"]
    assert all(x["kode_wilayah"] == "17" for x in b)


def test_semua_varian_pihps_dikenali(konf):
    """Nama di pohon komoditas PIHPS harus cocok dengan daftar varian sistem."""
    nama = ["Beras Kualitas Bawah I", "Beras Kualitas Bawah II", "Beras Kualitas Medium I", "Beras Kualitas Medium II",
            "Beras Kualitas Super I", "Beras Kualitas Super II", "Daging Ayam Ras Segar", "Daging Sapi Kualitas 1",
            "Daging Sapi Kualitas 2", "Telur Ayam Ras Segar", "Bawang Merah Ukuran Sedang", "Bawang Putih Ukuran Sedang",
            "Cabai Merah Besar", "Cabai Merah Keriting", "Cabai Rawit Hijau", "Cabai Rawit Merah", "Minyak Goreng Curah",
            "Minyak Goreng Kemasan Bermerk 1", "Minyak Goreng Kemasan Bermerk 2", "Gula Pasir Kualitas Premium", "Gula Pasir Lokal"]
    peta = konektor_resmi.peta_varian(konf)
    assert [n for n in nama if konektor_resmi._normal(n) not in peta] == []


def test_perbarui_menulis_konteks_yang_terbaca_pipeline(konf):
    panggil = []

    def pengambil(url):
        panggil.append(url)
        return BMKG if "bmkg" in url else PIHPS

    h = konektor_resmi.perbarui(konf, pengambil=pengambil, tidur=lambda s: None)
    assert h["bmkg"]["galat"] == [] and h["pihps"]["galat"] == []
    assert sum("GetGridDataDaerah" in u for u in panggil) == 5  # riwayat 400 hari, per 90 hari
    assert any("adm4=17.09.01.2001" in u for u in panggil)
    folder = konf.akar / "data/masuk/konteks"
    assert (folder / "harga_pihps_2026.csv").exists() and (folder / "prakiraan_bmkg_2026.csv").exists()
    hasil = masukan.baca_semua(konf.akar / "data/masuk", konf, akar_relatif=konf.akar)
    assert not hasil.penolakan
    assert {k.kode_sumber for k in hasil.konteks} == {"BD-BMKG", "BD-PIHPS"}

    # Jalan kedua: hanya 45 hari terakhir, tanpa baris ganda.
    panggil.clear()
    h2 = konektor_resmi.perbarui(konf, pengambil=pengambil, tidur=lambda s: None)
    assert sum("GetGridDataDaerah" in u for u in panggil) == 1 and h2["pihps"]["baris_baru"] == 0
    with (folder / "harga_pihps_2026.csv").open() as f:
        assert len(list(csv.DictReader(f))) == 5


def test_konteks_sinyal_menyebut_pihps(konf):
    from pipeline.masukan import ObservasiKonteks
    indeks = sinyal.IndeksKonteks([ObservasiKonteks(tanggal=date(2026, 9, 29), kode_wilayah="17", indikator="harga_pihps",
                                                    nilai=50000, satuan="Rp", kode_varian="CRW02", kode_sumber="BD-PIHPS",
                                                    berkas="x")])
    k, kalimat = sinyal.konteks_sinyal(konf, date(2026, 9, 30), "CRW02", 60000, indeks, {})
    assert k["pihps_provinsi"] == {"tanggal": "2026-09-29", "harga": 50000, "selisih_persen": 20.0}
    assert "PIHPS Bank Indonesia" in kalimat and "+20%" in kalimat


def test_kunci_nama_membuang_jenis_wilayah():
    k = konektor_resmi._kunci_nama
    assert k("Kota Bengkulu") == "bengkulu" and k("Kab. Bengkulu Tengah") == "bengkulu tengah" and k("Kabupaten Kepahiang") == "kepahiang"
    assert k("Kota Bengkulu") != k("Kabupaten Bengkulu Utara")


def test_pihps_kota_hanya_mengisi_wilayah_yang_ada_di_pihps(konf):
    daftar = {"data": [{"id": 71, "name": "Kota Bengkulu"}, {"id": 72, "name": "Kabupaten Bengkulu Utara"}]}
    panggil = []

    def pengambil(url):
        panggil.append(url)
        if "GetRefRegency" in url:
            assert "ref_prov_id=7" in url
            # pasar tradisional (1) dan pedagang besar (3) punya Kota Bengkulu; pasar modern (2) dan produsen (4) kosong
            return daftar if ("price_type_id=1" in url or "price_type_id=3" in url) else {"data": []}
        assert "regency_id=71" in url  # hanya Kota Bengkulu yang cocok dengan wilayah sistem
        return PIHPS

    h = konektor_resmi.perbarui_pihps_kota(konf, pengambil=pengambil, tidur=lambda s: None)
    assert list(h["wilayah"]) == ["1771", "1771:harga_pihps_grosir"] and h["wilayah"]["1771"]["id"] == 71 and h["galat"] == []
    assert sorted(h["tidak_ditemukan"]) == ["Kabupaten Bengkulu Tengah", "Kabupaten Kepahiang"]
    folder = konf.akar / "data/masuk/konteks"
    with (folder / "pihps_kota_2026.csv").open() as f:
        baris = list(csv.DictReader(f))
    assert baris and {b["kode_wilayah"] for b in baris} == {"1771"} and {b["kode_sumber"] for b in baris} == {"BD-PIHPS"}
    assert {b["indikator"] for b in baris} == {"harga_pihps", "harga_pihps_grosir"}  # jenis pasar dibedakan lewat indikator
    # tidak boleh bocor ke harga utama sementara (provinsi)
    from pipeline import pihps_harga
    assert pihps_harga._baca_konteks(folder) == {}
    hasil = masukan.baca_semua(konf.akar / "data/masuk", konf, akar_relatif=konf.akar)
    assert not hasil.penolakan and any(k.kode_wilayah == "1771" for k in hasil.konteks)


def test_pihps_kota_tahan_galat_daftar_kabupaten(konf):
    def gagal(url):
        raise OSError("tidak terjangkau")

    h = konektor_resmi.perbarui_pihps_kota(konf, pengambil=gagal, tidur=lambda s: None)
    assert h["wilayah"] == {} and h["baris_baru"] == 0 and all("daftar kabupaten PIHPS" in g for g in h["galat"]) and len(h["galat"]) == 4

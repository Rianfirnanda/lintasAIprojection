from datetime import date

import pytest
from openpyxl import Workbook

from pipeline import masukan
from tests.conftest import tulis_csv


@pytest.mark.parametrize("mentah,harapan", [
    ("45000", 45000), ("45.000", 45000), ("Rp 45.000", 45000), ("1.250.000", 1250000),
    ("12.500,50", 12500.5), ("45,000", 45000), ("12,5", 12.5), (45000, 45000), (12500.0, 12500),
])
def test_parse_harga_format_indonesia(mentah, harapan):
    assert masukan.parse_harga(mentah) == pytest.approx(harapan)


@pytest.mark.parametrize("mentah", ["", "abc", "0", "-5"])
def test_parse_harga_menolak_nilai_tidak_sah(mentah):
    with pytest.raises(ValueError):
        masukan.parse_harga(mentah)


@pytest.mark.parametrize("mentah", ["2026-09-28", "28/09/2026", "28-09-2026", "28.09.2026", date(2026, 9, 28), 46293])
def test_parse_tanggal(mentah):
    assert masukan.parse_tanggal(mentah) == date(2026, 9, 28)


def test_faktor_konversi():
    assert masukan.faktor_konversi("ons", "kg") == 10
    assert masukan.faktor_konversi("KG", "kg") == 1
    assert masukan.faktor_konversi("", "kg") == 1
    with pytest.raises(ValueError):
        masukan.faktor_konversi("butir", "kg")


def test_baca_harga_alias_konversi_dan_penolakan(konf, akar_sementara):
    tulis_csv(akar_sementara / "data/masuk/harga/uji.csv", """
Tanggal;Pasar;Varian;Harga;Satuan;Petugas
28/09/2026;PSR01;CRW02;Rp 45.000;kg;PTG01
28/09/2026;psr02;crw02;4.600;ons;PTG02
28/09/2026;PSR99;CRW02;45000;kg;PTG01
28/09/2026;PSR01;XXX01;45000;kg;PTG01
30/09/2026;PSR01;CRW02;45000;kg;PTG01
28/09/2026;PSR01;CRW02;;kg;PTG01
28/09/2026;PSR01;CRW02;45000;butir;PTG01
""")
    hasil = masukan.baca_semua(akar_sementara / "data/masuk", konf, akar_sementara)
    assert [o.harga for o in hasil.observasi] == [45000, 46000]
    assert hasil.observasi[1].kode_pasar == "PSR02" and hasil.observasi[1].satuan_asli == "ons"
    assert hasil.observasi[0].kode_sumber == "PSR-ENUM"
    alasan = [p.alasan for p in hasil.penolakan]
    assert any("kode_pasar tidak dikenal" in a for a in alasan)
    assert any("kode_varian tidak dikenal" in a for a in alasan)
    assert any("melewati hari ini" in a for a in alasan)
    assert any("harga kosong" in a for a in alasan)
    assert any("tidak dapat dikonversi" in a for a in alasan)
    b = hasil.batch[0]
    assert (b.jumlah_baris, b.diterima, b.ditolak) == (7, 2, 5)
    assert len(b.sha256) == 64 and b.berkas == "data/masuk/harga/uji.csv"


def test_berkas_dengan_data_pribadi_ditolak_utuh(konf, akar_sementara):
    tulis_csv(akar_sementara / "data/masuk/harga/pii.csv", """
tanggal,kode_pasar,kode_varian,harga,nama_pedagang,no_hp
2026-09-28,PSR01,CRW02,45000,Budi,0812
""")
    hasil = masukan.baca_semua(akar_sementara / "data/masuk", konf, akar_sementara)
    assert hasil.observasi == []
    assert "data pribadi" in hasil.batch[0].galat_berkas
    assert hasil.batch[0].ditolak == 1


def test_kolom_wajib_hilang(konf, akar_sementara):
    tulis_csv(akar_sementara / "data/masuk/harga/kurang.csv", "tanggal,kode_pasar,harga\n2026-09-28,PSR01,45000")
    hasil = masukan.baca_semua(akar_sementara / "data/masuk", konf, akar_sementara)
    assert "kode_varian" in hasil.batch[0].galat_berkas


def test_baca_xlsx(konf, akar_sementara):
    wb = Workbook()
    ws = wb.active
    ws.append(["Tanggal", "Kode Pasar", "Kode Varian", "Harga"])
    ws.append([date(2026, 9, 28), "PSR01", "BRS03", 13500])
    ws.append([None, None, None, None])
    path = akar_sementara / "data/masuk/harga/uji.xlsx"
    wb.save(path)
    hasil = masukan.baca_semua(akar_sementara / "data/masuk", konf, akar_sementara)
    assert len(hasil.observasi) == 1
    assert hasil.observasi[0].tanggal == date(2026, 9, 28) and hasil.observasi[0].harga == 13500


def test_id_observasi_stabil_dan_berbeda():
    a = masukan.id_observasi("2026-09-28", "PSR01", "CRW02", "PSR-ENUM", "R1", 45000, "kg", "")
    b = masukan.id_observasi("2026-09-28", "PSR01", "CRW02", "PSR-ENUM", "R1", 45000, "kg", "")
    c = masukan.id_observasi("2026-09-28", "PSR01", "CRW02", "PSR-ENUM", "R2", 45000, "kg", "")
    assert a == b != c and len(a) == 12


def test_konteks(konf, akar_sementara):
    tulis_csv(akar_sementara / "data/masuk/konteks/stok.csv", """
tanggal,kode_wilayah,indikator,nilai,satuan,kode_varian,kode_sumber
2026-09-25,1709,Stok Beras (ton),850.5,ton,BRS03,PMD-DISDAG
2026-09-25,9999,stok_beras_ton,850,ton,,PMD-DISDAG
""")
    hasil = masukan.baca_semua(akar_sementara / "data/masuk", konf, akar_sementara)
    assert len(hasil.konteks) == 1 and hasil.konteks[0].indikator == "stok_beras_ton"
    assert len(hasil.penolakan) == 1

from datetime import date
from types import SimpleNamespace as NS

from pipeline.sumber_harian import rangkum


def test_harga_terakhir_per_sumber_dan_status_tidak_menyamarkan_data_beku(konf):
    def o(tanggal, harga, status):
        return NS(kode_sumber='BD-SP2KP', kode_pasar='PSR01', kode_wilayah='1709',
                  kode_varian='BRS01', tanggal=date.fromisoformat(tanggal), harga=harga, status=status)
    rows = rangkum(konf, [o('2026-09-28', 10000, 'lolos'), o('2026-09-29', 14000, 'beku'),
                         o('2026-09-29', 16000, 'lolos')], [])
    assert len(rows) == 1
    assert rows[0]['harga'] == 15000
    assert rows[0]['tanggal'] == date(2026, 9, 29)
    assert rows[0]['status'] == 'Ada data tidak dipakai'
    assert rows[0]['peran'] == 'Wilayah utama'


def test_pihps_konteks_pembanding_tidak_menggandakan_harga_provinsi(konf):
    obs = NS(kode_sumber='BD-PIHPS', kode_pasar='PHP17', kode_wilayah='17', kode_varian='BRS01',
             tanggal=date(2026, 9, 29), harga=15000, status='lolos')
    def k(wilayah):
        return NS(kode_sumber='BD-PIHPS', indikator='harga_pihps', kode_varian='BRS01',
                  kode_wilayah=wilayah, tanggal=date(2026, 9, 29), nilai=15000)
    rows = rangkum(konf, [obs], [k('17'), k('1771')])
    assert len(rows) == 2
    assert all(r['peran'] == 'Pembanding wilayah' for r in rows)
    assert {r['status'] for r in rows} == {'Lolos pemeriksaan', 'Data konteks pembanding'}
    assert rangkum(konf, [], []) == []


def test_hanya_sumber_harga_resmi_yang_ditampilkan(konf):
    obs = NS(kode_sumber='PSR-ENUM')
    assert rangkum(konf, [obs], []) == []


def test_riwayat_mempertahankan_harga_dan_status_tiap_tanggal(konf):
    def o(t, harga, status):
        return NS(kode_sumber='BD-SP2KP', kode_pasar='PSR01', kode_wilayah='1709', kode_varian='BRS01',
                  tanggal=date(2026, 9, t), harga=harga, status=status)
    data = [o(28, 10000, 'lolos'), o(29, 14000, 'beku'), o(29, 16000, 'lolos')]
    rows = rangkum(konf, data, [], riwayat=True)
    assert rows[0]['riwayat'] == [['2026-09-28', 10000, 'Lolos pemeriksaan'],
                                  ['2026-09-29', 15000, 'Ada data tidak dipakai']]
    assert rows[0]['harga'] == 15000

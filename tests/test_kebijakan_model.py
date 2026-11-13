from datetime import date, timedelta
from types import SimpleNamespace as NS
from pipeline import kebijakan_model

HARI = date(2026, 11, 13)


def obs(sumber, harga, n=70, wilayah='1709', akhir=HARI):
    return [NS(kode_varian='BRS03', kode_sumber=sumber, kode_wilayah=wilayah,
               tanggal=akhir-timedelta(days=i), harga=harga, status='lolos') for i in range(n)]


def test_training_memilih_satu_sumber_tanpa_menambal_dari_lapangan():
    data = obs('PSR-ENUM', 90000) + obs('BPS-HRG', 12000) + obs('BD-SP2KP', 15000)
    data += obs('PSR-ENUM', 20000, n=1, akhir=HARI-timedelta(days=80))
    harga, meta = kebijakan_model.pilih(data, 'BRS03', '1709', '17', HARI, kebijakan_model.muat())
    assert set(harga.values()) == {15000}
    assert len(harga) == 70
    assert meta['kode_sumber'] == 'BD-SP2KP' and not meta['cadangan']


def test_sumber_beku_tidak_digunakan_dan_pi_hps_cadangan_diberi_wilayah():
    data = obs('BD-SP2KP', 15000, akhir=HARI-timedelta(days=20)) + obs('BD-PIHPS', 16000, wilayah='17')
    harga, meta = kebijakan_model.pilih(data, 'BRS03', '1709', '17', HARI, kebijakan_model.muat())
    assert set(harga.values()) == {16000}
    assert meta['cadangan'] and meta['kode_wilayah']=='17' and meta['jenis_data']=='observasi_asli'


def test_keputusan_sumber_asof_tidak_membaca_data_masa_depan():
    data = obs('BD-PIHPS', 16000)
    tambahan = obs('BD-SP2KP', 100000, akhir=HARI+timedelta(days=100))
    assert kebijakan_model.pilih(data, 'BRS03', '1709', None, HARI, kebijakan_model.muat()) == kebijakan_model.pilih(data+tambahan, 'BRS03', '1709', None, HARI, kebijakan_model.muat())
    data[0].status = 'beku'
    harga, _ = kebijakan_model.pilih(data, 'BRS03', '1709', None, HARI, kebijakan_model.muat())
    assert HARI not in harga


def test_tanpa_sumber_resmi_model_ditahan_dan_data_lapangan_tetap_utuh():
    data=obs('PSR-ENUM', 15000)
    harga, meta=kebijakan_model.pilih(data,'BRS03','1709','17',HARI,kebijakan_model.muat())
    assert not harga and not meta['boleh_training'] and len(data)==70


def test_kebijakan_tidak_membolehkan_regional_menyisipkan_cuaca_yang_dinonaktifkan(tmp_path):
    import json
    import pytest
    p=tmp_path/'config';p.mkdir()
    (p/'kebijakan_model.json').write_text(json.dumps({'tahap_fitur':['kalender','regional']}))
    with pytest.raises(ValueError,match='urutan'):
        kebijakan_model.muat(tmp_path)


def test_fingerprint_mencakup_kebijakan_dan_kalender(konf):
    from pipeline import analitik
    from dataclasses import replace
    import json
    a=analitik.versi_konfigurasi(konf)
    p=konf.akar/'config/kebijakan_model.json'
    p.write_text(json.dumps({**kebijakan_model.muat(),'maks_umur_hari':5}))
    b=analitik.versi_konfigurasi(konf)
    assert a!=b
    konf.kalender.append(replace(konf.kalender[0],tanggal=date(2027,1,1)))
    assert b!=analitik.versi_konfigurasi(konf)

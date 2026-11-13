import copy
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pytest

from pipeline import analisis, trust_cabai, proses
from tests.conftest import tulis_csv


def aturan():
    return trust_cabai.muat()


def serie(n=900, end=date(2026, 11, 13)):
    days = [end-timedelta(days=n-1-i) for i in range(n)]
    return analisis.SeriHarian(days, np.full(n, 15000.))


def test_scope_dan_batas_tinggi_tidak_boleh_dilonggarkan(tmp_path):
    a = aturan()
    assert set(a['kode_varian']) == trust_cabai.KODE
    assert trust_cabai.cadangan_hari(a) == 450
    (tmp_path/'config').mkdir()
    a['data']['tinggi']['observasi_asli_min'] = 100
    (tmp_path/'config/trust_cabai.json').write_text(json.dumps(a))
    with pytest.raises(ValueError, match='data tinggi'):
        trust_cabai.muat(tmp_path)


def test_kelengkapan_menghitung_tanggal_kosong_dan_mengecualikan_hanya_libur_eksplisit():
    s = serie(900)
    s.nilai[-10:] = np.nan
    observed = int(np.isfinite(s.nilai).sum())
    a = trust_cabai.data_seri(s, s.tanggal[-1], [0,1,2,3,4], [])
    assert a['observasi_asli'] == observed
    assert a['kelengkapan_90'] < 100
    assert a['umur_hari_pencatatan'] > 2
    with_future = analisis.SeriHarian(s.tanggal+[s.tanggal[-1]+timedelta(days=1)], np.r_[s.nilai, 99999.])
    b = trust_cabai.data_seri(with_future, s.tanggal[-1], [0,1,2,3,4], [])
    assert a == b


def test_tingkat_memerlukan_seluruh_gerbang_dan_tidak_mengubah_persen_lama():
    yes = [trust_cabai.cek('gerbang', True)]
    assert trust_cabai.level_dari(yes, [trust_cabai.cek('prospektif', None)]) == 'sedang'
    assert trust_cabai.level_dari(yes, yes) == 'tinggi'
    assert trust_cabai.level_dari([trust_cabai.cek('sMAPE', False)], yes) == 'rendah'
    assert trust_cabai.level_dari([trust_cabai.cek('bukti', None)], yes) == 'belum_cukup_bukti'


def titik(i, actual=15000., pred=15000., lower=15000., upper=15000.):
    return {'origin': i, 'aktual': actual, 'prediksi': pred, 'naif': 15000.,
            'bawah': lower, 'atas': upper, 'bawah_naif': 15000., 'atas_naif': 15000.}


def test_interval_lebar_tidak_mendapat_trust_gratis_dan_rentang_nol_tepat_diakui():
    a = aturan()
    m = trust_cabai.metrik([titik(i) for i in range(40)])
    assert m['pengecualian_konstan']
    assert all(s['lolos'] is True for s in trust_cabai.gerbang_interval(m, 'tinggi', a))
    bad = trust_cabai.metrik([titik(i, lower=5000., upper=40000.) for i in range(40)])
    assert bad['cakupan'] == 100 and not bad['pengecualian_konstan']
    assert not all(s['lolos'] for s in trust_cabai.gerbang_interval(bad, 'sedang', a))


def test_arah_membutuhkan_seluruh_kelas_dan_naif_tidak_mendapat_akurasi_arah_palsu():
    a = aturan()
    pts = [titik(i) for i in range(60)]
    m = trust_cabai.metrik_arah(pts, 7, a)
    assert m['balanced_accuracy'] is None
    assert all(s['lolos'] is None for s in trust_cabai.gerbang_arah(m, 'sedang', a))
    pts = [titik(i, actual=[12000.,15000.,18000.][i%3], pred=[12000.,15000.,18000.][i%3]) for i in range(60)]
    m = trust_cabai.metrik_arah(pts, 7, a)
    assert m['balanced_accuracy'] == 100
    assert all(s['lolos'] for s in trust_cabai.gerbang_arah(m, 'tinggi', a))
    for p in pts:
        p['prediksi'] = p['naif']
    m = trust_cabai.metrik_arah(pts, 7, a)
    assert m['balanced_accuracy'] == pytest.approx(100/3)


def test_origin_tumpang_tindih_tidak_menambah_bukti_bulanan():
    pts = [titik(i) for i in range(90)]
    result = trust_cabai.nonoverlap(pts, 30)
    assert [p['origin'] for p in result] == [0,30,60]


def test_batas_tepat_lima_persen_masih_stabil_bukan_lonjak_akibat_float():
    pts = []
    for i, price in enumerate((57000.,60000.,63000.)):
        p = titik(i, actual=price, pred=price); p['naif'] = 60000.; pts.append(p)
    result = trust_cabai.metrik_arah(pts, 30, aturan())
    assert result['kasus_per_kelas'] == {'-1':0,'0':3,'1':0}
    for i, price in enumerate((56999.,63001.)):
        p = titik(i+3, actual=price, pred=price); p['naif'] = 60000.; pts.append(p)
    assert trust_cabai.metrik_arah(pts,30,aturan())['kasus_per_kelas'] == {'-1':1,'0':3,'1':1}


def test_periode_dipilih_berdasar_kecukupan_data_bukan_galat():
    class Bank:
        minimal = 60
        seri = serie(1000)
        def jendela(self, h, end, panjang):
            n = 2 if end == 700 else 8
            return [titik(i, pred=30000.) for i in range(n)]
    periods, skipped = trust_cabai.periode_validasi(Bank(), 7, 700, aturan())
    assert len(periods) == 3 and len(skipped) == 1
    assert periods[0]['akhir'] == Bank.seri.tanggal[610].isoformat()
    assert all(p['metrik']['smape'] > 50 for p in periods)


def test_bank_aci_identik_dengan_produksi_dan_tidak_memakai_aktual_masa_depan():
    s = serie(900)
    s.nilai = 15000*np.exp(.1*np.sin(np.arange(s.n)/40))
    origin = 800
    bank = trust_cabai.BankPrediksi(s, s.nilai.copy(), 'naif', {})
    a = bank.interval('naif', origin)
    changed = s.nilai.copy(); changed[origin+1:] *= 10
    other = analisis.SeriHarian(s.tanggal, changed)
    b = trust_cabai.BankPrediksi(other, changed, 'naif', {}).interval('naif', origin)
    np.testing.assert_allclose(a, b, rtol=1e-12)
    prefix = analisis.SeriHarian(s.tanggal[:origin+1], s.nilai[:origin+1])
    bt = analisis.backtest_kalibrasi(prefix, prefix.nilai, 'naif', {}, 30, 60)
    aci = analisis.kalibrasi_adaptif(bt, .8)
    _, r = analisis.log_return(prefix)
    expected = analisis.interval_adaptif(bt, 30, aci['alfa_akhir'], float(np.std(r[-90:])))
    np.testing.assert_allclose(a, expected, rtol=1e-12)


def hv_palsu(end=date(2026,11,13)):
    conditions = {l: [trust_cabai.cek('contoh', True)] for l in ('sedang', 'tinggi')}
    trust = {'per_horizon': {}, '_saat_terbit': {}}
    projections = []
    for h in (1,7,30):
        trust['per_horizon'][str(h)] = {'syarat': copy.deepcopy(conditions), 'arah': {'syarat': copy.deepcopy(conditions)}}
        trust['per_horizon'][str(h)]['syarat']['tinggi'].append(trust_cabai.cek('Pemantauan prospektif ramalan terbit', None))
        trust['_saat_terbit'][str(h)] = {'prediksi':15000.,'bawah':14000,'atas':16000,'naif':15000.,'bawah_naif':14000.,'atas_naif':16000.}
        projections.append({'h':h,'tanggal':(end+timedelta(days=h)).isoformat(),'prediksi':15000,'bawah':14000,'atas':16000})
    return SimpleNamespace(trust_cabai=trust, model_terpilih='naif', seri=serie(end=end), proyeksi=projections,
                           validasi={'status':'eksperimen','syarat':[]})


SOURCE = {'boleh_training':True,'kode_sumber':'BD-SP2KP','kode_wilayah':'1709'}
NOW = datetime(2026,11,13,10,tzinfo=timezone.utc)


def test_buku_prospektif_idempoten_menjaga_ramalan_pertama_dan_memisahkan_varian(konf):
    konf.hari_ini = date(2026,11,13)
    a = aturan()
    first = hv_palsu()
    trust_cabai.lengkapi(konf, first, SOURCE, a, 'CRW02', waktu=NOW)
    path = konf.akar/'data/registry/trust_cabai_prospektif.json'
    assert len(json.loads(path.read_text())['ramalan']) == 3
    before = path.read_text()
    second = hv_palsu(); second.proyeksi[0]['prediksi'] = 25000
    trust_cabai.lengkapi(konf, second, SOURCE, a, 'CRW02', waktu=NOW)
    assert path.read_text() == before
    assert first.trust_cabai['level_gabungan'] != 'tinggi'
    other = hv_palsu()
    trust_cabai.lengkapi(konf, other, SOURCE, a, 'CRW01', waktu=NOW)
    assert first.trust_cabai['prospektif']['firma'] != other.trust_cabai['prospektif']['firma']
    assert len(json.loads(path.read_text())['ramalan']) == 6
    future = hv_palsu(date(2026,11,23)); konf.hari_ini = date(2026,11,23)
    trust_cabai.lengkapi(konf, future, SOURCE, a, 'CRW02', catat=False, waktu=datetime(2026,11,23,10,tzinfo=timezone.utc))
    assert future.trust_cabai['prospektif']['1']['hari_terbit_dengan_aktual'] == 1
    assert future.trust_cabai['prospektif']['7']['hari_terbit_dengan_aktual'] == 1
    assert future.trust_cabai['prospektif']['30']['hari_terbit_dengan_aktual'] == 0


def test_demo_backfill_dan_buku_rusak_tidak_menciptakan_bukti(konf):
    a = aturan(); path = konf.akar/'data/registry/trust_cabai_prospektif.json'
    backfill = hv_palsu()
    trust_cabai.lengkapi(konf, backfill, SOURCE, a, 'CRW02', waktu=NOW)
    assert not path.exists()
    konf.hari_ini = date(2026,11,13)
    demo = hv_palsu()
    trust_cabai.lengkapi(konf, demo, SOURCE, a, 'CRW02', mode_demo=True, waktu=NOW)
    assert demo.trust_cabai['level_gabungan'] == 'belum_cukup_bukti' and not path.exists()
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text('broken')
    real = hv_palsu()
    trust_cabai.lengkapi(konf, real, SOURCE, a, 'CRW02', waktu=NOW)
    assert path.read_text() == 'broken'
    assert real.trust_cabai['prospektif']['1']['galat_buku']


def test_pemilihan_model_cabai_tidak_melihat_450_hari_yang_dicadangkan(monkeypatch):
    from pipeline import konfigurasi
    s = serie(1000)
    s.nilai = 15000*np.exp(.1*np.sin(np.arange(s.n)/45))
    p = copy.deepcopy(konfigurasi.muat().pengaturan)
    p['analisis']['model_pohon'] = False
    cutoffs = []
    def capture(*args, **kwargs):
        cutoffs.append(args[9]); return {}
    monkeypatch.setattr(trust_cabai, 'evaluasi', capture)
    a = analisis.analisis_varian(s, 'volatil', [], p, kode='CRW02', kriteria_cabai=aturan())
    changed = s.nilai.copy(); changed[-450:] *= np.linspace(1., 3., 450)
    b = analisis.analisis_varian(analisis.SeriHarian(s.tanggal, changed), 'volatil', [], p, kode='CRW02', kriteria_cabai=aturan())
    assert a.model_terpilih == b.model_terpilih
    assert a.holdout['smape'] != b.holdout['smape']
    assert cutoffs == [s.tanggal[-1]-timedelta(days=450)]*2


def test_hari_raya_tidak_diakui_dari_satu_jenis_yang_lengkap_saja():
    from pipeline.konfigurasi import Acara
    s = serie(1000)
    calendar = [Acara(date(2025,12,25),'Natal','hari_raya','pasti'), Acara(date(2024,12,25),'Natal','hari_raya','pasti'),
                Acara(date(2026,3,21),'Idul Fitri','hari_raya','pasti')]
    features, checks = trust_cabai.fitur_tersedia(s, s.tanggal[-1], 'musiman_kalender', calendar, {}, {}, [], aturan())
    assert len(features['hari_raya_tahun_dengan_observasi']['natal']) == 2
    assert checks[0]['lolos'] is False


def test_kondisi_horizon_mengikuti_asal_proyeksi_saat_harga_terakhir_lebih_lama(monkeypatch):
    from pipeline import konfigurasi
    from pipeline.konfigurasi import Acara
    class Bank:
        def __init__(self, seri, *args):
            self.seri, self.minimal = seri, 60
        def jendela(self,*args):return []
        def prediksi(self,*args):return None
    monkeypatch.setattr(trust_cabai,'BankPrediksi',Bank)
    s = serie()
    asof = s.tanggal[-1]+timedelta(days=1)
    holiday = Acara(s.tanggal[-1]+timedelta(days=37),'Natal uji','hari_raya','pasti')
    result = trust_cabai.evaluasi(s,s.nilai,'naif',{},konfigurasi.muat().pengaturan,[holiday],{},{},aturan(),
                                  s.tanggal[-1]-timedelta(days=450),asof=asof)
    assert result['tanggal_asal_proyeksi'] == s.tanggal[-1].isoformat()
    assert result['per_horizon']['1']['kondisi_saat_ini'] == ['normal']


def test_pipeline_menerapkan_trust_cabai_tanpa_mengubah_skor_umum(konf, akar_sementara):
    lines = ['tanggal,kode_pasar,kode_varian,harga,satuan,kode_sumber']
    for i in range(1000):
        t = konf.hari_ini-timedelta(days=i)
        if t.weekday() < 5:
            lines.append(f'{t},PSR01,CRW02,15000,kg,BD-SP2KP')
    tulis_csv(akar_sementara/'data/masuk/harga/uji.csv', '\n'.join(lines))
    out = akar_sementara/'site/data'
    proses.jalankan(konf, out, sinkron_github=False, kirim_notifikasi=False)
    analytical = json.loads((out/'analitik.json').read_text())
    v = next(v for v in analytical['varian'] if v['kode'] == 'CRW02')
    trust = v['trust_cabai']
    assert trust['versi'] == 'cabai-v1'
    assert set(trust['per_horizon']) == {'1','7','30'}
    assert all(x['level'] != 'tinggi' for x in trust['per_horizon'].values())
    assert all(x['level'] == 'sedang' for x in trust['per_horizon'].values())
    assert v['syarat_lolos'] == sum(s['lolos'] is True for s in v['validasi']['syarat'])
    assert v['status'] == 'eksperimen'
    assert json.loads((out/'trust_cabai.json').read_text())['per_varian']['CRW02'] == trust
    assert 'trust_cabai' in json.loads((out/'seri/CRW02.json').read_text())


def test_arah_bulanan_memakai_arsip_panjang_bila_kelas_pada_holdout_harga_tidak_cukup(konf):
    end = date(2036,11,13)
    konf.hari_ini = end
    hv = hv_palsu(end)
    hv.seri = serie(3400, end)
    hv.trust_cabai['kode'] = 'CRW02'
    hv.trust_cabai['data'] = trust_cabai.data_seri(hv.seri, end, [0,1,2,3,4], konf.kalender)
    for x in hv.trust_cabai['per_horizon'].values():
        x['arah']['metrik'] = {'sedang':None,'tinggi':None}
        x['arah']['syarat'] = {l:[trust_cabai.cek('Kelas pada holdout harga belum cukup',None)] for l in ('sedang','tinggi')}
    a = aturan()
    signature = trust_cabai.firma_prospektif(konf, hv, SOURCE, a)
    records = []
    for i in range(90):
        issued = end-timedelta(days=31*(i+1))
        target = issued+timedelta(days=30)
        actual = (12000.,15000.,18000.)[i%3]
        hv.seri.nilai[hv.seri.indeks(target)] = actual
        records.append({'id':str(i),'firma':signature,'kode':'CRW02','h':30,'tanggal':target.isoformat(),
                        'diterbitkan_pada':datetime(issued.year,issued.month,issued.day,10,tzinfo=timezone.utc).isoformat(),
                        'prediksi':actual,'bawah':actual,'atas':actual,'naif':15000.,'bawah_naif':10000.,'atas_naif':20000.})
    path = konf.akar/'data/registry/trust_cabai_prospektif.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'versi':1,'ramalan':records}))
    trust_cabai.lengkapi(konf,hv,SOURCE,a,'CRW02',catat=False,waktu=datetime(2036,11,13,10,tzinfo=timezone.utc))
    assert hv.trust_cabai['per_horizon']['30']['arah']['level'] == 'tinggi'
    assert hv.trust_cabai['per_horizon']['30']['arah']['basis']['tinggi'] == 'ramalan_terbit_prospektif'
    assert hv.trust_cabai['prospektif']['30']['hari_terbit_dengan_aktual'] == 90

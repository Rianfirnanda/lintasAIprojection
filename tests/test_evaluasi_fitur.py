import copy
from datetime import date, timedelta
import numpy as np
from pipeline import evaluasi_fitur, kebijakan_model, musiman, analisis


def bloc(cakupan=80, lebar=2, skor=3):
    a=dict(n=60,smape=10,mae=100,bias=0,cakupan=80,lebar=2,skor_interval=3)
    c={**a,'smape':8,'mae':80,'cakupan':cakupan,'lebar':lebar,'skor_interval':skor}
    return {'acuan':a,'calon':c}


def test_promosi_membutuhkan_galat_bias_cakupan_lebar_dan_konsistensi():
    aturan=kebijakan_model.muat()
    assert evaluasi_fitur.putuskan([bloc() for _ in range(3)],aturan,3)[0]
    for kwargs in ({'cakupan':60},{'lebar':5},{'skor':9}):
        assert not evaluasi_fitur.putuskan([bloc(**kwargs) for _ in range(3)],aturan,3)[0]
    assert not evaluasi_fitur.putuskan([bloc()],aturan,3)[0]
    b=[bloc() for _ in range(3)];b[0]['calon']['smape']=11;b[1]['calon']['smape']=11
    assert not evaluasi_fitur.putuskan(b,aturan,3)[0]
    b=[bloc() for _ in range(3)];b[0]['calon']['bias']=20
    assert not evaluasi_fitur.putuskan(b,aturan,3)[0]


def test_regional_dan_klimatologi_hanya_memakai_informasi_hingga_kemarin():
    n=900;hari=[date(2022,1,1)+timedelta(days=i) for i in range(n)]
    s=analisis.SeriHarian(hari,15000+np.arange(n).astype(float))
    r=analisis.SeriHarian(hari,16000+np.arange(n).astype(float))
    wx={(t,'curah_hujan_mm'):float(i%20) for i,t in enumerate(hari)}
    a=musiman.siapkan(s,[],wx,regional={'1771':r})
    cutoff=800
    prix=r.nilai.copy();prix[cutoff:]*=5
    futur={k:(999 if k[0]>=hari[cutoff] else v) for k,v in wx.items()}
    b=musiman.siapkan(s,[],futur,regional={'1771':analisis.SeriHarian(hari,prix)})
    for h in (1,7,14,30):np.testing.assert_allclose(a['fitur'][h][:cutoff+1],b['fitur'][h][:cutoff+1])
    assert a['tersedia']['regional'] and a['tersedia']['cuaca']
    prefix=musiman.siapkan(analisis.SeriHarian(hari[:700],s.nilai[:700]),[],wx,
                          regional={'1771':r})
    for h in (1,7,14,30):np.testing.assert_allclose(a['fitur'][h][:700],prefix['fitur'][h])


def test_regional_tidak_meneruskan_observasi_45_hari():
    hari=[date(2026,1,1)+timedelta(days=i) for i in range(60)]
    s=analisis.SeriHarian(hari,np.full(60,15000.))
    r=analisis.SeriHarian(hari,np.r_[np.full(15,16000.),np.full(45,np.nan)])
    data=musiman.siapkan(s,[],{},regional={'1771':r})
    assert np.all(data['fitur'][7][-30:,-1]==0)


def test_model_baru_tidak_disertifikasi_jika_holdout_memburuk():
    v=analisis.pengaturan_validasi({})
    h={'model':'musiman_cuaca','smape':3.,'smape_naif':4.,'mae':100.,'mae_naif':130.,
       'bias_persen':0.,'cakupan_persen':80.,'mase':.7,'akurasi_arah':80.,
       'menang_origin_vs_naif':9,'origin_berbeda_vs_naif':10}
    assert analisis.nilai_validasi('pokok',v,900,98,h)['status']=='valid'
    h['smape']=4.5
    assert analisis.nilai_validasi('pokok',v,900,98,h)['status']=='eksperimen'


def test_holdout_hanya_mengubah_laporan_bukan_model_terpilih():
    from tests.test_musiman import seri_uji
    from pipeline import konfigurasi
    s, acara=seri_uji()
    p=copy.deepcopy(konfigurasi.muat().pengaturan);p['analisis']['model_pohon']=False
    a=analisis.analisis_varian(s,'pokok',acara,p)
    ubah=s.nilai.copy();ubah[-90:]*=3
    b=analisis.analisis_varian(analisis.SeriHarian(s.tanggal,ubah),'pokok',acara,p)
    assert a.model_terpilih==b.model_terpilih
    assert a.holdout['smape']!=b.holdout['smape']
    assert not a.validasi['holdout_untuk_seleksi'] and not b.validasi['holdout_untuk_seleksi']
    for audit in a.parameter['audit_fitur_bertahap']:
        for periode in audit.get('periode',[]):
            assert periode['akhir_kalibrasi'] < periode['mulai']
            assert periode['akhir'] <= (s.tanggal[-1]-timedelta(days=90)).isoformat()

"""Kebijakan eksplisit sumber training dan evaluasi fitur, terpisah dari data tampilan."""
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

BAWAAN = {
    'sumber_training': ['BD-SP2KP', 'BD-PIHPS'], 'minimal_hari_sumber': 60, 'maks_umur_hari': 7,
    'tahap_fitur': ['kalender', 'cuaca', 'regional'], 'periode_validasi': 3, 'panjang_periode_hari': 90,
    'perbaikan_smape_min_persen': 2., 'degradasi_mae_maks_persen': 2., 'cakupan_min_persen': 70.,
    'kenaikan_skor_interval_maks_persen': 5., 'kenaikan_lebar_maks_persen': 20.,
}


def muat(akar=None):
    p = Path(akar) / 'config/kebijakan_model.json' if akar else None
    d = {**BAWAAN, **(json.loads(p.read_text()) if p and p.exists() else {})}
    if set(d) - set(BAWAAN):
        raise ValueError('Kunci kebijakan model tidak dikenal')
    if d['sumber_training'] != ['BD-SP2KP', 'BD-PIHPS']:
        raise ValueError('Urutan training wajib SP2KP lalu PIHPS; sumber lapangan bukan sumber training resmi')
    urutan = ['kalender', 'cuaca', 'regional']
    if d['tahap_fitur'] != urutan[:len(d['tahap_fitur'])]:
        raise ValueError('Tahap fitur wajib merupakan urutan kalender, cuaca, lalu regional')
    for k in ('minimal_hari_sumber', 'maks_umur_hari', 'periode_validasi', 'panjang_periode_hari'):
        if type(d[k]) is not int or d[k] <= 0:
            raise ValueError(f'{k} harus bilangan bulat positif')
    if d['periode_validasi'] < 3 or d['panjang_periode_hari'] < 30:
        raise ValueError('Evaluasi wajib minimal tiga periode, masing-masing minimal 30 hari')
    for k in ('perbaikan_smape_min_persen','degradasi_mae_maks_persen','cakupan_min_persen',
              'kenaikan_skor_interval_maks_persen','kenaikan_lebar_maks_persen'):
        if not isinstance(d[k], (float, int)) or not 0 <= d[k] <= 100:
            raise ValueError(f'{k} harus persentase 0 sampai 100')
    return d


def pilih(observasi, kode, target, cadangan, asof, aturan):
    """Pilih satu sumber dan wilayah utuh; jangan menambal hari SP2KP dengan sumber lain."""
    grup = defaultdict(lambda: defaultdict(list))
    for o in observasi:
        if (o.kode_varian == kode and o.kode_sumber in aturan['sumber_training']
                and o.status in ('lolos', 'divalidasi') and o.tanggal <= asof):
            grup[(o.kode_wilayah, o.kode_sumber)][o.tanggal].append(o.harga)
    audit = []
    wilayah = list(dict.fromkeys(w for w in (target, cadangan) if w))
    for w in wilayah:
        for sumber in aturan['sumber_training']:
            hari = grup.get((w, sumber), {})
            umur = (asof - max(hari)).days if hari else None
            layak = len(hari) >= aturan['minimal_hari_sumber'] and umur <= aturan['maks_umur_hari']
            alasan = []
            if len(hari) < aturan['minimal_hari_sumber']:
                alasan.append('Riwayat tanggal observasi belum cukup')
            if umur is None:
                alasan.append('Belum ada data pada tanggal penilaian')
            elif umur > aturan['maks_umur_hari']:
                alasan.append('Data terakhir terlalu lama')
            audit.append({'wilayah': w, 'sumber': sumber, 'hari_teramati': len(hari), 'umur_hari': umur,
                          'layak': layak, 'alasan': alasan})
            if layak:
                return {t: float(median(v)) for t, v in hari.items()}, {
                    'kode_wilayah': w, 'kode_sumber': sumber, 'boleh_training': True,
                    'jenis_data': 'observasi_asli', 'tanggal_penilaian': asof.isoformat(),
                    'tanggal_awal': min(hari).isoformat(), 'tanggal_akhir': max(hari).isoformat(),
                    'hari_teramati': len(hari), 'cadangan': sumber != aturan['sumber_training'][0] or w != target,
                    'calon_sumber': audit,
                }
    return {}, {'boleh_training': False, 'jenis_data': 'pembanding_lapangan',
                'tanggal_penilaian': asof.isoformat(), 'calon_sumber': audit,
                'alasan': 'Tidak ada sumber resmi yang cukup panjang dan segar setelah pemeriksaan kualitas'}

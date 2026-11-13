"""Evaluasi lokal tanpa notifikasi, koneksi API, atau perubahan registry produksi."""
import argparse
import copy
import json
from datetime import date, timedelta
from pathlib import Path
import numpy as np
from . import analisis, konfigurasi, kebijakan_model, masukan, kualitas


def kasus_sintetis():
    rng = np.random.default_rng(72)
    n = 1200
    hari = [date(2022, 1, 1)+timedelta(days=i) for i in range(n)]
    hujan = 10+rng.normal(0, 2, n)
    log_harga = np.zeros(n)
    for t in range(1, n):
        log_harga[t] = log_harga[t-1]+.005*(hujan[max(t-8, 0)]-10)
    seri = {
        'tetap': np.full(n, 15000.), 'tren': 15000*np.exp(.0003*np.arange(n)),
        'musim_tahunan': 15000*np.exp(.16*np.sin(2*np.pi*np.arange(n)/365.25)),
        'hujan_kausal': 15000*np.exp(log_harga), 'derau': 15000+rng.normal(0, 100, n),
        'lonjakan': np.r_[np.full(n-60, 15000.), np.full(60, 30000.)],
        'celah_45_hari': np.r_[np.full(n-45, 15000.), np.full(45, np.nan)],
    }
    wx = {(t, 'curah_hujan_mm'): float(hujan[i]) for i, t in enumerate(hari)}
    return [(nama, analisis.SeriHarian(hari, y), 'pokok', {}, wx, {}) for nama, y in seri.items()]


def kasus_nyata(konf, aturan, kode):
    h = masukan.baca_semua(konf.akar/'data/masuk', konf, akar_relatif=konf.akar)
    q = kualitas.jalankan(h.observasi, konf, kualitas.baca_keputusan(konf.akar/'data/validasi'))
    hasil = []
    for v in konf.varian_aktif:
        if kode and v.kode not in kode:
            continue
        prix, asal = kebijakan_model.pilih(q.observasi, v.kode, konf.wilayah_target,
                                          konf.wilayah_cadangan, konf.hari_ini, aturan)
        if not prix:
            hasil.append((v.kode, None, v.kelompok, asal, {}, {})); continue
        w = asal['kode_wilayah']
        wx = {(x.tanggal, x.indikator): x.nilai for x in h.konteks if x.kode_sumber=='BD-CUACA' and x.kode_wilayah==w}
        regional = {}
        for code in konf.wilayah:
            if code == w:
                continue
            data, _ = kebijakan_model.pilih(q.observasi, v.kode, code, None, konf.hari_ini, aturan)
            if data:
                regional[code] = analisis.bentuk_seri(data)
        hasil.append((v.kode, analisis.bentuk_seri(prix), v.kelompok, asal, wx, regional))
    return hasil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-nyata', action='store_true')
    parser.add_argument('--model-pohon', action='store_true', help='Aktifkan RF/Boosting; lebih mahal')
    parser.add_argument('--kode', help='Kode varian dipisah koma, khusus data nyata')
    parser.add_argument('--keluaran', type=Path, default=Path('/tmp/evaluasi-model.json'))
    args = parser.parse_args()
    konf = konfigurasi.muat()
    kode_pilih = {x.strip() for x in args.kode.split(',') if x.strip()} if args.kode else None
    if kode_pilih and not args.data_nyata:
        parser.error('--kode hanya berlaku bersama --data-nyata')
    if kode_pilih and not kode_pilih <= {v.kode for v in konf.varian_aktif}:
        parser.error('Kode varian tidak dikenal atau tidak aktif')
    aturan = kebijakan_model.muat(konf.akar)
    peng = copy.deepcopy(konf.pengaturan)
    peng['analisis']['model_pohon'] = args.model_pohon
    kasus = kasus_nyata(konf, aturan, kode_pilih) if args.data_nyata else kasus_sintetis()
    hasil = []
    for kode, seri, kelompok, sumber, wx, regional in kasus:
        if seri is None:
            hasil.append({'kode': kode, 'sumber': sumber, 'model': None}); continue
        hv = analisis.analisis_varian(seri, kelompok, konf.hari_raya(), peng,
                                      kode=kode if args.data_nyata else None, cuaca=wx, kalender=konf.kalender,
                                      regional=regional, kebijakan=aturan)
        if not args.data_nyata:
            hv.validasi['boleh_proyeksi_resmi'] = False
        hasil.append({'kode': kode, 'sumber': sumber, 'model': hv.model_terpilih,
                      'validasi': hv.validasi, 'holdout': hv.holdout, 'audit_fitur': hv.parameter['audit_fitur_bertahap'],
                      'proyeksi': hv.proyeksi, 'catatan': hv.catatan})
        print(f'{kode}: {hv.model_terpilih}, {hv.validasi["status"]}', flush=True)
    output = {'mode': 'data_nyata' if args.data_nyata else 'skenario_sintetis', 'model_pohon': args.model_pohon,
              'kebijakan': aturan, 'hari_penilaian': konf.hari_ini.isoformat(), 'hasil': hasil}
    args.keluaran.parent.mkdir(parents=True, exist_ok=True)
    args.keluaran.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()

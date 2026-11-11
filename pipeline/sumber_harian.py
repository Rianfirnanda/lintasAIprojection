"""Harga terakhir dan riwayat per sumber, pasar/wilayah, dan varian."""
from collections import defaultdict
from statistics import median


def rangkum(konf, observasi, konteks, *, riwayat=False):
    kelompok = defaultdict(list)
    cakupan = set()
    for o in observasi:
        if o.kode_sumber not in ("BD-SP2KP", "BD-PIHPS"):
            continue
        kelompok[(o.kode_sumber, o.kode_pasar, o.kode_wilayah, o.kode_varian)].append(
            (o.tanggal, o.harga, o.status in ("lolos", "divalidasi")))
        cakupan.add((o.kode_sumber, o.kode_wilayah, o.kode_varian))
    for k in konteks:
        if (k.kode_sumber == "BD-PIHPS" and k.indikator == "harga_pihps"
                and k.kode_varian in konf.varian and k.nilai > 0
                and (k.kode_sumber, k.kode_wilayah, k.kode_varian) not in cakupan):
            kelompok[(k.kode_sumber, "", k.kode_wilayah, k.kode_varian)].append((k.tanggal, k.nilai, None))
    hasil = []
    for (sumber, pasar, wilayah, varian), nilai in sorted(kelompok.items()):
        tanggal = max(x[0] for x in nilai)
        terbaru = [x for x in nilai if x[0] == tanggal]
        sumber_master = konf.sumber[sumber]
        baris = {
            "kode_sumber": sumber,
            "sumber": "SP2KP Kemendag" if sumber == "BD-SP2KP" else "PIHPS Bank Indonesia (BI)",
            "url": sumber_master.url,
            "pasar": konf.pasar[pasar].nama if pasar else konf.wilayah[wilayah].nama,
            "varian": konf.varian[varian].nama, "satuan": konf.varian[varian].satuan,
            "tanggal": tanggal, "harga": median(x[1] for x in terbaru),
            "peran": "Wilayah utama" if wilayah == konf.wilayah_target else "Pembanding wilayah",
            "status": ("Data konteks pembanding" if not pasar else "Lolos pemeriksaan" if all(x[2] for x in terbaru)
                       else "Ada data tidak dipakai"),
        }
        if riwayat:
            per_tanggal = defaultdict(list)
            for t, harga, lolos in nilai:
                per_tanggal[t].append((harga, lolos))
            baris["riwayat"] = [
                [t.isoformat(), median(x[0] for x in items),
                 "Data konteks pembanding" if not pasar else "Lolos pemeriksaan" if all(x[1] for x in items)
                 else "Ada data tidak dipakai"]
                for t, items in sorted(per_tanggal.items())
            ]
        hasil.append(baris)
    return hasil

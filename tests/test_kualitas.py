from datetime import date, datetime, timedelta

from pipeline import kualitas
from pipeline.masukan import Observasi, id_observasi


def obs(tgl, harga, pasar="PSR01", varian="CRW02", sumber="PSR-ENUM", responden="R1", id_klien="", waktu=None, wilayah=None):
    wil = wilayah or ("1709" if pasar in ("PSR01", "PSR02") else {"PSR91": "1708", "PSR92": "1771"}[pasar])
    return Observasi(
        id=id_observasi(tgl, pasar, varian, sumber, responden, harga, "kg", id_klien), tanggal=tgl, kode_pasar=pasar,
        kode_wilayah=wil, kode_varian=varian, kode_sumber=sumber, harga=harga, harga_asli=harga, satuan_asli="kg",
        petugas="PTG", responden=responden, id_klien=id_klien, waktu_input=waktu, berkas="uji.csv", baris=2,
    )


def riwayat_stabil(akhir: date, hari=20, harga=40000.0):
    hasil = []
    for i in range(hari, 0, -1):
        t = akhir - timedelta(days=i)
        for p, r in (("PSR01", "R1"), ("PSR01", "R2"), ("PSR02", "R1")):
            hasil.append(obs(t, harga + (i % 3) * 200, pasar=p, responden=r))
    return hasil


def test_deduplikasi_identik_dan_kiriman_ulang(konf):
    t = date(2026, 9, 28)
    a = obs(t, 40000)
    b = obs(t, 40000)  # identik
    c = obs(t, 41000, responden="R2", id_klien="uuid-1")
    d = obs(t, 41000, responden="R2", id_klien="uuid-1", pasar="PSR02")  # id_klien sama = kiriman ulang
    hasil = kualitas.jalankan([a, b, c, d], konf, {})
    assert hasil.jumlah_duplikat == 2
    assert len(hasil.observasi) == 2


def test_konflik_kunci_dan_batas_wajar(konf):
    t = date(2026, 9, 28)
    hasil = kualitas.jalankan([obs(t, 40000), obs(t, 42000), obs(t, 400000, responden="R9")], konf, {})
    tanda = {o.harga: o.tanda for o in hasil.observasi}
    assert "duplikat_konflik" in tanda[40000] and "duplikat_konflik" in tanda[42000]
    assert "di_luar_batas_wajar" in tanda[400000]
    assert all(o.status == "perlu_validasi" for o in hasil.observasi)
    assert hasil.dipakai() == []


def test_lonjakan_tunggal_ditahan_tetapi_terkonfirmasi_silang_dilepas(konf):
    t = date(2026, 9, 28)
    dasar = riwayat_stabil(t)
    # satu observasi melonjak sendirian -> ditahan
    hasil = kualitas.jalankan(dasar + [obs(t, 60000)], konf, {})
    kini = [o for o in hasil.observasi if o.tanggal == t]
    assert kini[0].status == "perlu_validasi"
    assert set(kini[0].tanda) & {"perubahan_ekstrem", "pencilan_statistik"}
    # lonjakan didukung pasar/responden lain -> nyata, dilepas
    hasil = kualitas.jalankan(dasar + [obs(t, 60000), obs(t, 61000, responden="R2"), obs(t, 60500, pasar="PSR02")], konf, {})
    kini = [o for o in hasil.observasi if o.tanggal == t]
    assert all(o.status == "lolos" for o in kini)
    assert all("lonjakan_terkonfirmasi" in o.tanda for o in kini)


def test_persistensi_melepas_level_baru_di_pasar_tunggal(konf):
    akhir = date(2026, 9, 28)
    riwayat = [obs(akhir - timedelta(days=i), 40000 + (i % 3) * 200, pasar="PSR91") for i in range(25, 1, -1)]
    lonjak1 = obs(akhir - timedelta(days=1), 55000, pasar="PSR91")
    lonjak2 = obs(akhir, 55500, pasar="PSR91")
    hasil = kualitas.jalankan(riwayat + [lonjak1, lonjak2], konf, {})
    st = {o.tanggal: o.status for o in hasil.observasi}
    assert st[akhir - timedelta(days=1)] == "lolos" and st[akhir] == "lolos"


def test_salah_ketik_sekali_tetap_ditahan(konf):
    akhir = date(2026, 9, 28)
    riwayat = [obs(akhir - timedelta(days=i), 40000, pasar="PSR91") for i in range(25, 1, -1)]
    salah = obs(akhir - timedelta(days=1), 55000, pasar="PSR91")
    normal = obs(akhir, 40200, pasar="PSR91")
    hasil = kualitas.jalankan(riwayat + [salah, normal], konf, {})
    st = {o.tanggal: o.status for o in hasil.observasi}
    assert st[akhir - timedelta(days=1)] == "perlu_validasi" and st[akhir] == "lolos"


def test_keputusan_validator(konf):
    t = date(2026, 9, 28)
    a, b = obs(t, 400000), obs(t, 500000, responden="R2")
    kep = {a.id: kualitas.Keputusan("terima", "dicek", "V1", "2026-09-29"),
           b.id: kualitas.Keputusan("tolak", "salah ketik", "V1", "2026-09-29")}
    hasil = kualitas.jalankan([a, b], konf, kep)
    st = {o.id: o.status for o in hasil.observasi}
    assert st[a.id] == "divalidasi" and st[b.id] == "ditolak_validator"


def test_baca_keputusan(tmp_path):
    (tmp_path / "k.csv").write_text(
        "id_observasi,keputusan,alasan,validator,tanggal_validasi\nabc,terima,ok,V1,2026-09-29\nabc,tolak,koreksi,V2,2026-09-30\nx,??,,V1,\n")
    kep = kualitas.baca_keputusan(tmp_path)
    assert list(kep) == ["abc"] and kep["abc"].keputusan == "tolak"


def test_rekonsiliasi_memilih_sumber_prioritas(konf):
    t = date(2026, 9, 28)
    hasil = kualitas.rekonsiliasi([obs(t, 40000), obs(t, 48000, sumber="BPS-HRG")], konf)
    assert hasil[0]["melebihi_batas"] is True
    assert hasil[0]["sumber_dipakai"] == "BPS-HRG"
    assert hasil[0]["selisih_persen"] == 20.0


def test_ketepatan_waktu(konf):
    wajib = kualitas.hari_wajib(konf, date(2026, 8, 30), date(2026, 9, 28))
    assert all(d.weekday() < 5 for d in wajib)
    t = wajib[-1]
    tepat = obs(t, 40000, varian="BRS03", waktu=datetime(t.year, t.month, t.day, 10, 0))
    telat = obs(t, 40000, varian="BRS04", waktu=datetime(t.year, t.month, t.day, 18, 0))
    for o in (tepat, telat):
        o.status = "lolos"
    k = kualitas.ketepatan_waktu([tepat, telat], konf)
    psr01 = next(p for p in k["per_pasar"] if p["kode_pasar"] == "PSR01")
    assert psr01["diterima"] == 2 and psr01["ketepatan_persen"] == 50.0
    assert psr01["diharapkan"] == len(wajib) * len(konf.varian_aktif)
    assert psr01["tanggal_terakhir"] == t.isoformat()


def test_libur_pencatatan_terdeteksi_dari_data():
    """Hari kerja yang kosong di semua pasar satu sumber (mis. SP2KP, tiga pasar) dianggap libur pencatatan; kosong di satu
    pasar saja tetap dihitung data hilang."""
    senin = date(2026, 3, 16)
    hari = [senin + timedelta(days=i) for i in range(5)]  # Senin-Jumat
    data = []
    for p in ("PSR01", "PSR91", "PSR92"):
        for t in hari:
            if t == hari[2]:  # Rabu: semua pasar SP2KP tidak mencatat
                continue
            if p == "PSR01" and t == hari[3]:  # Kamis: hanya satu pasar kosong
                continue
            data.append(obs(t, 40000, pasar=p, sumber="BD-SP2KP"))
    data.append(obs(hari[2], 41000, pasar="PSR02", sumber="PSR-ENUM"))  # sumber satu pasar tidak menentukan libur
    assert kualitas.libur_pencatatan(data) == {hari[2]}

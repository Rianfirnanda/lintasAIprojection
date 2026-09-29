from datetime import date

from pipeline import layanan


def formulir_skm(nilai, pengguna="TPID / Pemerintah Daerah"):
    bagian = [f"### Jenis pengguna\n\n{pengguna}"]
    for i, v in enumerate(nilai, 1):
        bagian.append(f"### U{i}. Unsur ke-{i}\n\n{v}")
    bagian.append("### Saran perbaikan\n\n_No response_")
    return "\n\n".join(bagian)


def test_urai_formulir():
    f = layanan.urai_formulir("### A\n\nsatu\n\n### B\n\n_No response_\n\n### C\n\nbaris 1\nbaris 2")
    assert f == {"A": "satu", "B": "", "C": "baris 1\nbaris 2"}


def test_hitung_ikm_permenpan():
    skm = [{"body": formulir_skm([4] * 9)}, {"body": formulir_skm([3] * 8 + [2], "Masyarakat umum")},
           {"body": formulir_skm([4] * 5)}]  # tidak lengkap -> diabaikan
    h = layanan.hitung_ikm(skm)
    assert h["responden"] == 2
    # NRR: U1..U8 = 3.5, U9 = 3.0 -> IKM = (8*3.5 + 3.0)/9 * 25
    assert h["ikm"] == round((8 * 3.5 + 3.0) / 9 * 25, 2)
    assert (h["mutu"], h["kinerja"]) == ("B", "Baik")
    assert h["unsur_terendah"] == "U9" and h["per_pengguna"]["Masyarakat umum"] == 1
    assert layanan.hitung_ikm([])["ikm"] is None


def test_mutu_ikm_batas():
    assert layanan.mutu_ikm(88.31)[0] == "A" and layanan.mutu_ikm(88.30)[0] == "B"
    assert layanan.mutu_ikm(76.61)[0] == "B" and layanan.mutu_ikm(76.60)[0] == "C"
    assert layanan.mutu_ikm(64.99)[0] == "D"


def test_ringkas_pengaduan_dan_kumpulkan():
    pengaduan = [
        {"title": "a", "state": "closed", "comments": 1, "created_at": "2026-09-01T00:00:00Z", "closed_at": "2026-09-03T00:00:00Z",
         "body": "### Jenis pengaduan\n\nData terlambat / tidak diperbarui"},
        {"title": "b", "state": "open", "comments": 0, "created_at": "2026-09-10T00:00:00Z", "body": ""},
    ]

    class Klien:
        def daftar_issue(self, label):
            return {"skm": [{"body": formulir_skm([4] * 9), "created_at": "2026-09-05T00:00:00Z"}],
                    "pengaduan-data": pengaduan}[label]

    h = layanan.kumpulkan(Klien(), date(2026, 9, 29))
    assert h["ikm"] == 100.0 and h["skm_triwulan_berjalan"]["responden"] == 1
    p = h["pengaduan"]
    assert (p["total"], p["terbuka"], p["ditanggapi"], p["ditanggapi_persen"]) == (2, 1, 1, 50.0)
    assert p["median_hari_selesai"] == 2.0 and p["per_jenis"]["Data terlambat / tidak diperbarui"] == 1
    assert "GitHub Actions" in layanan.kumpulkan(None, date(2026, 9, 29))["catatan_ikm"]

    class Gagal:
        def daftar_issue(self, label):
            raise RuntimeError("HTTP 403")
    assert "Gagal" in layanan.kumpulkan(Gagal(), date(2026, 9, 29))["catatan_ikm"]

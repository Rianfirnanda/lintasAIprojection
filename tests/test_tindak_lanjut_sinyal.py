from datetime import date

from pipeline import sinyal, tindak_lanjut


def test_baca_buku_status_terakhir_dan_anomali_terlewat(tmp_path):
    (tmp_path / "tl.csv").write_text(
        "id_sinyal,status,catatan,petugas,tanggal,kode_varian,tanggal_kejadian\n"
        "abc,perlu_verifikasi,,A,2026-09-01,,\n"
        "abc,terverifikasi,cek pasar,B,2026-09-02,,\n"
        ",anomali_terlewat,lonjakan bawang,B,2026-09-03,BWM01,2026-08-20\n"
        "xyz,status_ngawur,,A,2026-09-01,,\n", encoding="utf-8")
    status, terlewat = tindak_lanjut.baca_buku(tmp_path)
    assert status["abc"].status == "terverifikasi" and len(status["abc"].riwayat) == 2
    assert "xyz" not in status
    assert terlewat == [{"kode_varian": "BWM01", "tanggal_kejadian": "2026-08-20", "catatan": "lonjakan bawang", "petugas": "B"}]


def test_status_dari_issue():
    assert tindak_lanjut.status_dari_issue({"labels": [{"name": "status: false-alarm"}], "state": "open"}) == "false_alarm"
    assert tindak_lanjut.status_dari_issue({"labels": [{"name": "sinyal-harga"}], "state": "closed"}) == "selesai"
    assert tindak_lanjut.status_dari_issue({"labels": [], "state": "open"}) == "perlu_verifikasi"


def _sinyal(id_, keparahan="tinggi", jenis="anomali_harga", aktif=True):
    return {"id": id_, "jenis": jenis, "keparahan": keparahan, "aktif": aktif, "judul": f"Sinyal {id_}",
            "tanggal_mulai": "2026-09-28", "tanggal_terakhir": "2026-09-29", "nilai_aktual": 60000, "baseline": 40000,
            "deviasi_persen": 50.0, "narasi": "konteks", "konteks": {"a": 1}}


def test_sinkronisasi_github_nonaktif_tanpa_token():
    peng = {"tindak_lanjut": {"github_issues": True, "keparahan_minimal_issue": "tinggi", "maks_issue_baru_per_jalan": 5}}
    peta, pesan = tindak_lanjut.sinkronisasi_github([_sinyal("a1")], peng, None, "o/r", True)
    assert peta == {} and "nonaktif" in pesan


def test_sinkronisasi_github_membaca_dan_membuat(monkeypatch):
    dibuat = []

    def daftar(self, label):
        return [{"body": "x <!-- id_sinyal: aaa111 -->", "labels": [{"name": "status: terverifikasi"}], "state": "open",
                 "html_url": "https://github.com/o/r/issues/1", "number": 1, "updated_at": "t"}]

    def buat(self, judul, isi, label):
        dibuat.append((judul, isi, label))
        return {"html_url": f"https://github.com/o/r/issues/{len(dibuat) + 1}", "number": len(dibuat) + 1, "created_at": "t"}

    monkeypatch.setattr(tindak_lanjut.KlienGitHub, "daftar_issue", daftar)
    monkeypatch.setattr(tindak_lanjut.KlienGitHub, "buat_issue", buat)
    monkeypatch.setattr(tindak_lanjut.KlienGitHub, "pastikan_label", lambda self: None)
    monkeypatch.setattr(tindak_lanjut.KlienGitHub, "event_issue", lambda self, n: [
        {"event": "labeled", "label": {"name": "status: terverifikasi"}, "created_at": "2026-09-02T00:00:00Z"}])
    peng = {"tindak_lanjut": {"github_issues": True, "keparahan_minimal_issue": "tinggi", "maks_issue_baru_per_jalan": 2}}
    daftar_sinyal = [_sinyal("aaa111"), _sinyal("bbb222"), _sinyal("ccc333"), _sinyal("ddd444"),
                     _sinyal("eee555", keparahan="sedang"), _sinyal("fff666", jenis="drift"), _sinyal("ggg777", aktif=False)]
    peta, pesan = tindak_lanjut.sinkronisasi_github(daftar_sinyal, peng, "token", "o/r", boleh_buat=True, url_dashboard="https://x")
    assert peta["aaa111"]["status"] == "terverifikasi" and peta["aaa111"]["direspons"] == "2026-09-02T00:00:00Z"
    assert len(dibuat) == 2  # dibatasi maks_issue_baru_per_jalan
    assert set(peta) == {"aaa111", "bbb222", "ccc333"}
    assert "<!-- id_sinyal: bbb222 -->" in dibuat[0][1] and "sinyal-harga" in dibuat[0][2]
    # mode demo: hanya membaca
    dibuat.clear()
    peta, pesan = tindak_lanjut.sinkronisasi_github(daftar_sinyal, peng, "token", "o/r", boleh_buat=False)
    assert dibuat == [] and "demo" in pesan


def test_sinkronisasi_github_galat_tidak_menggagalkan(monkeypatch):
    def gagal(self, label):
        raise RuntimeError("HTTP 403")
    monkeypatch.setattr(tindak_lanjut.KlienGitHub, "daftar_issue", gagal)
    peng = {"tindak_lanjut": {"github_issues": True, "keparahan_minimal_issue": "tinggi", "maks_issue_baru_per_jalan": 2}}
    peta, pesan = tindak_lanjut.sinkronisasi_github([_sinyal("a")], peng, "token", "o/r", True)
    assert peta == {} and "gagal" in pesan


def test_id_sinyal_stabil():
    assert sinyal.id_sinyal("anomali_harga", "CRW02", "1709", "2026-09-28") == sinyal.id_sinyal("anomali_harga", "CRW02", "1709", "2026-09-28")
    assert len(sinyal.id_sinyal("x")) == 10


def test_evaluasi_deteksi_dari_label():
    daftar = [_sinyal("a"), _sinyal("b"), _sinyal("c"), _sinyal("d")]
    status = {"a": "terverifikasi", "b": "selesai", "c": "false_alarm", "d": "baru"}
    ev = sinyal.evaluasi_deteksi(daftar, status, [{"kode_varian": "X"}], titik_dievaluasi=100)
    assert (ev["tp"], ev["fp"], ev["fn"]) == (2, 1, 1)
    assert ev["precision"] == round(2 / 3, 3) and ev["recall"] == round(2 / 3, 3)
    assert ev["false_positive_rate"] == round(1 / (1 + 96), 4)
    kosong = sinyal.evaluasi_deteksi(daftar, {}, [], 100)
    assert "catatan" in kosong and "precision" not in kosong


def test_alasan_drift():
    s_cfg = {"psi_ambang": 0.25, "rasio_volatilitas_batas": [0.5, 2.0], "alfa_uji_drift": 0.01}
    assert sinyal.alasan_drift({"psi": 0.5, "p_psi": 0.2}, s_cfg, 10) == []  # tidak signifikan
    assert len(sinyal.alasan_drift({"psi": 0.5, "p_psi": 0.001}, s_cfg, 10)) == 1
    assert len(sinyal.alasan_drift({"rasio_volatilitas": 3.0, "p_volatilitas": 0.001}, s_cfg, 10)) == 1
    assert len(sinyal.alasan_drift({"penurunan_periode_terakhir_persen": 30, "penurunan_periode_sebelumnya_persen": 12}, s_cfg, 10)) == 1
    assert sinyal.alasan_drift({"penurunan_periode_terakhir_persen": 30, "penurunan_periode_sebelumnya_persen": 5}, s_cfg, 10) == []


def test_sinyal_data_terlambat(konf):
    ketepatan = {"per_pasar": [
        {"kode_pasar": "PSR01", "nama_pasar": "Pasar A", "tanggal_terakhir": "2026-09-28", "blank_spot": False},
        {"kode_pasar": "PSR02", "nama_pasar": "Pasar B", "tanggal_terakhir": "2026-09-21", "blank_spot": True},
    ]}
    daftar = sinyal.bentuk_sinyal(konf, {}, {}, sinyal.IndeksKonteks([]), ketepatan, date(2026, 9, 28))
    assert [s["kode_pasar"] for s in daftar] == ["PSR02"]
    assert daftar[0]["jenis"] == "data_terlambat" and "blank spot" in daftar[0]["narasi"]

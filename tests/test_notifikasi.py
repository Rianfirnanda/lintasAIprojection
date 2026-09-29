import json

from pipeline import notifikasi


def _s(id_, keparahan="tinggi", jenis="anomali_harga", aktif=True):
    return {"id": id_, "jenis": jenis, "keparahan": keparahan, "aktif": aktif, "judul": f"Judul {id_}",
            "narasi": "konteks", "url_issue": None}


LAPORAN = [
    {"judul": "Buletin Harga Pangan Mingguan", "label": "Minggu ke-40 2026", "periode_berjalan": True, "ringkasan": [], "rekomendasi": []},
    {"judul": "Buletin Harga Pangan Mingguan", "label": "Minggu ke-39 2026", "periode_berjalan": False,
     "ringkasan": ["Indeks 102,9"], "rekomendasi": ["Verifikasi cabai"]},
]
ENV_TG = {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "c"}


def test_tanpa_kanal_dan_demo(konf):
    assert "belum ada kanal" in notifikasi.jalankan(konf, [_s("a")], LAPORAN, "", False, env={})
    assert "mode demo" in notifikasi.jalankan(konf, [_s("a")], LAPORAN, "", True, env=ENV_TG)


def test_kirim_sekali_saja(konf, akar_sementara):
    terkirim = []
    pengirim = {"telegram": lambda token, chat, teks: terkirim.append(teks)}
    sinyal = [_s("a"), _s("b", keparahan="rendah"), _s("c", jenis="drift"), _s("d", aktif=False), _s("e", keparahan="sedang")]
    pesan = notifikasi.jalankan(konf, sinyal, LAPORAN, "https://x.github.io/r/", False, env=ENV_TG, pengirim=pengirim)
    assert "2 sinyal dikirim lewat telegram" in pesan and "buletin Minggu ke-39 2026" in pesan
    assert len(terkirim) == 2
    assert "Judul a" in terkirim[0] and "Judul e" in terkirim[0] and "Judul b" not in terkirim[0]
    assert "https://x.github.io/r/sinyal.html" in terkirim[0]
    assert "Minggu ke-39 2026" in terkirim[1] and "laporan.html" in terkirim[1]
    status = json.loads((akar_sementara / "data/notifikasi/terkirim.json").read_text())
    assert set(status["sinyal"]) == {"a", "e"} and status["buletin"] == ["Minggu ke-39 2026"]
    terkirim.clear()
    assert notifikasi.jalankan(konf, sinyal, LAPORAN, "", False, env=ENV_TG, pengirim=pengirim) == "tidak ada notifikasi baru"
    assert terkirim == []


def test_kanal_gagal_tidak_dicatat(konf, akar_sementara):
    def gagal(*a):
        raise OSError("jaringan")
    pesan = notifikasi.jalankan(konf, [_s("a")], [], "", False, env=ENV_TG, pengirim={"telegram": gagal})
    assert "gagal" in pesan
    assert not (akar_sementara / "data/notifikasi/terkirim.json").exists()


def test_kanal_email_terdeteksi():
    env = {"SMTP_HOST": "smtp.gmail.com", "SMTP_USER": "u", "SMTP_PASSWORD": "p", "EMAIL_KE": "a@b.c"}
    assert notifikasi.kanal_tersedia(env) == ["email"]
    assert notifikasi.kanal_tersedia({**env, **ENV_TG}) == ["telegram", "email"]


def test_pesan_dipotong_dan_dibatasi():
    teks = notifikasi.susun_pesan_sinyal([_s(str(i)) for i in range(15)], "", 10)
    assert "… dan 5 sinyal lainnya." in teks

import json

import pytest

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


def test_email_ke_semua_pengguna_terdaftar_tanpa_dobel():
    env = {"SMTP_HOST": "smtp.resend.com", "SMTP_USER": "resend", "SMTP_PASSWORD": "p",
           "EMAIL_KE": "kantor@contoh.go.id, A@contoh.go.id", "EMAIL_PENGGUNA": "a@contoh.go.id,b@contoh.go.id"}
    assert notifikasi.penerima_email(env) == ["kantor@contoh.go.id", "a@contoh.go.id", "b@contoh.go.id"]
    assert notifikasi.penerima_email(env, ke_pengguna=False) == ["kantor@contoh.go.id", "a@contoh.go.id"]
    # cukup pengguna terdaftar, tanpa EMAIL_KE
    tanpa_ke = {k: v for k, v in env.items() if k != "EMAIL_KE"}
    assert notifikasi.kanal_tersedia(tanpa_ke) == ["email"]
    assert notifikasi.kanal_tersedia(tanpa_ke, ke_pengguna=False) == []


class _SmtpPalsu:
    def __init__(self, *a, **k):
        self.terkirim = []
        _SmtpPalsu.terakhir = self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, **k):
        pass

    def login(self, u, p):
        self.masuk = (u, p)

    def send_message(self, pesan):
        if pesan["To"] == "ditolak@contoh.go.id":
            import smtplib
            raise smtplib.SMTPRecipientsRefused({pesan["To"]: (550, b"ditolak")})
        self.terkirim.append(pesan)


def test_kirim_email_satu_per_penerima(monkeypatch):
    monkeypatch.setattr(notifikasi.smtplib, "SMTP_SSL", _SmtpPalsu)
    env = {"SMTP_HOST": "smtp.resend.com", "SMTP_PORT": "465", "SMTP_USER": "resend", "SMTP_PASSWORD": "p",
           "EMAIL_DARI": "onboarding@resend.dev"}
    n = notifikasi.kirim_email(env, "Subjek", "Isi", ["a@contoh.go.id", "ditolak@contoh.go.id", "b@contoh.go.id"])
    s = _SmtpPalsu.terakhir
    # tiap orang menerima email sendiri: alamat pengguna lain tidak terlihat; satu alamat ditolak tidak menghentikan yang lain
    assert n == 2 and [p["To"] for p in s.terkirim] == ["a@contoh.go.id", "b@contoh.go.id"]
    assert all(p["From"] == "onboarding@resend.dev" and "Bcc" not in p for p in s.terkirim)
    with pytest.raises(RuntimeError):
        notifikasi.kirim_email(env, "S", "I", ["ditolak@contoh.go.id"])


def test_email_pengguna_aktif_dari_firestore():
    from pipeline import firestore_sinkron as fs

    class Dok:
        def __init__(self, d):
            self.d = d

        def to_dict(self):
            return self.d

    class Db:
        def collection(self, nama):
            assert nama == "lbp_pengguna"
            return type("K", (), {"stream": lambda _s: [
                Dok({"email": "B@contoh.go.id", "status": "aktif"}), Dok({"email": "a@contoh.go.id", "status": "aktif"}),
                Dok({"email": "tunggu@contoh.go.id", "status": "menunggu"}), Dok({"email": "x@contoh.go.id", "status": "ditolak"}),
                Dok({"email": "bukan-email", "status": "aktif"}), Dok({"status": "aktif"})]})()
    assert fs.email_pengguna_aktif(Db()) == ["a@contoh.go.id", "b@contoh.go.id"]


# ---------------------------------------------------------------- uji kirim dan galat Telegram yang jelas

class TelegramTiruan:
    """Bot API palsu: getMe, sendMessage (gagal untuk chat yang tidak dikenal), getUpdates."""

    def __init__(self, token_sah="123:abc", chat_dikenal=("-1001",), pembaruan=None):
        self.token_sah, self.chat_dikenal, self.pembaruan, self.terkirim = token_sah, set(chat_dikenal), pembaruan or [], []

    def __call__(self, token, metode, data=None, batas_waktu=30):
        if token != self.token_sah:
            raise notifikasi.GalatTelegram("Unauthorized", 401)
        if metode == "getMe":
            return {"username": "takar_pangan_bot"}
        if metode == "sendMessage":
            if data["chat_id"] not in self.chat_dikenal:
                raise notifikasi.GalatTelegram("Bad Request: chat not found", 400)
            self.terkirim.append(data)
            return {"message_id": 1}
        if metode == "getUpdates":
            return self.pembaruan
        raise AssertionError(metode)


PEMBARUAN = [{"message": {"chat": {"id": 555123, "type": "private", "first_name": "Rian", "last_name": "F"}}},
             {"my_chat_member": {"chat": {"id": -1001, "type": "supergroup", "title": "TPID Benteng"}}},
             {"message": {"chat": {"id": 555123, "type": "private", "first_name": "Rian"}}}]


def test_uji_kanal_berhasil_dan_gagal_dengan_alasan_dan_daftar_obrolan():
    tg = TelegramTiruan()
    h = notifikasi.uji_kanal({"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "-1001"}, "17-10-2026 08.00 WIB", panggil=tg)
    assert h["ok"] and h["telegram"]["ok"] and "@takar_pangan_bot" in h["ringkas"] and h["obrolan"] == []
    assert "Uji notifikasi" in tg.terkirim[0]["text"]
    # ID obrolan salah: alasan Telegram ditampilkan apa adanya beserta sarannya, dan obrolan yang pernah menghubungi bot didaftar
    tg = TelegramTiruan(pembaruan=PEMBARUAN)
    h = notifikasi.uji_kanal({"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "@rian"}, panggil=tg)
    assert not h["ok"] and "chat not found" in h["telegram"]["pesan"] and "Start" in h["telegram"]["pesan"]
    assert {o["id"]: (o["jenis"], o["nama"]) for o in h["obrolan"]} == {"555123": ("pribadi", "Rian"), "-1001": ("grup", "TPID Benteng")}
    # ringkasan untuk catatan proses publik tidak memuat ID atau nama obrolan
    assert "555123" not in h["ringkas"] and "TPID Benteng" not in h["ringkas"] and "2 obrolan" in h["ringkas"]
    # token salah
    h = notifikasi.uji_kanal({"TELEGRAM_BOT_TOKEN": "999:x", "TELEGRAM_CHAT_ID": "-1001"}, panggil=TelegramTiruan())
    assert not h["ok"] and "@BotFather" in h["telegram"]["pesan"]
    # token benar, ID belum diisi, belum ada yang menghubungi bot
    h = notifikasi.uji_kanal({"TELEGRAM_BOT_TOKEN": "123:abc"}, panggil=TelegramTiruan())
    assert "belum diisi" in h["telegram"]["pesan"] and "tekan Start" in h["ringkas"]
    # tanpa kanal sama sekali
    assert "Belum ada kanal" in notifikasi.uji_kanal({})["ringkas"]


def test_uji_kanal_email():
    env = {"SMTP_HOST": "smtp.x", "SMTP_USER": "u", "SMTP_PASSWORD": "p", "EMAIL_KE": "a@x.go.id, b@x.go.id"}
    dikirim = []
    h = notifikasi.uji_kanal(env, kirim_surel=lambda e, subjek, teks, penerima: dikirim.append(penerima) or len(penerima))
    assert h["ok"] and h["email"]["pesan"] == "Email uji terkirim ke 2 alamat." and dikirim == [["a@x.go.id", "b@x.go.id"]]
    h = notifikasi.uji_kanal(env, kirim_surel=lambda *a: (_ for _ in ()).throw(RuntimeError("login ditolak")))
    assert not h["ok"] and "login ditolak" in h["email"]["pesan"]


def test_galat_http_telegram_dibaca_alasannya(monkeypatch):
    import io
    import urllib.error

    def buka(req, timeout=30):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(
            json.dumps({"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}).encode()))

    monkeypatch.setattr(notifikasi.urllib.request, "urlopen", buka)
    with pytest.raises(notifikasi.GalatTelegram) as e:
        notifikasi.kirim_telegram("123:abc", "@salah", "halo")
    assert e.value.deskripsi == "Bad Request: chat not found" and e.value.kode == 400 and "123:abc" not in str(e.value)


def test_tombol_kirim_pesan_uji_dari_situs_mencatat_hasil_untuk_admin(akar_sementara, monkeypatch, capsys):
    from pipeline import __main__ as m
    from pipeline import firestore_sinkron as fs

    dicatat = {}
    monkeypatch.setattr(fs, "pasang_rahasia_dari_firestore", lambda akar: [])
    monkeypatch.setattr(fs, "catat_perintah", lambda jenis, url, **kolom: dicatat.update(jenis=jenis, url=url, **kolom))
    monkeypatch.setattr(notifikasi, "uji_kanal", lambda env, waktu, ke_pengguna=True: {
        "ok": False, "ringkas": "Telegram: gagal. Telegram menolak: Bad Request: chat not found.",
        "obrolan": [{"id": "555123", "jenis": "pribadi", "nama": "Rian"}]})
    m._uji_notifikasi_dari_situs(akar_sementara, "https://github.com/x/y/actions/runs/9")
    assert dicatat["jenis"] == "uji_notifikasi" and dicatat["status"] == "gagal" and dicatat["obrolan"][0]["id"] == "555123"
    keluaran = capsys.readouterr().out
    assert "chat not found" in keluaran and "555123" not in keluaran  # ID obrolan tidak masuk catatan proses publik

"""Notifikasi sinyal prioritas dan buletin mingguan ke Telegram dan/atau email (gratis).

Kanal diaktifkan lewat GitHub Secrets:
  Telegram : TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (bot dibuat lewat @BotFather, tambahkan ke grup TPID)
  Email    : SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_DARI (opsional), dan penerima:
             semua pengguna aktif (EMAIL_PENGGUNA, diisi mesin dari Firestore; bisa dimatikan lewat
             notifikasi.email_ke_pengguna) ditambah EMAIL_KE (pisahkan dengan koma). Tiap penerima mendapat email
             sendiri, jadi alamat sesama pengguna tidak saling terlihat.

Sinyal yang sudah dikirim dicatat di data/notifikasi/terkirim.json (di-commit oleh GitHub Actions) agar tidak dobel.
Mode demo tidak mengirim notifikasi kecuali notifikasi.kirim_saat_demo = true.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path

log = logging.getLogger(__name__)

TINGKAT = {"rendah": 0, "sedang": 1, "tinggi": 2}
BAWAAN = {
    "aktif": True,
    "keparahan_minimal": "sedang",
    "jenis": ["anomali_harga", "proyeksi_naik", "risiko_hari_raya", "data_terlambat", "data_beku"],
    "maks_sinyal_per_pesan": 10,
    "email_ke_pengguna": True,
    "buletin_mingguan": True,
    "kirim_saat_demo": False,
}
BATAS_TELEGRAM = 4000
LABEL_JENIS = {"anomali_harga": "Anomali harga", "proyeksi_naik": "Proyeksi naik", "risiko_hari_raya": "Risiko hari raya",
               "data_terlambat": "Data terlambat", "data_beku": "Data tidak diperbarui", "drift": "Drift"}


def baca_status(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"sinyal": {}, "buletin": []}


def simpan_status(path: Path, status: dict, hari_ini: date, simpan_hari: int = 180) -> None:
    batas = (hari_ini - timedelta(days=simpan_hari)).isoformat()
    status["sinyal"] = {k: v for k, v in status["sinyal"].items() if v >= batas}
    status["buletin"] = status["buletin"][-30:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def pilih_sinyal(sinyal: list[dict], sudah: dict, cfg: dict) -> list[dict]:
    minimal = TINGKAT[cfg["keparahan_minimal"]]
    return [
        s for s in sinyal
        if s.get("aktif") and s["jenis"] in cfg["jenis"] and TINGKAT[s["keparahan"]] >= minimal and s["id"] not in sudah
    ]


def susun_pesan_sinyal(sinyal: list[dict], url: str, maks: int) -> str:
    baris = [f"Sinyal harga pangan Kab. Bengkulu Tengah ({len(sinyal)} baru)", ""]
    for s in sinyal[:maks]:
        baris.append(f"• [{s['keparahan'].upper()}] {LABEL_JENIS.get(s['jenis'], s['jenis'])}: {s['judul']}")
        if s.get("narasi"):
            baris.append(f"  {s['narasi'][:280]}")
        if s.get("url_issue"):
            baris.append(f"  Tindak lanjut: {s['url_issue']}")
    if len(sinyal) > maks:
        baris.append(f"… dan {len(sinyal) - maks} sinyal lainnya.")
    baris += ["", "Sinyal wajib diverifikasi sebelum menjadi dasar keputusan."]
    if url:
        baris.append(f"Dashboard: {url}sinyal.html")
    return "\n".join(baris)


def susun_pesan_buletin(periode: dict, url: str) -> str:
    baris = [f"{periode['judul']}, {periode['label']}", ""]
    baris += [f"• {r}" for r in periode["ringkasan"]]
    if periode.get("rekomendasi"):
        baris += ["", "Rekomendasi (bahan pertimbangan):"]
        baris += [f"{i}. {r}" for i, r in enumerate(periode["rekomendasi"][:5], 1)]
    if url:
        baris += ["", f"Buletin lengkap (bisa dicetak/PDF): {url}laporan.html"]
    return "\n".join(baris)


# Penjelasan galat Telegram dalam bahasa sederhana (dicocokkan dengan teks "description" dari Telegram).
SARAN_TELEGRAM = [
    ("chat not found", "ID obrolan tidak dikenal bot. Buka bot di Telegram lalu tekan Start (untuk pesan pribadi), atau masukkan "
                       "bot ke grup lalu kirim satu pesan di grup itu. Setelah itu isi ID obrolan yang benar (lihat daftar di bawah)."),
    ("bot was blocked", "Bot diblokir oleh penerima. Buka bot di Telegram, buka blokirnya, lalu tekan Start lagi."),
    ("bot was kicked", "Bot sudah dikeluarkan dari grup. Masukkan lagi bot ke grup tujuan."),
    ("bot is not a member", "Bot belum dimasukkan ke grup atau kanal tujuan."),
    ("not enough rights", "Bot belum boleh mengirim pesan di grup atau kanal ini. Jadikan bot admin atau beri izin mengirim pesan."),
    ("can't initiate conversation", "Penerima belum pernah membuka bot. Buka bot di Telegram lalu tekan Start."),
    ("chat_id is empty", "ID obrolan masih kosong."),
    ("unauthorized", "Token bot ditolak Telegram. Salin ulang token dari @BotFather."),
    ("not found", "Token bot tidak dikenal Telegram. Salin ulang token dari @BotFather."),
]


class GalatTelegram(RuntimeError):
    def __init__(self, deskripsi: str, kode: int | None = None):
        self.deskripsi, self.kode = deskripsi, kode
        cocok = next((saran for kunci, saran in SARAN_TELEGRAM if kunci in deskripsi.lower()), "")
        self.saran = cocok
        super().__init__(f"Telegram menolak: {deskripsi}." + (f" {cocok}" if cocok else ""))


def panggil_telegram(token: str, metode: str, data: dict | None = None, batas_waktu: int = 30) -> dict:
    """Panggil Bot API Telegram. Galat dari Telegram dilempar sebagai GalatTelegram berisi alasan aslinya (mis.
    "Bad Request: chat not found"), bukan hanya "HTTP Error 400"."""
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{metode}", method="POST" if data is not None else "GET",
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=batas_waktu) as r:
            hasil = json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            isi = json.loads(e.read().decode("utf-8", "replace"))
            raise GalatTelegram(str(isi.get("description") or e), e.code) from None
        except (ValueError, AttributeError):
            raise GalatTelegram(f"HTTP {e.code}", e.code) from None
    if not hasil.get("ok"):
        raise GalatTelegram(str(hasil.get("description") or hasil))
    return hasil.get("result")


def kirim_telegram(token: str, chat_id: str, teks: str) -> None:
    for i in range(0, len(teks), BATAS_TELEGRAM):
        panggil_telegram(token, "sendMessage", {"chat_id": chat_id, "text": teks[i:i + BATAS_TELEGRAM],
                                                 "disable_web_page_preview": True})


def obrolan_bot(token: str, panggil=panggil_telegram) -> list[dict]:
    """Obrolan yang baru-baru ini mengirim pesan ke bot (dari getUpdates): untuk menemukan ID obrolan yang benar."""
    try:
        pembaruan = panggil(token, "getUpdates", {"limit": 100, "allowed_updates": ["message", "my_chat_member", "channel_post"]})
    except GalatTelegram:
        return []
    hasil: dict[str, dict] = {}
    for u in pembaruan or []:
        for kunci in ("message", "channel_post", "my_chat_member", "edited_message"):
            chat = (u.get(kunci) or {}).get("chat")
            if not chat or "id" not in chat:
                continue
            nama = chat.get("title") or " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x) or chat.get("username") or ""
            hasil[str(chat["id"])] = {"id": str(chat["id"]), "jenis": {"private": "pribadi", "group": "grup", "supergroup": "grup",
                                                                        "channel": "kanal"}.get(chat.get("type"), chat.get("type", "")),
                                      "nama": nama[:80]}
    return list(hasil.values())[:10]


def uji_kanal(env: dict, sekarang: str = "", panggil=panggil_telegram, kirim_surel=None, ke_pengguna: bool = True) -> dict:
    """Kirim pesan uji ke tiap kanal yang kuncinya terisi. Mengembalikan hasil per kanal dengan alasan bila gagal dan,
    untuk Telegram, daftar obrolan yang pernah menghubungi bot (supaya ID obrolan yang benar mudah dipilih).
    Ringkasan (`ringkas`) tidak memuat ID atau nama obrolan, jadi aman ditulis di catatan proses publik."""
    hasil: dict = {"telegram": None, "email": None, "obrolan": [], "bot": ""}
    teks = ("Uji notifikasi Takar Pangan 10\u202221 berhasil. Peringatan harga pangan penting untuk Kabupaten Bengkulu Tengah "
            "akan dikirim ke obrolan ini." + (f" ({sekarang})" if sekarang else ""))
    token, chat = (env.get("TELEGRAM_BOT_TOKEN") or "").strip(), (env.get("TELEGRAM_CHAT_ID") or "").strip()
    if token:
        try:
            bot = panggil(token, "getMe") or {}
            hasil["bot"] = bot.get("username", "")
            if not chat:
                hasil["telegram"] = {"ok": False, "pesan": "Token bot benar, tetapi ID obrolan belum diisi."}
            else:
                panggil(token, "sendMessage", {"chat_id": chat, "text": teks, "disable_web_page_preview": True})
                hasil["telegram"] = {"ok": True, "pesan": f"Pesan uji terkirim lewat bot @{hasil['bot']}." if hasil["bot"] else "Pesan uji terkirim."}
        except GalatTelegram as e:
            hasil["telegram"] = {"ok": False, "pesan": str(e)}
        if hasil["telegram"] and not hasil["telegram"]["ok"]:
            hasil["obrolan"] = obrolan_bot(token, panggil)
    if all(env.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")):
        penerima = penerima_email(env, ke_pengguna)
        if not penerima:
            hasil["email"] = {"ok": False, "pesan": "Akun email pengirim sudah diisi, tetapi belum ada alamat penerima."}
        else:
            try:
                n = (kirim_surel or kirim_email)(env, "[Uji] Notifikasi Takar Pangan 10\u202221", teks, penerima)
                hasil["email"] = {"ok": True, "pesan": f"Email uji terkirim ke {n} alamat."}
            except Exception as e:  # noqa: BLE001
                hasil["email"] = {"ok": False, "pesan": f"Email uji gagal: {e}"[:300]}
    bagian = []
    for nama, label in (("telegram", "Telegram"), ("email", "Email")):
        h = hasil[nama]
        if h:
            bagian.append(f"{label}: {'berhasil' if h['ok'] else 'gagal'}. {h['pesan']}")
    if hasil["obrolan"]:
        bagian.append(f"Ada {len(hasil['obrolan'])} obrolan yang pernah menghubungi bot; pilih ID yang benar di halaman Pengaturan.")
    elif hasil["telegram"] and not hasil["telegram"]["ok"] and token:
        bagian.append("Belum ada obrolan yang menghubungi bot. Buka bot di Telegram dan tekan Start, atau kirim pesan di grup yang "
                      "sudah berisi bot, lalu jalankan uji lagi.")
    hasil["ok"] = any(h and h["ok"] for h in (hasil["telegram"], hasil["email"]))
    hasil["ringkas"] = " ".join(bagian) or "Belum ada kanal notifikasi: isi token bot dan ID obrolan Telegram, atau akun email, di Pengaturan."
    return hasil


def _daftar(teks: str | None) -> list[str]:
    return [x.strip().lower() for x in (teks or "").split(",") if "@" in x]


def penerima_email(env: dict, ke_pengguna: bool = True) -> list[str]:
    """EMAIL_KE ditambah (bila diaktifkan) email semua pengguna aktif, tanpa dobel."""
    semua = _daftar(env.get("EMAIL_KE")) + (_daftar(env.get("EMAIL_PENGGUNA")) if ke_pengguna else [])
    return list(dict.fromkeys(semua))


def kirim_email(env: dict, subjek: str, teks: str, penerima: list[str] | None = None) -> int:
    """Kirim satu email ke tiap penerima (alamat sesama penerima tidak terlihat). Kembalikan jumlah yang terkirim."""
    penerima = penerima if penerima is not None else penerima_email(env)
    pengirim = env.get("EMAIL_DARI") or env["SMTP_USER"]
    port = int(env.get("SMTP_PORT") or 465)
    konteks = ssl.create_default_context()
    if port == 465:
        s = smtplib.SMTP_SSL(env["SMTP_HOST"], port, context=konteks, timeout=30)
    else:
        s = smtplib.SMTP(env["SMTP_HOST"], port, timeout=30)
        s.starttls(context=konteks)
    terkirim, gagal = 0, []
    with s:
        s.login(env["SMTP_USER"], env["SMTP_PASSWORD"])
        for alamat in penerima:
            pesan = EmailMessage()
            pesan["Subject"] = subjek
            pesan["From"] = pengirim
            pesan["To"] = alamat
            pesan.set_content(teks)
            try:
                s.send_message(pesan)
                terkirim += 1
            except smtplib.SMTPException as e:  # satu alamat ditolak tidak menghentikan yang lain
                gagal.append(f"{alamat}: {e}")
    if gagal:
        log.warning("email tidak terkirim ke %d alamat: %s", len(gagal), "; ".join(gagal)[:500])
    if not terkirim:
        raise RuntimeError("email tidak terkirim ke siapa pun")
    return terkirim


def kanal_tersedia(env: dict, ke_pengguna: bool = True) -> list[str]:
    kanal = []
    if env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID"):
        kanal.append("telegram")
    if all(env.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")) and penerima_email(env, ke_pengguna):
        kanal.append("email")
    return kanal


def _kirim(kanal: list[str], env: dict, subjek: str, teks: str, pengirim: dict | None, ke_pengguna: bool = True) -> list[str]:
    pengirim = pengirim or {}
    berhasil = []
    for k in kanal:
        try:
            if k == "telegram":
                (pengirim.get("telegram") or kirim_telegram)(env["TELEGRAM_BOT_TOKEN"], env["TELEGRAM_CHAT_ID"], teks)
            else:
                (pengirim.get("email") or kirim_email)(env, subjek, teks, penerima_email(env, ke_pengguna))
            berhasil.append(k)
        except Exception as e:  # jangan gagalkan pipeline karena kanal notifikasi bermasalah
            log.warning("gagal mengirim notifikasi lewat %s: %s", k, e)
    return berhasil


def jalankan(konf, sinyal: list[dict], laporan_mingguan: list[dict], url_dashboard: str, demo: bool,
             env: dict | None = None, pengirim: dict | None = None) -> str:
    """Kirim notifikasi yang belum pernah terkirim. Kembalikan pesan status untuk dicatat di meta.json."""
    cfg = {**BAWAAN, **konf.pengaturan.get("notifikasi", {})}
    env = env if env is not None else dict(os.environ)
    if not cfg["aktif"]:
        return "notifikasi dimatikan di pengaturan"
    if demo and not cfg["kirim_saat_demo"]:
        return "notifikasi tidak dikirim dalam mode demo"
    ke_pengguna = bool(cfg["email_ke_pengguna"])
    kanal = kanal_tersedia(env, ke_pengguna)
    if not kanal:
        return "belum ada kanal notifikasi (atur secret Telegram atau SMTP)"

    path = konf.akar / "data" / "notifikasi" / "terkirim.json"
    status = baca_status(path)
    catatan = []
    berubah = False
    baru = pilih_sinyal(sinyal, status["sinyal"], cfg)
    if baru:
        teks = susun_pesan_sinyal(baru, url_dashboard, cfg["maks_sinyal_per_pesan"])
        ok = _kirim(kanal, env, f"[Sinyal harga] {len(baru)} sinyal baru di Kab. Bengkulu Tengah", teks, pengirim, ke_pengguna)
        if ok:
            for s in baru:
                status["sinyal"][s["id"]] = konf.hari_ini.isoformat()
            berubah = True
            catatan.append(f"{len(baru)} sinyal dikirim lewat {', '.join(ok)}")
        else:
            catatan.append("pengiriman sinyal gagal di semua kanal")

    # Buletin mingguan: kirim sekali untuk minggu terakhir yang sudah lengkap.
    selesai = [p for p in laporan_mingguan if not p.get("periode_berjalan")]
    if cfg["buletin_mingguan"] and selesai and selesai[0]["label"] not in status["buletin"]:
        p = selesai[0]
        ok = _kirim(kanal, env, f"{p['judul']}, {p['label']}", susun_pesan_buletin(p, url_dashboard), pengirim, ke_pengguna)
        if ok:
            status["buletin"].append(p["label"])
            berubah = True
            catatan.append(f"buletin {p['label']} dikirim lewat {', '.join(ok)}")

    if berubah:
        simpan_status(path, status, konf.hari_ini)
    return "; ".join(catatan) or "tidak ada notifikasi baru"

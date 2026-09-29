"""Notifikasi sinyal prioritas dan buletin mingguan ke Telegram dan/atau email (gratis).

Kanal diaktifkan lewat GitHub Secrets:
  Telegram : TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (bot dibuat lewat @BotFather, tambahkan ke grup TPID)
  Email    : SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_KE (pisahkan dengan koma), EMAIL_DARI (opsional)

Sinyal yang sudah dikirim dicatat di data/notifikasi/terkirim.json (di-commit oleh GitHub Actions) agar tidak dobel.
Mode demo tidak mengirim notifikasi kecuali notifikasi.kirim_saat_demo = true.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
import urllib.request
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path

log = logging.getLogger(__name__)

TINGKAT = {"rendah": 0, "sedang": 1, "tinggi": 2}
BAWAAN = {
    "aktif": True,
    "keparahan_minimal": "sedang",
    "jenis": ["anomali_harga", "proyeksi_naik", "risiko_hari_raya", "data_terlambat"],
    "maks_sinyal_per_pesan": 10,
    "buletin_mingguan": True,
    "kirim_saat_demo": False,
}
BATAS_TELEGRAM = 4000
LABEL_JENIS = {"anomali_harga": "Anomali harga", "proyeksi_naik": "Proyeksi naik", "risiko_hari_raya": "Risiko hari raya",
               "data_terlambat": "Data terlambat", "drift": "Drift"}


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


def kirim_telegram(token: str, chat_id: str, teks: str) -> None:
    for i in range(0, len(teks), BATAS_TELEGRAM):
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", method="POST",
            data=json.dumps({"chat_id": chat_id, "text": teks[i:i + BATAS_TELEGRAM],
                             "disable_web_page_preview": True}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            hasil = json.loads(r.read())
            if not hasil.get("ok"):
                raise RuntimeError(f"Telegram menolak pesan: {hasil}")


def kirim_email(env: dict, subjek: str, teks: str) -> None:
    pesan = EmailMessage()
    pesan["Subject"] = subjek
    pesan["From"] = env.get("EMAIL_DARI") or env["SMTP_USER"]
    pesan["To"] = ", ".join(x.strip() for x in env["EMAIL_KE"].split(",") if x.strip())
    pesan.set_content(teks)
    port = int(env.get("SMTP_PORT") or 465)
    konteks = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(env["SMTP_HOST"], port, context=konteks, timeout=30) as s:
            s.login(env["SMTP_USER"], env["SMTP_PASSWORD"])
            s.send_message(pesan)
    else:
        with smtplib.SMTP(env["SMTP_HOST"], port, timeout=30) as s:
            s.starttls(context=konteks)
            s.login(env["SMTP_USER"], env["SMTP_PASSWORD"])
            s.send_message(pesan)


def kanal_tersedia(env: dict) -> list[str]:
    kanal = []
    if env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID"):
        kanal.append("telegram")
    if all(env.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_KE")):
        kanal.append("email")
    return kanal


def _kirim(kanal: list[str], env: dict, subjek: str, teks: str, pengirim: dict | None) -> list[str]:
    pengirim = pengirim or {}
    berhasil = []
    for k in kanal:
        try:
            if k == "telegram":
                (pengirim.get("telegram") or kirim_telegram)(env["TELEGRAM_BOT_TOKEN"], env["TELEGRAM_CHAT_ID"], teks)
            else:
                (pengirim.get("email") or kirim_email)(env, subjek, teks)
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
    kanal = kanal_tersedia(env)
    if not kanal:
        return "belum ada kanal notifikasi (atur secret Telegram atau SMTP)"

    path = konf.akar / "data" / "notifikasi" / "terkirim.json"
    status = baca_status(path)
    catatan = []
    berubah = False
    baru = pilih_sinyal(sinyal, status["sinyal"], cfg)
    if baru:
        teks = susun_pesan_sinyal(baru, url_dashboard, cfg["maks_sinyal_per_pesan"])
        ok = _kirim(kanal, env, f"[Sinyal harga] {len(baru)} sinyal baru di Kab. Bengkulu Tengah", teks, pengirim)
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
        ok = _kirim(kanal, env, f"{p['judul']}, {p['label']}", susun_pesan_buletin(p, url_dashboard), pengirim)
        if ok:
            status["buletin"].append(p["label"])
            berubah = True
            catatan.append(f"buletin {p['label']} dikirim lewat {', '.join(ok)}")

    if berubah:
        simpan_status(path, status, konf.hari_ini)
    return "; ".join(catatan) or "tidak ada notifikasi baru"

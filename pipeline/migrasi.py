"""Alat bantu pindah ke proyek Firebase baru. Panduan lengkapnya ada di docs/Panduan_Migrasi_Takar_Pangan.pdf.

Dijalankan lewat alur kerja "Migrasi ke proyek baru" (migrasi.yml) dengan Secret sementara FIREBASE_SERVICE_ACCOUNT_LAMA,
yaitu kunci akun layanan proyek lama. Ada dua pekerjaan:

  salin-akun  Akun login (Firebase Authentication) dan koleksi lbp_pengguna, lbp_akses, serta lbp_jejak disalin dari proyek
              lama ke proyek baru dengan UID yang sama. Peran, izin per orang, tabel hak akses, pendaftaran otomatis, dan
              jejak tindakan admin tetap seperti semula, dan orang cukup masuk lagi dengan akun Google yang sama. Proyek
              lama hanya dibaca. Yang sudah ada di proyek baru tidak ditimpa, jadi aman dijalankan ulang.
  pengalih    Situs kecil untuk alamat lama: setiap halaman diarahkan ke halaman yang sama di alamat baru, dan service
              worker lama dicabut supaya aplikasi yang terpasang di ponsel tidak terus membuka salinan lama.

Data lain (harga, keputusan, kebijakan, rapat, pengaturan) sudah tersimpan di repositori dan ikut pindah bersamanya.
Keluaran hanya berisi jumlah, tanpa nama atau email, karena log GitHub Actions repositori ini terbuka untuk umum.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

KOLEKSI_AKUN = ("lbp_pengguna", "lbp_akses", "lbp_jejak")
LINGKUP = ("https://www.googleapis.com/auth/cloud-platform", "https://www.googleapis.com/auth/firebase",
           "https://www.googleapis.com/auth/identitytoolkit")
MAKS_AKUN = 1000  # batas satu permintaan accounts:batchGet dan accounts:batchCreate
MAKS_TULIS = 400  # di bawah batas 500 tulisan per batch Firestore
_SITUS = re.compile(r"[a-z0-9][a-z0-9-]{2,62}")
_HOST = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+")
_JALUR = re.compile(r"[A-Za-z0-9._~/-]*")
_EMAIL = re.compile(r"[^\s@\"'<>]+@[^\s@\"'<>]+\.[A-Za-z]{2,}")


def samarkan_email(teks: str) -> str:
    """Pesan galat dari Google bisa memuat email. Log repositori ini publik, jadi email diganti tanda."""
    return _EMAIL.sub("[email]", teks)


# ---------------------------------------------------------------- kunci dan sambungan

def baca_kunci(path: Path) -> dict:
    """Isi berkas kunci akun layanan. Hanya jenis dan project_id yang diperiksa; isinya tidak pernah dicetak."""
    nama = Path(path).name
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ValueError(f"Berkas kunci {nama} kosong atau bukan JSON. Tempel seluruh isi berkas kunci ke Secret.") from None
    if not isinstance(data, dict) or data.get("type") != "service_account" or not data.get("project_id"):
        raise ValueError(f"Berkas kunci {nama} bukan kunci akun layanan Google (harus memuat \"type\": \"service_account\").")
    return data


def _emulator_auth() -> str:
    return (os.environ.get("FIREBASE_AUTH_EMULATOR_HOST") or "").strip()


def sesi_auth(kunci: dict):
    """Sesi HTTP ke Firebase Authentication atas nama akun layanan, atau ke emulator saat diuji."""
    if _emulator_auth():
        import requests  # noqa: PLC0415

        sesi = requests.Session()
        sesi.headers["Authorization"] = "Bearer owner"
        return sesi
    from google.auth.transport.requests import AuthorizedSession  # noqa: PLC0415
    from google.oauth2 import service_account  # noqa: PLC0415

    return AuthorizedSession(service_account.Credentials.from_service_account_info(kunci, scopes=LINGKUP))


def klien_firestore(kunci: dict):
    """Klien Firestore untuk satu proyek. Dua proyek dipakai sekaligus, jadi kredensial diberikan langsung."""
    from google.cloud import firestore  # noqa: PLC0415

    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        from google.auth.credentials import AnonymousCredentials  # noqa: PLC0415

        return firestore.Client(project=kunci["project_id"], credentials=AnonymousCredentials())
    from google.oauth2 import service_account  # noqa: PLC0415

    return firestore.Client(project=kunci["project_id"], credentials=service_account.Credentials.from_service_account_info(kunci))


def _alamat_auth(proyek: str, aksi: str) -> str:
    host = _emulator_auth()
    dasar = f"http://{host}/identitytoolkit.googleapis.com" if host else "https://identitytoolkit.googleapis.com"
    return f"{dasar}/v1/projects/{proyek}/accounts:{aksi}"


def _periksa(r, langkah: str, saran: str) -> None:
    if r.status_code < 400:
        return
    try:
        pesan = (r.json().get("error") or {}).get("message", "")
    except ValueError:
        pesan = r.text[:200]
    tambahan = f" {saran}" if r.status_code in (401, 403) else ""
    raise RuntimeError(samarkan_email(f"{langkah} gagal ({r.status_code}): {pesan}.{tambahan}"))


# ---------------------------------------------------------------- akun login

def daftar_akun(sesi, proyek: str, saran: str = "") -> list[dict]:
    """Semua akun login satu proyek (accounts:batchGet, per 1.000 akun)."""
    akun, token = [], ""
    while True:
        params = {"maxResults": MAKS_AKUN}
        if token:
            params["nextPageToken"] = token
        r = sesi.get(_alamat_auth(proyek, "batchGet"), params=params, timeout=60)
        _periksa(r, f"Membaca akun login proyek {proyek}", saran)
        isi = r.json()
        halaman = isi.get("users") or []
        akun.extend(halaman)
        token = isi.get("nextPageToken") or ""
        if not token or not halaman:
            return akun


def rekam_impor(u: dict) -> dict:
    """Satu akun dari accounts:batchGet menjadi rekaman accounts:batchCreate, dengan bentuk yang sama seperti
    ImportUserRecord di firebase-admin. Akun Google dikenali dari providerUserInfo (rawId), jadi UID-nya tetap."""
    hasil = {k: u[k] for k in ("localId", "email", "displayName", "photoUrl", "phoneNumber", "customAttributes") if u.get(k)}
    hasil["emailVerified"] = bool(u.get("emailVerified"))
    hasil["disabled"] = bool(u.get("disabled"))
    for k in ("createdAt", "lastLoginAt"):
        if str(u.get(k) or "").isdigit():
            hasil[k] = int(u[k])
    # Sandi (penyedia "password") tidak bisa dipindah tanpa kunci hash proyek lama. Sistem ini hanya memakai login Google.
    penyedia = [{k: p[k] for k in ("rawId", "providerId", "displayName", "email", "photoUrl") if p.get(k)}
                for p in u.get("providerUserInfo") or []
                if p.get("rawId") and p.get("providerId") and p["providerId"] not in ("password", "phone")]
    if penyedia:
        hasil["providerUserInfo"] = penyedia
    return hasil


def _penyedia(u: dict) -> set[tuple[str, str]]:
    return {(p.get("providerId"), p.get("rawId")) for p in u.get("providerUserInfo") or [] if p.get("rawId")}


def rencana_akun(lama: list[dict], baru: list[dict]) -> tuple[list[dict], set[str], dict]:
    """Akun mana yang dimasukkan ke proyek baru. Mengembalikan (rekaman, UID yang dilewati, jumlah).

    UID yang sudah ada di proyek baru dilewati (penyalinan sebelumnya, jadi aman diulang). Email atau akun Google yang sama
    dengan UID lain berarti orang itu sudah masuk ke situs baru sebelum akun disalin: akunnya di proyek baru dibiarkan,
    dan data lamanya tidak ikut disalin supaya tidak ada akun kembar.
    """
    uid_baru = {u.get("localId") for u in baru}
    email_baru = {u["email"].lower() for u in baru if u.get("email")}
    penyedia_baru = set().union(*(_penyedia(u) for u in baru)) if baru else set()
    rekaman, lewati = [], set()
    jumlah = {"lama": len(lama), "dipindah": 0, "sudah_ada": 0, "bentrok": 0, "gagal": 0}
    for u in lama:
        uid = u.get("localId")
        if not uid:
            continue
        if uid in uid_baru:
            jumlah["sudah_ada"] += 1
        elif (u.get("email") or "").lower() in email_baru or _penyedia(u) & penyedia_baru:
            lewati.add(uid)
            jumlah["bentrok"] += 1
        else:
            rekaman.append(rekam_impor(u))
    return rekaman, lewati, jumlah


def impor_akun(sesi, proyek: str, rekaman: list[dict], saran: str = "") -> list[int]:
    """Masukkan akun ke proyek baru. Mengembalikan nomor urut rekaman yang ditolak."""
    gagal: list[int] = []
    for awal in range(0, len(rekaman), MAKS_AKUN):
        r = sesi.post(_alamat_auth(proyek, "batchCreate"), json={"users": rekaman[awal:awal + MAKS_AKUN]}, timeout=120)
        _periksa(r, f"Memasukkan akun login ke proyek {proyek}", saran)
        gagal += [awal + int(e.get("index", 0)) for e in r.json().get("error") or []]
    return gagal


# ---------------------------------------------------------------- koleksi Firestore

def salin_koleksi(db_lama, db_baru, nama: str, lewati: set[str] | frozenset[str] = frozenset()) -> dict:
    """Salin dokumen yang belum ada di proyek baru. Dokumen yang sudah ada di proyek baru tidak ditimpa."""
    ada = {ref.id for ref in db_baru.collection(nama).list_documents()}
    jumlah = {"disalin": 0, "sudah_ada": 0, "dilewati": 0}
    batch, isi = db_baru.batch(), 0
    for dok in db_lama.collection(nama).stream():
        if dok.id in lewati:
            jumlah["dilewati"] += 1
            continue
        if dok.id in ada:
            jumlah["sudah_ada"] += 1
            continue
        batch.set(db_baru.collection(nama).document(dok.id), dok.to_dict() or {})
        isi += 1
        jumlah["disalin"] += 1
        if isi >= MAKS_TULIS:
            batch.commit()
            batch, isi = db_baru.batch(), 0
    if isi:
        batch.commit()
    return jumlah


def salin_akun(berkas_lama: Path, berkas_baru: Path, sesi_fn=sesi_auth, klien_fn=klien_firestore) -> dict:
    """Pindahkan akun login beserta peran, tabel hak akses, dan jejak tindakan admin ke proyek baru."""
    lama, baru = baca_kunci(berkas_lama), baca_kunci(berkas_baru)
    if lama["project_id"] == baru["project_id"]:
        raise ValueError("Kunci lama dan kunci baru berasal dari proyek yang sama. Isi FIREBASE_SERVICE_ACCOUNT_LAMA dengan "
                         "kunci akun layanan proyek lama, dan FIREBASE_SERVICE_ACCOUNT dengan kunci proyek baru.")
    sesi_lama, sesi_baru = sesi_fn(lama), sesi_fn(baru)
    saran_lama = "Beri akun layanan proyek lama peran Firebase Authentication Viewer, lalu jalankan lagi."
    saran_baru = "Beri akun layanan proyek baru peran Firebase Authentication Admin, lalu jalankan lagi."
    akun_lama = daftar_akun(sesi_lama, lama["project_id"], saran_lama)
    akun_baru = daftar_akun(sesi_baru, baru["project_id"], saran_baru)
    rekaman, lewati, jumlah = rencana_akun(akun_lama, akun_baru)
    gagal = impor_akun(sesi_baru, baru["project_id"], rekaman, saran_baru) if rekaman else []
    lewati |= {rekaman[i]["localId"] for i in gagal if 0 <= i < len(rekaman)}
    jumlah["dipindah"], jumlah["gagal"] = len(rekaman) - len(gagal), len(gagal)

    db_lama, db_baru = klien_fn(lama), klien_fn(baru)
    koleksi = {nama: salin_koleksi(db_lama, db_baru, nama, lewati if nama == "lbp_pengguna" else frozenset())
               for nama in KOLEKSI_AKUN}
    return {"proyek_lama": lama["project_id"], "proyek_baru": baru["project_id"], "akun": jumlah, "koleksi": koleksi}


def cetak_ringkasan(h: dict) -> None:
    a = h["akun"]
    print(f"Proyek lama {h['proyek_lama']}, proyek baru {h['proyek_baru']}.")
    print(f"Akun login: {a['lama']} di proyek lama. {a['dipindah']} dipindah, {a['sudah_ada']} sudah ada, "
          f"{a['bentrok']} sudah lebih dulu masuk ke situs baru, {a['gagal']} gagal.")
    for nama, j in h["koleksi"].items():
        print(f"{nama}: {j['disalin']} disalin, {j['sudah_ada']} sudah ada, {j['dilewati']} dilewati.")
    if a["bentrok"]:
        print("Akun yang sudah lebih dulu masuk ke situs baru dibiarkan apa adanya. Atur perannya di halaman Pengguna.")
    if a["gagal"]:
        print(f"::warning::{a['gagal']} akun ditolak proyek baru. Pemiliknya cukup masuk lagi lalu disetujui di halaman Pengguna.")


# ---------------------------------------------------------------- pengalih untuk alamat lama

HTML_PENGALIH = """<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="4; url=__ALAMAT__">
<title>Takar Pangan 10•21 sudah pindah alamat</title>
<style>
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #0f1720; color: #e8edf2;
         font: 16px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  main { max-width: 32rem; padding: 2rem 1.5rem; }
  h1 { font-size: 1.35rem; line-height: 1.3; margin: 0 0 .75rem; }
  p { margin: 0 0 .75rem; color: #b9c4cf; }
  a { color: #7cc4ff; word-break: break-all; }
</style>
<script>
  // Hapus service worker dan simpanan lama di perangkat ini, lalu buka halaman yang sama di alamat baru.
  (function () {
    var tujuan = __ALAMAT_JS__.replace(/\\/$/, "") + location.pathname + location.search + location.hash;
    var sudah = false;
    function pergi() { if (!sudah) { sudah = true; location.replace(tujuan); } }
    function hapusSimpanan() {
      if (!window.caches || !caches.keys) return Promise.resolve();
      return caches.keys().then(function (k) { return Promise.all(k.map(function (n) { return caches.delete(n); })); });
    }
    function tunggu(ms) { return new Promise(function (s) { setTimeout(s, ms); }); }
    var cabut = navigator.serviceWorker && navigator.serviceWorker.getRegistrations
      ? navigator.serviceWorker.getRegistrations().then(function (d) {
          return Promise.all(d.map(function (r) { return r.unregister(); }));
        })
      : Promise.resolve();
    // Simpanan dihapus dua kali: service worker lama bisa saja masih menyimpan halaman ini sesaat setelah penghapusan pertama.
    Promise.all([cabut, hapusSimpanan()]).then(function () { return tunggu(300); }).then(hapusSimpanan).then(pergi, pergi);
    setTimeout(pergi, 2500);
  })();
</script>
</head>
<body>
<main>
  <h1>Takar Pangan 10•21 sudah pindah alamat</h1>
  <p>Alamat barunya <a href="__ALAMAT__">__ALAMAT_TAMPIL__</a>. Halaman ini akan membukanya secara otomatis.</p>
  <p>Bila aplikasi Takar Pangan terpasang di ponsel, hapus aplikasinya, lalu pasang lagi dari alamat baru.</p>
</main>
</body>
</html>
"""

SW_PENCABUT = """// Situs ini sudah pindah alamat. Service worker lama diganti dengan yang ini: simpanannya dihapus, dirinya dicabut,
// lalu halaman yang sedang terbuka dimuat ulang supaya langsung diarahkan ke alamat baru.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) await caches.delete(k);
    await self.registration.unregister();
    for (const c of await self.clients.matchAll({ type: "window" })) c.navigate(c.url).catch(() => {});
  })());
});
"""


def alamat_situs(env) -> str:
    """Alamat situs baru: URL_DASHBOARD bila diisi, selain itu situs Firebase Hosting yang aktif."""
    if (env.get("URL_DASHBOARD") or "").strip():
        return env["URL_DASHBOARD"].strip()
    situs = (env.get("FIREBASE_HOSTING_SITE") or "").strip()
    return f"https://{situs}.web.app/" if situs else ""


def _alamat_sah(alamat: str) -> str:
    bagian = urlsplit((alamat or "").strip())
    host = bagian.hostname or ""
    if (bagian.scheme != "https" or not _HOST.fullmatch(host) or bagian.query or bagian.fragment
            or bagian.username or bagian.password or not _JALUR.fullmatch(bagian.path or "")):
        raise ValueError("Alamat baru harus berupa alamat https lengkap tanpa tanda tanya atau pagar, misalnya "
                         "https://takarpangan.contoh.go.id/. Isi variabel URL_DASHBOARD dengan alamat situs baru.")
    return f"https://{host}{f':{bagian.port}' if bagian.port else ''}{bagian.path or '/'}"


def siapkan_pengalih(tujuan: Path, alamat_baru: str, situs: str, situs_aktif: str = "") -> Path:
    """Tulis situs pengalih (firebase.json, situs/index.html, situs/sw.js) untuk diterbitkan ke situs Hosting lama."""
    situs = (situs or "").strip()
    if not _SITUS.fullmatch(situs):
        raise ValueError("Nama situs Hosting lama tidak sah. Isi hanya namanya (huruf kecil, angka, tanda minus), misalnya "
                         "lintas-benteng-proyeksi, bukan alamat lengkapnya.")
    if situs == (situs_aktif or "").strip():
        raise ValueError(f"Situs {situs} adalah situs yang sedang dipakai sistem (FIREBASE_HOSTING_SITE). Pengalih hanya "
                         "untuk situs lama, supaya situs baru tidak tertimpa.")
    alamat = _alamat_sah(alamat_baru)
    if urlsplit(alamat).hostname in (f"{situs}.web.app", f"{situs}.firebaseapp.com"):
        raise ValueError("Alamat baru masih alamat situs lama, jadi pengunjung akan diarahkan berputar-putar. Isi variabel "
                         "URL_DASHBOARD dengan alamat situs baru.")
    folder = Path(tujuan)
    (folder / "situs").mkdir(parents=True, exist_ok=True)
    halaman = (HTML_PENGALIH.replace("__ALAMAT_JS__", json.dumps(alamat))
               .replace("__ALAMAT_TAMPIL__", html.escape(alamat.rstrip("/").removeprefix("https://")))
               .replace("__ALAMAT__", html.escape(alamat)))
    (folder / "situs" / "index.html").write_text(halaman, encoding="utf-8")
    (folder / "situs" / "sw.js").write_text(SW_PENCABUT, encoding="utf-8")
    # Pengalihan lewat halaman, bukan aturan "redirects": aturan itu juga berlaku untuk sw.js, padahal browser tidak mau
    # memperbarui service worker dari alamat yang dialihkan. Berkas yang ada (sw.js) didahulukan Hosting atas rewrites.
    konfig = {"hosting": {"site": situs, "public": "situs",
                          "rewrites": [{"source": "**", "destination": "/index.html"}],
                          "headers": [{"source": "**", "headers": [{"key": "Cache-Control", "value": "no-cache"}]}]}}
    (folder / "firebase.json").write_text(json.dumps(konfig, indent=2) + "\n", encoding="utf-8")
    return folder


# ---------------------------------------------------------------- perintah

def perintah(a) -> int:
    """Dipanggil dari `python -m pipeline migrasi ...`."""
    try:
        if a.tugas == "salin-akun":
            if not a.lama or not a.baru:
                raise ValueError("Isi --lama dan --baru dengan berkas kunci akun layanan proyek lama dan proyek baru.")
            cetak_ringkasan(salin_akun(a.lama, a.baru))
            return 0
        alamat = a.alamat_baru or alamat_situs(os.environ)
        folder = siapkan_pengalih(a.keluaran, alamat, a.situs, situs_aktif=os.environ.get("FIREBASE_HOSTING_SITE", ""))
        print(f"Situs pengalih untuk {a.situs} disiapkan di {folder}. Semua halaman diarahkan ke {_alamat_sah(alamat)}")
        return 0
    except Exception as e:  # noqa: BLE001 - galat apa pun dilaporkan singkat tanpa jejak panjang yang bisa memuat data
        print(f"GAGAL: {samarkan_email(str(e)) or type(e).__name__}", file=sys.stderr)
        return 2

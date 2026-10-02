// Peran pengguna, menu tiap peran, akses halaman, dan login.
//
// Penting: situs ini statis, jadi peran di sini mengatur TAMPILAN (menu dan beranda). Data tetap berupa berkas publik.
// Login "contoh" memakai akun di config/pengguna.json. Login "firebase" (konfigurasi Firebase terisi) memakai akun Google
// lewat Firebase Authentication; akun baru menunggu persetujuan admin, dan peran serta izin halaman diatur admin di
// halaman Pengguna. Aturan Firestore (firestore.rules) yang menjaga hak itu di sisi server.

const M = {
  beranda: ["index.html", "Beranda"],
  harga: ["harga.html", "Harga"],
  peringatan: ["sinyal.html", "Peringatan"],
  laporan: ["laporan.html", "Laporan"],
  capaian: ["kinerja.html", "Capaian"],
  cek: ["kualitas.html", "Cek Data"],
  akurasi: ["model.html", "Akurasi"],
  sumber: ["sumber.html", "Sumber"],
  catat: ["input.html", "Catat Harga"],
  alur: ["alur.html", "Alur"],
  pengguna: ["pengguna.html", "Pengguna"],
  pengaturan: ["pengaturan.html", "Pengaturan"],
  tentang: ["tentang.html", "Tentang"],
};

export const PERAN = {
  masyarakat: {
    nama: "Masyarakat", ikon: "orang", ringkas: "Lihat harga dan laporan mingguan", judulBeranda: "Harga Hari Ini",
    menu: ["beranda", "harga", "laporan", "tentang"], lainnya: [],
  },
  petugas: {
    nama: "Petugas Lapangan", ikon: "toko", ringkas: "Catat harga di pasar", judulBeranda: "Tugas Hari Ini",
    menu: ["beranda", "catat", "harga", "tentang"], lainnya: [],
  },
  operator: {
    nama: "Operator Data", ikon: "database", ringkas: "Kelola berkas dan cek mutu data", judulBeranda: "Kondisi Data",
    menu: ["beranda", "cek", "sumber", "harga", "tentang"], lainnya: [],
  },
  analis: {
    nama: "Analis", ikon: "cari", ringkas: "Periksa data, peringatan, dan model", judulBeranda: "Meja Analis",
    menu: ["beranda", "peringatan", "cek", "akurasi", "laporan", "harga"], lainnya: ["tentang"],
  },
  tpid: {
    nama: "TPID", ikon: "tim", ringkas: "Pantau harga dan ambil keputusan", judulBeranda: "Dashboard TPID",
    menu: ["beranda", "peringatan", "laporan", "capaian", "harga"], lainnya: ["alur", "tentang"],
  },
  admin: {
    nama: "Administrator", ikon: "gembokPerisai", ringkas: "Kelola seluruh sistem", judulBeranda: "Kondisi Sistem",
    menu: ["beranda", "pengaturan", "pengguna", "peringatan", "laporan", "cek"],
    lainnya: ["akurasi", "harga", "capaian", "sumber", "catat", "alur", "tentang"],
  },
};

export const URUT_PERAN = ["masyarakat", "petugas", "operator", "analis", "tpid", "admin"];
export const HALAMAN_BEBAS = ["index.html", "tentang.html", "masuk.html"];
export const SEMUA_HALAMAN = Object.values(M).map((x) => x[0]);
export const DAFTAR_HALAMAN = Object.values(M).map(([href, label]) => ({ href, label }));

const ubah = (kunci) => kunci.map((k) => ({ href: M[k][0], label: M[k][1] }));
const KUNCI_DARI_HREF = Object.fromEntries(Object.entries(M).map(([k, [href]]) => [href, k]));
/** Halaman yang hanya boleh dibuka administrator, apa pun izin yang diberikan. */
export const HALAMAN_ADMIN = ["pengaturan.html", "pengguna.html"];

/**
 * Menu untuk peran tertentu. `izin` (daftar href, dari akun Firebase) membatasi atau menambah halaman:
 * null berarti memakai bawaan peran.
 */
export function menuPeran(peran, izin = null) {
  const p = PERAN[peran] || PERAN.masyarakat;
  if (!Array.isArray(izin)) return { utama: ubah(p.menu), lainnya: ubah(p.lainnya) };
  const boleh = new Set(izin.filter((h) => KUNCI_DARI_HREF[h] && (peran === "admin" || !HALAMAN_ADMIN.includes(h))));
  boleh.add("index.html");
  const utama = p.menu.filter((k) => boleh.has(M[k][0]));
  const sisa = Object.keys(M).filter((k) => boleh.has(M[k][0]) && !utama.includes(k));
  const urutLainnya = [...p.lainnya.filter((k) => sisa.includes(k)), ...sisa.filter((k) => !p.lainnya.includes(k))];
  return { utama: ubah(utama), lainnya: ubah(urutLainnya) };
}

/** Izin halaman akun yang sedang masuk (null = bawaan peran). */
export const izinAktif = () => (Array.isArray(sesi()?.halaman) ? sesi().halaman : null);

export function halamanPeran(peran, izin = null) {
  const { utama, lainnya } = menuPeran(peran, izin);
  return new Set([...HALAMAN_BEBAS, ...utama.map((x) => x.href), ...lainnya.map((x) => x.href)]);
}

/** Apakah peran boleh membuka halaman. Untuk peran yang sedang masuk, izin halaman akunnya ikut dihitung. */
export function bolehAkses(peran, halaman, izin = peran === peranAktif() ? izinAktif() : null) {
  return halamanPeran(peran, izin).has(halaman);
}

/* ---------- sesi */
const KUNCI = "lintas-sesi-v1";
const MASA_MS = 7 * 24 * 3600 * 1000;

export function sesi() {
  try {
    const s = JSON.parse(localStorage.getItem(KUNCI));
    if (!s || !PERAN[s.peran] || Date.now() - s.masuk > MASA_MS) return null;
    return s;
  } catch { return null; }
}

export function peranAktif() {
  return sesi()?.peran || "masyarakat";
}

function simpanSesi(s) {
  try { localStorage.setItem(KUNCI, JSON.stringify({ ...s, masuk: Date.now() })); return true; } catch { return false; }
}

/** "ok", "masuk" (perlu login), atau "tolak" (sudah login tetapi bukan haknya). */
export function periksaAkses(halaman) {
  if (bolehAkses(peranAktif(), halaman)) return "ok";
  return sesi() ? "tolak" : "masuk";
}

export async function keluar() {
  const s = sesi();
  try { localStorage.removeItem(KUNCI); } catch { /* abaikan */ }
  if (s?.sumber === "firebase") {
    const { keluarFirebase } = await import("./firebase-klien.js");
    await keluarFirebase();
  }
}

/** Simpan sesi dari akun Firebase yang sudah disetujui. */
export function simpanSesiFirebase(data) {
  return PERAN[data.peran] ? simpanSesi(data) : false;
}

/* ---------- login */
export async function sha256(teks) {
  if (!globalThis.crypto?.subtle) throw new Error("Buka situs lewat alamat https agar login dapat dipakai.");
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(teks));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export const hashSandi = (garam, id, sandi) => sha256(`${garam}:${id.trim().toLowerCase()}:${sandi}`);

async function masukContoh(id, sandi) {
  const r = await fetch("data/pengguna.json", { cache: "no-cache" });
  if (!r.ok) return { ok: false, galat: "Daftar akun belum tersedia." };
  const { garam, akun } = await r.json();
  const h = await hashSandi(garam, id, sandi);
  const a = akun.find((x) => x.id === id.trim().toLowerCase() && x.sandi_hash === h);
  if (!a || !PERAN[a.peran]) return { ok: false, galat: "Nama pengguna atau kata sandi salah." };
  simpanSesi({ id: a.id, nama: a.nama, peran: a.peran, sumber: "contoh" });
  return { ok: true, peran: a.peran };
}

/** Masuk memakai penyedia login yang aktif menurut meta.login ("contoh" atau "firebase"). */
export async function masuk(meta, id, sandi) {
  if (!id.trim() || !sandi) return { ok: false, galat: "Isi nama pengguna dan kata sandi." };
  try {
    if (meta?.login === "firebase") return { ok: false, galat: "Gunakan tombol Masuk dengan Google." };
    return await masukContoh(id, sandi);
  } catch (e) {
    return { ok: false, galat: e.message || "Tidak bisa masuk saat ini." };
  }
}

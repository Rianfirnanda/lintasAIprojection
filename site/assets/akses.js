// Peran pengguna, menu tiap peran, akses halaman, dan login.
//
// Penting: situs ini statis, jadi peran di sini mengatur TAMPILAN (menu dan beranda). Data tetap berupa berkas publik.
// Login "contoh" memakai akun di config/pengguna.json. Login "firebase" (config/firebase.json terisi) memakai
// Firebase Authentication, dan pembatasan data sungguhan dilakukan lewat aturan Firestore di sisi server.

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

export function menuPeran(peran) {
  const p = PERAN[peran] || PERAN.masyarakat;
  return { utama: ubah(p.menu), lainnya: ubah(p.lainnya) };
}

export function halamanPeran(peran) {
  const { utama, lainnya } = menuPeran(peran);
  return new Set([...HALAMAN_BEBAS, ...utama.map((x) => x.href), ...lainnya.map((x) => x.href)]);
}

export function bolehAkses(peran, halaman) {
  return halamanPeran(peran).has(halaman);
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
    try {
      const { getAuth, signOut } = await import(`${FB}firebase-auth.js`);
      await signOut(getAuth());
    } catch { /* abaikan */ }
  }
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

const FB = "https://www.gstatic.com/firebasejs/10.12.2/";

async function masukFirebase(email, sandi) {
  const konf = (await (await fetch("data/firebase.json", { cache: "no-cache" })).json()).konfigurasi;
  const [{ initializeApp, getApps }, { getAuth, signInWithEmailAndPassword, signOut }, { getFirestore, doc, getDoc }] =
    await Promise.all([import(`${FB}firebase-app.js`), import(`${FB}firebase-auth.js`), import(`${FB}firebase-firestore.js`)]);
  const app = getApps()[0] || initializeApp(konf);
  const auth = getAuth(app);
  try {
    const { user } = await signInWithEmailAndPassword(auth, email.trim(), sandi);
    const dok = await getDoc(doc(getFirestore(app), "pengguna", user.uid));
    const data = dok.exists() ? dok.data() : {};
    if (!PERAN[data.peran]) {
      await signOut(auth);
      return { ok: false, galat: "Akun ini belum diberi peran. Hubungi administrator." };
    }
    simpanSesi({ id: user.email, nama: data.nama || user.email, peran: data.peran, sumber: "firebase" });
    return { ok: true, peran: data.peran };
  } catch (e) {
    const salah = ["auth/invalid-credential", "auth/wrong-password", "auth/user-not-found", "auth/invalid-email"];
    return { ok: false, galat: salah.includes(e.code) ? "Email atau kata sandi salah." : "Tidak bisa masuk saat ini. Coba lagi nanti." };
  }
}

/** Masuk memakai penyedia login yang aktif menurut meta.login ("contoh" atau "firebase"). */
export async function masuk(meta, id, sandi) {
  if (!id.trim() || !sandi) return { ok: false, galat: "Isi nama pengguna dan kata sandi." };
  try {
    return meta?.login === "firebase" ? await masukFirebase(id, sandi) : await masukContoh(id, sandi);
  } catch (e) {
    return { ok: false, galat: e.message || "Tidak bisa masuk saat ini." };
  }
}

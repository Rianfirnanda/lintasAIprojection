// Penghubung situs ke Firebase: login Google, akun di Firestore (koleksi lbp_pengguna), dan jejak tindakan admin.
// Dimuat hanya bila meta.login === "firebase". SDK Firebase disimpan di site/vendor/firebase (tanpa CDN).
//
// Yang benar-benar menjaga keamanan adalah aturan Firestore (firestore.rules): pendaftar hanya bisa membuat akun
// "menunggu", dan hanya admin aktif yang bisa menyetujui, memberi peran, dan mengatur izin halaman.

export const KOLEKSI_PENGGUNA = "lbp_pengguna";
export const KOLEKSI_JEJAK = "lbp_jejak";
export const DOK_AKSES = ["lbp_akses", "peran"];

let siap = null;
let modeEmulator = false;

/** { fb, app, auth, db } setelah SDK dan konfigurasi termuat. Dipanggil berkali-kali aman. */
export function firebaseSiap() {
  siap ||= (async () => {
    const r = await fetch("data/firebase.json", { cache: "no-cache" });
    if (!r.ok) throw new Error("Konfigurasi Firebase belum tersedia.");
    const { konfigurasi } = await r.json();
    const fb = await import("../vendor/firebase/firebase.js");
    const { emulator, ...konf } = konfigurasi;
    const app = fb.getApps()[0] || fb.initializeApp(konf);
    const auth = fb.getAuth(app);
    const db = fb.getFirestore(app);
    const lokal = ["localhost", "127.0.0.1"].includes(location.hostname);
    if (emulator && lokal) {
      fb.connectAuthEmulator(auth, emulator.auth, { disableWarnings: true });
      fb.connectFirestoreEmulator(db, emulator.firestore[0], emulator.firestore[1]);
      modeEmulator = true;
    }
    return { fb, app, auth, db };
  })();
  siap.catch(() => { siap = null; });
  return siap;
}

/** Pengguna Firebase yang sedang masuk (menunggu Firebase selesai memulihkan login), atau null. */
export async function penggunaKini() {
  const { fb, auth } = await firebaseSiap();
  if (auth.currentUser) return auth.currentUser;
  return new Promise((selesai) => {
    const lepas = fb.onAuthStateChanged(auth, (u) => { lepas(); selesai(u); });
  });
}

/** Masuk dengan akun Google. Memakai jendela kecil (popup); bila diblokir browser, pindah halaman (redirect). */
export async function masukGoogle() {
  const { fb, auth } = await firebaseSiap();
  // Khusus uji otomatis dengan emulator di localhost: masuk dengan akun Google tiruan tanpa jendela popup.
  const ujiEmail = modeEmulator && sessionStorage.getItem("lbp-uji-email");
  if (ujiEmail) {
    const token = JSON.stringify({ sub: `uji-${ujiEmail}`, email: ujiEmail, email_verified: true, name: sessionStorage.getItem("lbp-uji-nama") || ujiEmail });
    return (await fb.signInWithCredential(auth, fb.GoogleAuthProvider.credential(token))).user;
  }
  const penyedia = new fb.GoogleAuthProvider();
  penyedia.setCustomParameters({ prompt: "select_account" });
  try {
    return (await fb.signInWithPopup(auth, penyedia)).user;
  } catch (e) {
    if (e?.code === "auth/popup-blocked" || e?.code === "auth/operation-not-supported-in-this-environment") {
      await fb.signInWithRedirect(auth, penyedia);
      return null; // halaman akan berpindah
    }
    throw e;
  }
}

/** Hasil login lewat redirect (dipanggil saat halaman masuk dibuka). */
export async function hasilRedirect() {
  const { fb, auth } = await firebaseSiap();
  try { return (await fb.getRedirectResult(auth))?.user || null; } catch { return null; }
}

export async function keluarFirebase() {
  try {
    const { fb, auth } = await firebaseSiap();
    await fb.signOut(auth);
  } catch { /* abaikan: sesi lokal tetap dihapus */ }
}

const kodeIzinDitolak = (e) => e?.code === "permission-denied" || /permission/i.test(e?.message || "");

/**
 * Data akun pengguna di Firestore. Bila belum ada, dibuat berstatus "menunggu".
 * Email admin pertama (diatur di aturan Firestore) otomatis menjadi admin aktif.
 */
export async function pastikanAkun(user) {
  const { fb, db } = await firebaseSiap();
  const ref = fb.doc(db, KOLEKSI_PENGGUNA, user.uid);
  let dok = await fb.getDoc(ref);
  const nama = (user.displayName || user.email || "Pengguna").slice(0, 120);
  if (!dok.exists() || dok.data().status === "menunggu") {
    // Coba angkat sebagai admin pertama. Aturan Firestore menolak bila email ini tidak terdaftar.
    try {
      if (dok.exists()) {
        await fb.updateDoc(ref, { status: "aktif", peran: "admin", halaman: null, diperbarui: fb.serverTimestamp() });
      } else {
        await fb.setDoc(ref, { email: user.email, nama, foto: user.photoURL || null, status: "aktif", peran: "admin",
          halaman: null, dibuat: fb.serverTimestamp(), diperbarui: fb.serverTimestamp() });
      }
    } catch (e) {
      if (!kodeIzinDitolak(e)) throw e;
      if (!dok.exists()) {
        await fb.setDoc(ref, { email: user.email, nama, foto: user.photoURL || null, status: "menunggu", peran: null,
          halaman: null, dibuat: fb.serverTimestamp(), diperbarui: fb.serverTimestamp() });
      }
    }
    dok = await fb.getDoc(ref);
  }
  return { uid: user.uid, ...dok.data() };
}

/** Pantau perubahan akun sendiri (misalnya saat admin menyetujui). Mengembalikan fungsi untuk berhenti. */
export async function pantauAkunSendiri(uid, saatBerubah) {
  const { fb, db } = await firebaseSiap();
  return fb.onSnapshot(fb.doc(db, KOLEKSI_PENGGUNA, uid), (d) => saatBerubah(d.exists() ? { uid, ...d.data() } : null), () => {});
}

/**
 * Isi sesi lokal dari data akun Firestore. Halaman yang boleh dibuka: izin pribadi akun (bila diatur), lalu tabel hak
 * akses per peran dari halaman Pengguna, lalu bawaan peran (null). Urutan ini sama dengan aturan Firestore.
 */
export function sesiDariAkun(akun, tabel = null) {
  const halaman = Array.isArray(akun.halaman) ? akun.halaman
    : akun.peran !== "admin" && Array.isArray(tabel?.[akun.peran]) ? tabel[akun.peran] : null;
  return { id: akun.email, nama: akun.nama || akun.email, peran: akun.peran, halaman,
    foto: akun.foto || null, uid: akun.uid, sumber: "firebase" };
}

/** Tabel hak akses per peran ({ peran: [halaman] }), atau null bila admin belum pernah mengubahnya. */
export async function muatTabelAkses() {
  const { fb, db } = await firebaseSiap();
  try {
    const d = await fb.getDoc(fb.doc(db, ...DOK_AKSES));
    return d.exists() ? d.data().halaman || null : null;
  } catch { return null; }
}

/** Sesi lengkap untuk akun aktif (memuat tabel hak akses dulu). */
export async function sesiAkun(akun) {
  return sesiDariAkun(akun, await muatTabelAkses());
}

/** Pantau tabel hak akses (halaman Pengguna). */
export async function pantauTabelAkses(saatBerubah) {
  const { fb, db } = await firebaseSiap();
  return fb.onSnapshot(fb.doc(db, ...DOK_AKSES), (d) => saatBerubah(d.exists() ? d.data() : null), () => saatBerubah(null));
}

/** Simpan tabel hak akses (hanya peran Administrator) dan catat jejaknya. */
export async function simpanTabelAkses(halaman, rincian = "") {
  const { fb, db, auth } = await firebaseSiap();
  await fb.setDoc(fb.doc(db, ...DOK_AKSES), { halaman, diubah_oleh: auth.currentUser.email, diubah_pada: fb.serverTimestamp() });
  await catatJejak("hak_akses", { uid: "", email: "" }, rincian);
}

/* ---------- untuk panel admin */

/** Pantau semua akun (hanya berhasil untuk pengelola akun). */
export async function pantauSemuaAkun(saatBerubah, saatGalat) {
  const { fb, db } = await firebaseSiap();
  const q = fb.query(fb.collection(db, KOLEKSI_PENGGUNA), fb.orderBy("dibuat", "desc"));
  return fb.onSnapshot(q, (snap) => saatBerubah(snap.docs.map((d) => ({ uid: d.id, ...d.data() })), snap.metadata.fromCache), saatGalat);
}

/** Pantau jejak tindakan admin terbaru. */
export async function pantauJejak(saatBerubah, saatGalat, jumlah = 30) {
  const { fb, db } = await firebaseSiap();
  const q = fb.query(fb.collection(db, KOLEKSI_JEJAK), fb.orderBy("waktu", "desc"), fb.limit(jumlah));
  return fb.onSnapshot(q, (snap) => saatBerubah(snap.docs.map((d) => ({ id: d.id, ...d.data() }))), saatGalat);
}

/** Ubah akun orang lain (admin) dan catat jejaknya. `perubahan` berisi status, peran, dan/atau halaman. */
export async function ubahAkun(sasaran, perubahan, aksi, rincian = "") {
  const { fb, db, auth } = await firebaseSiap();
  const saya = auth.currentUser;
  await fb.updateDoc(fb.doc(db, KOLEKSI_PENGGUNA, sasaran.uid), {
    ...perubahan, diperbarui: fb.serverTimestamp(), diputus_oleh: saya.email, diputus_pada: fb.serverTimestamp(),
  });
  await catatJejak(aksi, sasaran, rincian);
}

export async function hapusAkun(sasaran) {
  const { fb, db } = await firebaseSiap();
  await fb.deleteDoc(fb.doc(db, KOLEKSI_PENGGUNA, sasaran.uid));
  await catatJejak("hapus", sasaran, "");
}

async function catatJejak(aksi, sasaran, rincian) {
  const { fb, db, auth } = await firebaseSiap();
  const saya = auth.currentUser;
  try {
    await fb.addDoc(fb.collection(db, KOLEKSI_JEJAK), {
      aksi, oleh: saya.uid, oleh_email: saya.email, sasaran: sasaran.uid, sasaran_email: sasaran.email || "",
      rincian: String(rincian).slice(0, 300), waktu: fb.serverTimestamp(),
    });
  } catch (e) {
    console.warn("Jejak admin tidak tersimpan", e);
  }
}

/** Pesan galat Firebase yang mudah dipahami. */
export function pesanGalat(e) {
  const k = e?.code || "";
  if (k === "auth/popup-closed-by-user" || k === "auth/cancelled-popup-request") return "Jendela login ditutup sebelum selesai.";
  if (k === "auth/unauthorized-domain") return "Alamat situs ini belum diizinkan untuk login. Admin perlu menambahkannya di Firebase Authentication, bagian Authorized domains.";
  if (k === "auth/operation-not-allowed") return "Login Google belum diaktifkan di Firebase Authentication.";
  if (k === "auth/network-request-failed" || k === "unavailable") return "Tidak ada sambungan internet. Coba lagi.";
  if (kodeIzinDitolak(e)) return "Akses ditolak oleh aturan keamanan. Pastikan akun Anda sudah disetujui admin.";
  return e?.message ? `Terjadi galat: ${e.message}` : "Terjadi galat. Coba lagi.";
}

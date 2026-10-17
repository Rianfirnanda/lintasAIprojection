// Kehadiran dan log aktivitas pengguna (hanya bila situs memakai login Firebase).
//   - lbp_kehadiran/{uid}: halaman yang sedang dibuka, sedang dipakai atau diam, kapan terakhir aktif, dan lokasi bila
//     pemiliknya memilih membagikan.
//   - lbp_aktivitas: catatan masuk, membuka halaman, keluar, dan perubahan izin lokasi. Kolom hapus_pada dipakai
//     kebijakan TTL Firestore supaya catatan lama terhapus sendiri (lihat PANDUAN_OPERASIONAL.md bagian 8).
// Hanya pengelola akun (Administrator) yang bisa membaca keduanya (firestore.rules).
// Lokasi hanya diambil setelah pengguna menekan "Bagikan lokasi" dan browser mengizinkan. Petugas lapangan dikirim tepat
// (untuk memantau kunjungan pasar); peran lain dibulatkan sekitar 1 km supaya rumah orang tidak bisa ditunjuk.

export const KOLEKSI_KEHADIRAN = "lbp_kehadiran";
export const KOLEKSI_AKTIVITAS = "lbp_aktivitas";
export const MENIT_AKTIF = 10;
export const MENIT_DIAM = 30;
export const SIMPAN_HARI = 90;
const DETAK_MS = 5 * 60e3;
const LOKASI_MS = 10 * 60e3;
const PERAN_TEPAT = ["petugas"];

/** Lokasi yang dikirim: tepat untuk petugas lapangan, dibulatkan sekitar 1 km untuk peran lain. */
export function bulatkanLokasi(koordinat, peran) {
  const tepat = PERAN_TEPAT.includes(peran);
  const f = tepat ? 1e5 : 1e2;
  const akurasi = Math.round(Number(koordinat.accuracy) || 0);
  return { lat: Math.round(koordinat.latitude * f) / f, lon: Math.round(koordinat.longitude * f) / f,
    akurasi: tepat ? akurasi : Math.max(akurasi, 1100), perkiraan: !tepat };
}

const milidetik = (t) => (t?.toMillis ? t.toMillis() : t instanceof Date ? t.getTime() : typeof t === "number" ? t : t ? Date.parse(t) : 0);

/** Status untuk tampilan admin: aktif (dipakai dalam 10 menit), diam (terbuka tapi tidak dipakai, sampai 30 menit), atau tidak aktif. */
export function statusKehadiran(k, kini = Date.now()) {
  const t = milidetik(k?.terakhir_aktif);
  const menit = t ? Math.max(0, (kini - t) / 60e3) : Infinity;
  if (!k || k.status === "keluar" || menit > MENIT_DIAM) return { kode: "tidak", label: k?.status === "keluar" ? "Keluar" : "Tidak aktif", menit };
  if (k.status === "aktif" && menit <= MENIT_AKTIF) return { kode: "aktif", label: "Aktif", menit };
  return { kode: "diam", label: "Diam", menit };
}

/** "baru saja", "12 menit lalu", "3 jam lalu", "2 hari lalu". */
export function berapaLama(menit) {
  if (!Number.isFinite(menit)) return "belum pernah";
  if (menit < 1) return "baru saja";
  if (menit < 60) return `${Math.round(menit)} menit lalu`;
  if (menit < 48 * 60) return `${Math.round(menit / 60)} jam lalu`;
  return `${Math.round(menit / 1440)} hari lalu`;
}

/** Gabungkan akun, kehadiran, dan waktu sekarang menjadi baris tampilan (urut: aktif dulu, lalu yang terakhir aktif). */
export function susunBaris(akun, kehadiran, kini = Date.now()) {
  const hadir = Object.fromEntries(kehadiran.map((k) => [k.uid, k]));
  return akun.filter((a) => a.status === "aktif").map((a) => {
    const k = hadir[a.uid] || null;
    const s = statusKehadiran(k, kini);
    return { uid: a.uid, nama: a.nama || a.email, email: a.email, peran: a.peran, k, s,
      lokasi: k?.izin_lokasi === "ya" ? k.lokasi || null : null, izin: k?.izin_lokasi || "belum" };
  }).sort((x, y) => ({ aktif: 0, diam: 1, tidak: 2 })[x.s.kode] - ({ aktif: 0, diam: 1, tidak: 2 })[y.s.kode] || x.s.menit - y.s.menit);
}

/** Jumlah per status dan jumlah yang membagikan lokasi. */
export function hitung(baris) {
  return {
    aktif: baris.filter((b) => b.s.kode === "aktif").length,
    diam: baris.filter((b) => b.s.kode === "diam").length,
    tidak: baris.filter((b) => b.s.kode === "tidak").length,
    lokasi: baris.filter((b) => b.lokasi).length,
  };
}

/** Judul halaman tanpa nama situs di belakangnya. */
const judulKini = () => document.title.replace(/\s*[·|-]\s*Takar Pangan.*$/, "").slice(0, 120);
const halamanKini = () => location.pathname.split("/").pop() || "index.html";
const perangkat = () => (/Mobi|Android|iPhone|iPad/i.test(navigator.userAgent) ? "ponsel" : "komputer");
const KUNCI_IZIN = (uid) => `lbp-izin-lokasi-${uid}`;

let st = null;

async function siap() {
  const fk = await import("./firebase-klien.js");
  const user = await fk.penggunaKini();
  if (!user) return null;
  const { fb, db } = await fk.firebaseSiap();
  return { fb, db, uid: user.uid };
}

function dataKehadiran(status) {
  return {
    status, halaman: halamanKini().slice(0, 60), judul: judulKini(), perangkat: perangkat(),
    terakhir_aktif: st.fb.serverTimestamp(), izin_lokasi: st.izin,
    lokasi: st.izin === "ya" ? st.lokasi : null,
    lokasi_waktu: st.izin === "ya" && st.lokasiWaktu ? st.fb.Timestamp.fromMillis(st.lokasiWaktu) : null,
  };
}

async function detak(status) {
  if (!st) return;
  st.statusTerkirim = status;
  try { await st.fb.setDoc(st.fb.doc(st.db, KOLEKSI_KEHADIRAN, st.uid), dataKehadiran(status)); } catch { /* dicoba lagi pada detak berikutnya */ }
}

async function catat(aksi, rincian = "") {
  if (!st) return;
  try {
    await st.fb.addDoc(st.fb.collection(st.db, KOLEKSI_AKTIVITAS), {
      uid: st.uid, nama: String(st.nama || "").slice(0, 120), peran: st.peran, aksi, halaman: halamanKini().slice(0, 60),
      rincian: String(rincian).slice(0, 200), lokasi: st.izin === "ya" ? st.lokasi : null,
      waktu: st.fb.serverTimestamp(), hapus_pada: st.fb.Timestamp.fromMillis(Date.now() + SIMPAN_HARI * 864e5),
    });
  } catch { /* log aktivitas tidak boleh mengganggu pemakaian */ }
}

function ambilLokasi() {
  return new Promise((selesai, gagal) => {
    if (!navigator.geolocation) { gagal(new Error("tidak didukung")); return; }
    navigator.geolocation.getCurrentPosition((p) => selesai(p.coords), gagal, { enableHighAccuracy: PERAN_TEPAT.includes(st.peran), timeout: 20000, maximumAge: LOKASI_MS });
  });
}

async function perbaruiLokasi() {
  try {
    st.lokasi = bulatkanLokasi(await ambilLokasi(), st.peran);
    st.lokasiWaktu = Date.now();
    return true;
  } catch (e) {
    // Izin dicabut di pengaturan browser: berhenti meminta dan beri tahu admin bahwa lokasi tidak lagi dibagikan.
    if (e?.code === 1) { st.izin = "ditolak"; st.lokasi = null; simpanIzin(); }
    return false;
  }
}

function simpanIzin() {
  try { localStorage.setItem(KUNCI_IZIN(st.uid), st.izin); } catch { /* abaikan */ }
}

async function aturIzin(bagikan) {
  if (bagikan) {
    st.izin = "ya";
    await perbaruiLokasi(); // bila browser menolak, izin menjadi "ditolak"; bila hanya lambat, dicoba lagi nanti
  } else {
    st.izin = "tidak";
    st.lokasi = null;
    st.lokasiWaktu = null;
  }
  simpanIzin();
  await detak("aktif");
  await catat(st.izin === "ya" ? "lokasi_dibagikan" : "lokasi_dihentikan", st.izin === "ditolak" ? "browser menolak izin lokasi" : "");
  perbaruiMenu();
  return st.izin;
}

/** Tawaran berbagi lokasi, sekali per akun. Tidak menghalangi halaman. */
function tawarkanLokasi() {
  if (document.querySelector(".tawar-lokasi")) return;
  const tepat = PERAN_TEPAT.includes(st.peran);
  const el = document.createElement("div");
  el.className = "tawar-lokasi";
  el.setAttribute("role", "dialog");
  el.setAttribute("aria-label", "Berbagi lokasi");
  el.innerHTML = `<p><b>Bagikan lokasi Anda dengan Administrator?</b>
      ${tepat ? "Lokasi dipakai untuk memantau kunjungan petugas ke pasar." : "Lokasi hanya perkiraan (sekitar 1 km), bukan alamat rumah."}
      Lokasi dikirim hanya saat aplikasi dibuka, dan bisa dihentikan kapan saja lewat menu akun.</p>
    <div class="tawar-lokasi-aksi"><button type="button" class="tombol utama-aksi" data-ya>Bagikan lokasi</button>
      <button type="button" class="tombol" data-tidak>Jangan</button></div>`;
  document.body.append(el);
  el.addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    el.remove();
    await aturIzin(b.hasAttribute("data-ya"));
  });
}

/** Pilihan "Lokasi: dibagikan / tidak dibagikan" di menu akun. */
function perbaruiMenu() {
  const menu = document.querySelector(".akun .menu-jatuh");
  if (!menu || !st) return;
  let b = menu.querySelector("[data-lokasi]");
  if (!b) {
    b = document.createElement("button");
    b.type = "button";
    b.setAttribute("data-lokasi", "");
    menu.querySelector("[data-keluar]")?.before(b);
    b.addEventListener("click", () => aturIzin(st.izin !== "ya"));
  }
  b.textContent = st.izin === "ya" ? "Berhenti berbagi lokasi" : "Bagikan lokasi ke Administrator";
}

/** Dipasang di setiap halaman setelah akun Firebase dipastikan aktif. `sesi`: { peran, nama }. */
export async function pasangKehadiran(sesi) {
  if (st) return;
  const s = await siap().catch(() => null);
  if (!s) return;
  st = { ...s, peran: sesi.peran, nama: sesi.nama, izin: "belum", lokasi: null, lokasiWaktu: 0, dipakai: true, statusTerkirim: "" };
  try {
    const lama = await s.fb.getDoc(s.fb.doc(s.db, KOLEKSI_KEHADIRAN, s.uid));
    const d = lama.exists() ? lama.data() : null;
    st.izin = d?.izin_lokasi || localStorage.getItem(KUNCI_IZIN(s.uid)) || "belum";
    if (st.izin === "ya" && d?.lokasi) { st.lokasi = d.lokasi; st.lokasiWaktu = milidetik(d.lokasi_waktu); }
  } catch { /* pakai bawaan */ }
  if (st.izin === "ya" && Date.now() - st.lokasiWaktu > LOKASI_MS) await perbaruiLokasi();
  await detak("aktif");
  catat("buka", judulKini());
  perbaruiMenu();
  if (st.izin === "belum" && navigator.geolocation) setTimeout(tawarkanLokasi, 2500);

  const tandai = () => { st.dipakai = true; };
  for (const j of ["pointerdown", "keydown", "scroll", "touchstart"]) addEventListener(j, tandai, { passive: true, capture: true });
  setInterval(async () => {
    if (document.hidden) return;
    const status = st.dipakai ? "aktif" : "diam";
    st.dipakai = false;
    if (status === "diam" && st.statusTerkirim === "diam") return; // tidak ada yang berubah, hemat kuota
    if (st.izin === "ya" && Date.now() - st.lokasiWaktu > LOKASI_MS) await perbaruiLokasi();
    detak(status);
  }, DETAK_MS);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { if (st.statusTerkirim !== "diam") detak("diam"); } else { st.dipakai = true; detak("aktif"); }
  });
}

/** Catat masuk atau keluar dari halaman Masuk (sebelum pindah halaman). Tidak pernah melempar galat. */
export async function catatMasukKeluar(aksi, sesi) {
  const tunggu = new Promise((r) => setTimeout(r, 2500));
  const kerja = (async () => {
    const s = await siap();
    if (!s) return;
    st ||= { ...s, peran: sesi.peran, nama: sesi.nama, izin: "belum", lokasi: null, lokasiWaktu: 0, dipakai: true, statusTerkirim: "" };
    try {
      const lama = await s.fb.getDoc(s.fb.doc(s.db, KOLEKSI_KEHADIRAN, s.uid));
      const d = lama.exists() ? lama.data() : null;
      st.izin = d?.izin_lokasi || "belum";
      if (st.izin === "ya" && d?.lokasi) { st.lokasi = d.lokasi; st.lokasiWaktu = milidetik(d.lokasi_waktu); }
    } catch { /* abaikan */ }
    if (aksi === "masuk" && st.izin === "ya") await perbaruiLokasi();
    await Promise.all([catat(aksi), detak(aksi === "keluar" ? "keluar" : "aktif")]);
  })().catch(() => {});
  await Promise.race([kerja, tunggu]);
}

/* ---------- untuk tampilan Administrator */

/** Pantau kehadiran semua akun (hanya berhasil untuk pengelola akun). */
export async function pantauKehadiran(saatBerubah, saatGalat) {
  const fk = await import("./firebase-klien.js");
  const { fb, db } = await fk.firebaseSiap();
  return fb.onSnapshot(fb.collection(db, KOLEKSI_KEHADIRAN), (snap) => saatBerubah(snap.docs.map((d) => ({ uid: d.id, ...d.data() }))), saatGalat);
}

/** Pantau log aktivitas terbaru. */
export async function pantauAktivitas(saatBerubah, saatGalat, jumlah = 300) {
  const fk = await import("./firebase-klien.js");
  const { fb, db } = await fk.firebaseSiap();
  const q = fb.query(fb.collection(db, KOLEKSI_AKTIVITAS), fb.orderBy("waktu", "desc"), fb.limit(jumlah));
  return fb.onSnapshot(q, (snap) => saatBerubah(snap.docs.map((d) => ({ id: d.id, ...d.data() }))), saatGalat);
}

export const _uji = { milidetik };

// Catat galat yang terjadi di perangkat pengguna ke Firestore (lbp_galat), supaya Administrator tahu ada halaman yang
// rusak di ponsel atau peramban tertentu tanpa menunggu laporan. Hemat kuota: paling banyak 3 catatan per sesi dan galat
// yang sama hanya sekali. Yang dicatat hanya pesan galat, letaknya di kode, halaman, peramban, dan lebar layar; tidak ada
// isi formulir. Catatan terhapus sendiri setelah 30 hari (kolom hapus_pada, kebijakan TTL Firestore).

export const MAKS_PER_SESI = 3;
export const SIMPAN_HARI_GALAT = 30;
const KUNCI_SESI = "lbp-galat-terkirim";

const potong = (s, n) => String(s ?? "").slice(0, n);

/** Galat yang bukan dari situs ini atau tidak bisa ditindaklanjuti (ekstensi peramban, skrip luar, gangguan jaringan). */
export function abaikan(g) {
  const teks = `${g.pesan} ${g.sumber} ${g.tumpukan}`;
  return !g.pesan || /^Script error\.?$/i.test(g.pesan) || /ResizeObserver loop/i.test(g.pesan)
    || /(chrome|moz|safari(-web)?)-extension:/i.test(teks)
    || /Failed to fetch|NetworkError|Load failed|network error|client is offline|unavailable/i.test(g.pesan)
    || /AbortError|The user aborted/i.test(g.pesan);
}

/** Ringkas event `error` atau `unhandledrejection` menjadi { pesan, sumber, tumpukan }. Murni, bisa diuji di Node. */
export function ringkasGalat(e, asal = "") {
  const err = e?.error ?? e?.reason ?? null;
  const pesan = potong(err?.message || (typeof err === "string" ? err : "") || e?.message || (err ? String(err) : ""), 300);
  const berkas = (e?.filename || "").replace(asal, "");
  const sumber = potong(berkas ? `${berkas}:${e.lineno || 0}:${e.colno || 0}` : "", 200);
  const tumpukan = potong(String(err?.stack || "").split(asal).join(""), 1200);
  return { pesan, sumber, tumpukan, jenis: e?.type === "unhandledrejection" ? "janji" : "galat" };
}

/** Sidik sederhana supaya galat yang sama tidak dikirim berulang dalam satu sesi. */
export const sidikGalat = (g) => `${g.pesan}|${g.sumber}`.slice(0, 200);

const ms = (t) => (t?.toMillis ? t.toMillis() : t ? new Date(t).getTime() : 0);

/** Nama peramban dan sistem yang mudah dibaca dari user agent, mis. "Chrome, Android". */
export function namaPeramban(ua = "") {
  const p = /SamsungBrowser/.test(ua) ? "Samsung Internet" : /Edg\//.test(ua) ? "Edge" : /OPR\//.test(ua) ? "Opera"
    : /Firefox\//.test(ua) ? "Firefox" : /CriOS|Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Lainnya";
  const s = /Android/.test(ua) ? "Android" : /iPhone|iPad|iPod/.test(ua) ? "iOS" : /Windows/.test(ua) ? "Windows"
    : /Mac OS X/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : "";
  return s ? `${p}, ${s}` : p;
}

/** Kelompokkan catatan galat yang sama (pesan dan letak sama), terbaru dulu. Murni, bisa diuji di Node. */
export function kelompokkanGalat(daftar) {
  const per = new Map();
  for (const g of daftar) {
    const k = `${g.pesan}|${g.sumber}`;
    const x = per.get(k) || { pesan: g.pesan, sumber: g.sumber, tumpukan: g.tumpukan, jumlah: 0, terakhir: 0, id: [],
      pengguna: new Set(), halaman: new Set(), peramban: new Set(), peran: new Set() };
    x.jumlah += 1;
    x.id.push(g.id);
    x.pengguna.add(g.uid);
    x.halaman.add(g.halaman);
    x.peramban.add(namaPeramban(g.peramban));
    x.peran.add(g.peran);
    x.terakhir = Math.max(x.terakhir, ms(g.waktu));
    per.set(k, x);
  }
  return [...per.values()].sort((a, b) => b.terakhir - a.terakhir);
}

function bacaTerkirim() {
  try { return JSON.parse(sessionStorage.getItem(KUNCI_SESI) || "[]"); } catch { return []; }
}

/**
 * Mulai mencatat galat untuk akun yang sedang masuk. `awal`: galat yang terjadi sebelum modul ini termuat (ditampung
 * app.js). Dipanggil sekali per halaman.
 */
export function pasangCatatGalat(sesi, awal = []) {
  if (!sesi?.uid || window.__lbpCatatGalat) return;
  window.__lbpCatatGalat = true;
  const asal = location.origin;

  async function kirim(e) {
    const g = ringkasGalat(e, asal);
    if (abaikan(g)) return;
    const terkirim = bacaTerkirim();
    const sidik = sidikGalat(g);
    if (terkirim.length >= MAKS_PER_SESI || terkirim.includes(sidik)) return;
    terkirim.push(sidik);
    try { sessionStorage.setItem(KUNCI_SESI, JSON.stringify(terkirim)); } catch { /* abaikan */ }
    try {
      const fk = await import("./firebase-klien.js");
      const { fb, db } = await fk.firebaseSiap();
      await fb.addDoc(fb.collection(db, "lbp_galat"), {
        uid: sesi.uid, peran: sesi.peran, halaman: potong(location.pathname.split("/").pop() || "index.html", 60),
        ...g, peramban: potong(navigator.userAgent, 250), layar: `${innerWidth}x${innerHeight}`,
        daring: navigator.onLine !== false, waktu: fb.serverTimestamp(),
        hapus_pada: fb.Timestamp.fromMillis(Date.now() + SIMPAN_HARI_GALAT * 864e5),
      });
    } catch { /* mencatat galat tidak boleh menimbulkan galat baru */ }
  }

  for (const e of awal) kirim(e);
  addEventListener("error", (e) => { if (e.target === window || e.target === undefined) kirim(e); });
  addEventListener("unhandledrejection", kirim);
}

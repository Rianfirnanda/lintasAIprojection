// Status jaringan dan layanan di kaki halaman. Semua pemeriksaan berjalan di browser pengunjung dan diperbarui
// langsung: jaringan tiap 30 detik, layanan tiap menit, dan seketika saat internet putus atau tersambung lagi.
// Tidak ada data yang dikirim ke mana pun; yang dicek hanya apakah alamat layanan bisa dijangkau.
import { esc, waktu } from "./app.js";

const JEDA_JARINGAN = 30000;
const JEDA_LAYANAN = 60000;
const BATAS_WAKTU = 8000;
const URUT = { baik: 0, netral: 0, memeriksa: 0, waspada: 1, gangguan: 2 };

const jam = (t) => (t?.toDate ? t.toDate() : t ? new Date(t) : null);
const fmtJam = (d) => d.toLocaleString("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

async function denganBatas(janji) {
  const ab = new AbortController();
  const t = setTimeout(() => ab.abort(), BATAS_WAKTU);
  try { return await janji(ab.signal); } finally { clearTimeout(t); }
}

/** Waktu tempuh ke situs sendiri (ms), atau null bila gagal. */
async function ukurJaringan() {
  if (!navigator.onLine) return { luring: true, ms: null };
  const t0 = performance.now();
  try {
    const r = await denganBatas((signal) => fetch(`data/meta.json?cek=${Date.now()}`, { method: "HEAD", cache: "no-store", signal }));
    return { luring: false, ok: r.ok, ms: Math.round(performance.now() - t0) };
  } catch {
    return { luring: !navigator.onLine, ok: false, ms: null };
  }
}

/** Apakah alamat bisa dijangkau. Jawaban tidak dibaca (mode no-cors); cukup tahu sambungannya berhasil. */
async function terjangkau(url) {
  try {
    await denganBatas((signal) => fetch(url, { mode: "no-cors", cache: "no-store", signal }));
    return true;
  } catch {
    return false;
  }
}

/** Alamat Firestore dan login Google (atau emulator saat uji lokal). */
async function alamatFirebase() {
  try {
    const { konfigurasi } = await (await fetch("data/firebase.json", { cache: "no-cache" })).json();
    const lokal = ["localhost", "127.0.0.1"].includes(location.hostname);
    if (konfigurasi?.emulator && lokal) {
      const [h, p] = konfigurasi.emulator.firestore;
      return { database: `http://${h}:${p}/`, login: `${String(konfigurasi.emulator.auth).replace(/\/$/, "")}/` };
    }
  } catch { /* pakai alamat produksi */ }
  return { database: "https://firestore.googleapis.com/", login: "https://identitytoolkit.googleapis.com/" };
}

function sinyal(ms, luring) {
  if (luring || ms == null) return 0;
  if (ms < 300) return 4;
  if (ms < 800) return 3;
  if (ms < 1500) return 2;
  return 1;
}

const batang = (n) => `<span class="sinyal" aria-hidden="true">${[1, 2, 3, 4].map((i) => `<i class="${i <= n ? "isi" : ""}"></i>`).join("")}</span>`;

/**
 * Pasang panel status ke `wadah`.
 * @param {HTMLElement} wadah
 * @param {{ meta: object|null, firebase: boolean, masuk: boolean }} opsi  masuk = pengguna sudah masuk lewat Firebase
 */
export function pasangStatusLayanan(wadah, { meta, firebase = false, masuk = false } = {}) {
  const baris = {
    jaringan: { label: "Jaringan Anda", keadaan: "memeriksa", teks: "Memeriksa…" },
    situs: { label: "Situs", keadaan: "memeriksa", teks: "Memeriksa…" },
    data: { label: "Data harga", keadaan: "memeriksa", teks: "Memeriksa…" },
  };
  if (firebase) {
    baris.database = { label: "Basis data", keadaan: "memeriksa", teks: "Memeriksa…" };
    baris.login = { label: "Login Google", keadaan: "memeriksa", teks: "Memeriksa…" };
    if (masuk) baris.mesin = { label: "Mesin pengolah", keadaan: "memeriksa", teks: "Memeriksa…" };
  }
  let kualitas = 0;
  let diperiksa = null;
  let luring = !navigator.onLine;
  let lewatSnapshot = false; // basis data dinilai dari sambungan langsung Firestore (lebih akurat) bila sudah masuk

  wadah.innerHTML = `
    <div class="status-kepala">
      <button type="button" class="status-buka" aria-expanded="false" title="Lihat rincian status">
        <span class="status-titik netral" aria-hidden="true"></span>
        <span class="status-judul"><b role="status" aria-live="polite">Memeriksa layanan…</b><small></small></span>
        <svg class="status-panah" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M6 15l6-6 6 6"/></svg>
      </button>
      <button type="button" class="status-ulang" title="Periksa lagi" aria-label="Periksa status layanan lagi">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 11a8 8 0 00-14-4M4 5v4h4M4 13a8 8 0 0014 4M20 19v-4h-4"/></svg>
      </button>
    </div>
    <ul class="status-daftar" hidden></ul>`;
  const titik = wadah.querySelector(".status-titik");
  const judul = wadah.querySelector(".status-judul b");
  const kecil = wadah.querySelector(".status-judul small");
  const daftar = wadah.querySelector(".status-daftar");

  function gambar() {
    daftar.innerHTML = Object.entries(baris).map(([k, b]) => `<li class="${b.keadaan}">
      <span class="status-titik ${b.keadaan}" aria-hidden="true"></span>
      <span class="status-label">${esc(b.label)}</span>
      <span class="status-nilai">${k === "jaringan" ? batang(kualitas) : ""}${esc(b.teks)}</span></li>`).join("");
    const terburuk = Object.values(baris).reduce((a, b) => (URUT[b.keadaan] > URUT[a] ? b.keadaan : a), "baik");
    const menunggu = Object.values(baris).some((b) => b.keadaan === "memeriksa");
    const ringkas = luring ? ["gangguan", "Anda sedang luring"]
      : menunggu ? ["netral", "Memeriksa layanan…"]
        : terburuk === "gangguan" ? ["gangguan", "Ada layanan yang terganggu"]
          : terburuk === "waspada" ? ["waspada", "Layanan berjalan, ada yang lambat"]
            : ["baik", "Semua layanan berjalan normal"];
    titik.className = `status-titik ${ringkas[0]}`;
    wadah.dataset.keadaan = ringkas[0];
    if (judul.textContent !== ringkas[1]) judul.textContent = ringkas[1];
    kecil.textContent = luring ? "Periksa Wi-Fi atau data seluler. Halaman memeriksa ulang sendiri."
      : diperiksa ? `Diperiksa ${diperiksa.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })} · diperbarui otomatis` : "";
  }

  function nilaiData() {
    if (!meta?.dibuat) {
      baris.data = { ...baris.data, keadaan: "waspada", teks: "Belum tersedia" };
      return;
    }
    const umurJam = (Date.now() - new Date(meta.dibuat).getTime()) / 3.6e6;
    baris.data = umurJam < 36
      ? { ...baris.data, keadaan: "baik", teks: `Terbaru, ${waktu(meta.dibuat)}` }
      : { ...baris.data, keadaan: "waspada", teks: `Belum diperbarui ${Math.round(umurJam / 24)} hari` };
  }

  async function periksaJaringan() {
    const h = await ukurJaringan();
    luring = h.luring;
    kualitas = sinyal(h.ms, h.luring);
    const jenis = navigator.connection?.effectiveType;
    const label = { 4: "Sangat baik", 3: "Baik", 2: "Lambat", 1: "Sangat lambat" }[kualitas];
    baris.jaringan = luring ? { ...baris.jaringan, keadaan: "gangguan", teks: "Terputus" }
      : h.ms == null ? { ...baris.jaringan, keadaan: "gangguan", teks: "Tidak stabil" }
        : { ...baris.jaringan, keadaan: kualitas >= 3 ? "baik" : "waspada",
          teks: `${label}${jenis ? ` · ${jenis.toUpperCase()}` : ""} · ${h.ms} ms` };
    baris.situs = luring ? { ...baris.situs, keadaan: "netral", teks: "Menunggu internet" }
      : h.ok ? { ...baris.situs, keadaan: "baik", teks: "Berjalan" }
        : { ...baris.situs, keadaan: "gangguan", teks: "Tidak terjangkau" };
    diperiksa = new Date();
    gambar();
  }

  let alamat = null;
  async function periksaLayanan() {
    nilaiData();
    if (firebase && !luring) {
      alamat ||= await alamatFirebase();
      const [db, lg] = await Promise.all([lewatSnapshot ? null : terjangkau(alamat.database), terjangkau(alamat.login)]);
      if (!lewatSnapshot) baris.database = { ...baris.database, keadaan: db ? "baik" : "gangguan", teks: db ? "Tersambung" : "Tidak terjangkau" };
      baris.login = { ...baris.login, keadaan: lg ? "baik" : "gangguan", teks: lg ? "Berjalan" : "Tidak terjangkau" };
    }
    gambar();
  }

  // Bila sudah masuk: status mesin dan sambungan basis data dibaca langsung dari Firestore (lbp_status/pipeline).
  if (firebase && masuk) {
    import("./firebase-klien.js").then(({ firebaseSiap }) => firebaseSiap()).then(({ fb, db }) => {
      fb.onSnapshot(fb.doc(db, "lbp_status", "pipeline"), { includeMetadataChanges: true }, (d) => {
        lewatSnapshot = true;
        const dariServer = !d.metadata.fromCache;
        baris.database = { ...baris.database, keadaan: dariServer ? "baik" : luring ? "gangguan" : "waspada",
          teks: dariServer ? "Tersambung langsung" : "Menyambung ulang…" };
        const st = d.exists() ? d.data() : null;
        const selesai = jam(st?.selesai);
        baris.mesin = !st ? { ...baris.mesin, keadaan: "netral", teks: "Belum ada catatan" }
          : st.status === "berjalan" ? { ...baris.mesin, keadaan: "baik", teks: "Sedang memproses data" }
            : st.hasil === "success" ? { ...baris.mesin, keadaan: "baik", teks: selesai ? `Normal, terakhir ${fmtJam(selesai)}` : "Normal" }
              : { ...baris.mesin, keadaan: "gangguan", teks: selesai ? `Proses terakhir gagal, ${fmtJam(selesai)}` : "Proses terakhir gagal" };
        gambar();
      }, () => {
        lewatSnapshot = false;
        delete baris.mesin; // akun tanpa izin membaca status: baris disembunyikan
        gambar();
      });
    }).catch(() => { delete baris.mesin; gambar(); });
  }

  const buka = wadah.querySelector(".status-buka");
  buka.addEventListener("click", (e) => {
    e.stopPropagation();
    daftar.hidden = !daftar.hidden;
    buka.setAttribute("aria-expanded", String(!daftar.hidden));
  });
  document.addEventListener("click", (e) => { if (!wadah.contains(e.target)) { daftar.hidden = true; buka.setAttribute("aria-expanded", "false"); } });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { daftar.hidden = true; buka.setAttribute("aria-expanded", "false"); } });
  const semua = () => Promise.all([periksaJaringan(), periksaLayanan()]);
  wadah.querySelector(".status-ulang").addEventListener("click", (e) => {
    const t = e.currentTarget;
    t.classList.add("berputar");
    semua().finally(() => setTimeout(() => t.classList.remove("berputar"), 400));
  });
  addEventListener("online", () => { luring = false; semua(); });
  addEventListener("offline", () => { luring = true; periksaJaringan(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) semua(); });
  navigator.connection?.addEventListener?.("change", periksaJaringan);
  setInterval(() => { if (!document.hidden) periksaJaringan(); }, JEDA_JARINGAN);
  setInterval(() => { if (!document.hidden) periksaLayanan(); }, JEDA_LAYANAN);
  nilaiData();
  gambar();
  semua();
}

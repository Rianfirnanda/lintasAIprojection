// Utilitas bersama dashboard (ES module, tanpa build step).

const BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
const BULAN_PANJANG = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"];

export const HALAMAN = [
  ["index.html", "Dashboard"],
  ["sinyal.html", "Sinyal & Tindak Lanjut"],
  ["laporan.html", "Laporan"],
  ["kinerja.html", "Kinerja"],
  ["kualitas.html", "Quality Gate"],
  ["model.html", "Mutu Model"],
  ["sumber.html", "Sumber Data"],
  ["input.html", "Input Harga"],
  ["tentang.html", "Metodologi"],
];

export const JENIS_SINYAL = {
  anomali_harga: "Anomali harga",
  proyeksi_naik: "Proyeksi naik",
  risiko_hari_raya: "Risiko hari raya",
  data_terlambat: "Data terlambat",
  drift: "Drift model/data",
};

export const STATUS_SINYAL = {
  baru: "Baru",
  perlu_verifikasi: "Perlu verifikasi",
  terverifikasi: "Terverifikasi",
  false_alarm: "False alarm",
  ditindaklanjuti: "Ditindaklanjuti",
  selesai: "Selesai",
};

let metaCache = null;

export async function muatJSON(nama) {
  const versi = metaCache?.dibuat ? `?v=${encodeURIComponent(metaCache.dibuat)}` : `?t=${Date.now()}`;
  const r = await fetch(`data/${nama}${versi}`, { cache: "no-cache" });
  if (!r.ok) throw new Error(`Gagal memuat data/${nama} (HTTP ${r.status})`);
  return r.json();
}

export async function muatMeta() {
  if (!metaCache) metaCache = await muatJSON("meta.json");
  return metaCache;
}

export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export function rp(x) {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  return "Rp" + Math.round(x).toLocaleString("id-ID");
}

export function angka(x, digit = 0) {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  return Number(x).toLocaleString("id-ID", { minimumFractionDigits: digit, maximumFractionDigits: digit });
}

export function persen(x, digit = 1, bertanda = false) {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  const t = Number(x).toLocaleString("id-ID", { minimumFractionDigits: digit, maximumFractionDigits: digit });
  return (bertanda && x > 0 ? "+" : "") + t + "%";
}

export function tgl(iso, panjang = false) {
  if (!iso) return "–";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${d} ${(panjang ? BULAN_PANJANG : BULAN)[m - 1]} ${y}`;
}

export function waktu(iso) {
  if (!iso) return "–";
  const d = new Date(iso);
  return `${tgl(iso.slice(0, 10))} ${String(d.getHours()).padStart(2, "0")}.${String(d.getMinutes()).padStart(2, "0")}`;
}

export function lencanaKeparahan(k) {
  if (!k) return "";
  const label = { tinggi: "Tinggi", sedang: "Sedang", rendah: "Rendah" }[k] || k;
  return `<span class="lencana ${esc(k)}">${esc(label)}</span>`;
}

export function lencanaStatus(s) {
  const kelas = { terverifikasi: "tinggi", ditindaklanjuti: "info", selesai: "baik", false_alarm: "polos" }[s] || "";
  return `<span class="lencana ${kelas}">${esc(STATUS_SINYAL[s] || s)}</span>`;
}

export function kelasPerubahan(x, ambang = 5) {
  if (x === null || x === undefined) return "";
  if (x >= ambang * 2) return "sel-naik-kuat";
  if (x >= ambang) return "sel-naik";
  if (x <= -ambang * 2) return "sel-turun-kuat";
  if (x <= -ambang) return "sel-turun";
  return "";
}

// ---------- tema
function temaTersimpan() {
  try { return localStorage.getItem("tema"); } catch { return null; }
}
function simpanTema(t) {
  try { t ? localStorage.setItem("tema", t) : localStorage.removeItem("tema"); } catch { /* abaikan */ }
}
const t0 = temaTersimpan();
if (t0) document.documentElement.dataset.theme = t0;

export function temaGelap() {
  const t = document.documentElement.dataset.theme;
  if (t) return t === "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

const pendengarTema = new Set();
export function saatTemaBerubah(fn) { pendengarTema.add(fn); }
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => pendengarTema.forEach((f) => f()));

export function warna(nama) {
  return getComputedStyle(document.documentElement).getPropertyValue(`--${nama}`).trim();
}

// ---------- kerangka halaman
const IKON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 6-6"/></svg>`;

export async function pasangKerangka(aktif) {
  const kepala = document.createElement("header");
  kepala.className = "kepala";
  kepala.innerHTML = `
    <div class="kepala-dalam">
      <a class="merek" href="index.html" style="color:inherit;text-decoration:none">
        <span class="merek-ikon">${IKON}</span>
        <span><strong>Pemantauan Harga Pangan</strong><small>BPS Kabupaten Bengkulu Tengah · TPID</small></span>
      </a>
      <div class="kepala-kanan">
        <nav class="navigasi" aria-label="Navigasi utama">
          ${HALAMAN.map(([h, n]) => `<a href="${h}"${h === aktif ? ' aria-current="page"' : ""}>${n}</a>`).join("")}
        </nav>
        <button class="tombol tombol-tema" type="button" aria-label="Ganti tema terang/gelap" title="Ganti tema">◐</button>
      </div>
    </div>`;
  document.body.prepend(kepala);
  kepala.querySelector(".tombol-tema").addEventListener("click", () => {
    const baru = temaGelap() ? "light" : "dark";
    document.documentElement.dataset.theme = baru;
    simpanTema(baru);
    pendengarTema.forEach((f) => f());
  });

  const kaki = document.createElement("footer");
  kaki.className = "kaki";
  document.body.append(kaki);

  let meta = null;
  try {
    meta = await muatMeta();
  } catch (e) {
    kaki.innerHTML = `<p>Data belum tersedia: ${esc(e.message)}. Jalankan pipeline (GitHub Actions) terlebih dahulu.</p>`;
    return null;
  }
  if (meta.mode_demo) {
    const b = document.createElement("div");
    b.className = "banner-demo";
    b.setAttribute("role", "status");
    b.innerHTML = `<div><strong>DATA DEMO (sintetis) — bukan angka resmi.</strong> Sistem berjalan dalam mode demo karena belum ada berkas harga nyata di <code>data/masuk/harga</code>. Mode demo otomatis mati setelah data pertama diunggah.</div>`;
    kepala.after(b);
  }
  const tautanRun = meta.url_run ? ` · <a href="${esc(meta.url_run)}">log proses</a>` : "";
  const tautanRepo = meta.url_repo ? ` · <a href="${esc(meta.url_repo)}">repositori</a>` : "";
  kaki.innerHTML = `
    <p>Diperbarui ${esc(waktu(meta.dibuat))} WIB · data terakhir ${esc(tgl(meta.tanggal_data_terakhir))} · versi pipeline ${esc(meta.versi)}${meta.commit ? " · commit " + esc(meta.commit.slice(0, 7)) : ""}${tautanRun}${tautanRepo}</p>
    <p>Sinyal dan proyeksi adalah alat bantu analisis dan wajib diverifikasi manusia sebelum menjadi dasar keputusan. Angka pada dashboard ini bukan rilis resmi BPS.</p>
    <p>Sumber: BPS Kabupaten Bengkulu Tengah (pencatatan harga pasar), Pemda (bila tersedia), cuaca © Open-Meteo (CC BY 4.0), peta © kontributor OpenStreetMap.</p>
    ${tautanLayanan(meta.layanan)}`;
  return meta;
}

function tautanLayanan(l) {
  if (!l) return "";
  const t = [];
  if (l.url_pengaduan_eksternal) t.push(`<a href="${esc(l.url_pengaduan_eksternal)}">Pengaduan (WhatsApp/PST)</a>`);
  if (l.url_pengaduan) t.push(`<a href="${esc(l.url_pengaduan)}">Laporkan data tidak sesuai</a>`);
  if (l.url_survei_eksternal) t.push(`<a href="${esc(l.url_survei_eksternal)}">Survei kepuasan</a>`);
  else if (l.url_survei) t.push(`<a href="${esc(l.url_survei)}">Survei kepuasan</a>`);
  return t.length ? `<p>Layanan: ${t.join(" · ")}</p>` : "";
}

export function tampilkanGalat(wadah, e) {
  wadah.innerHTML = `<div class="pesan galat">Gagal memuat data: ${esc(e.message || e)}</div>`;
}

export function unduhTeks(namaBerkas, isi, tipe = "text/csv") {
  const blob = new Blob([isi], { type: `${tipe};charset=utf-8` });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = namaBerkas;
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

export function keCSV(kolom, baris) {
  const kutip = (v) => {
    const s = String(v ?? "");
    return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [kolom.join(","), ...baris.map((b) => kolom.map((k) => kutip(b[k])).join(","))].join("\n") + "\n";
}

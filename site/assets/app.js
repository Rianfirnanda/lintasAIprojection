// Utilitas bersama dashboard (ES module, tanpa build step).
import { PERAN, menuPeran, peranAktif, sesi, periksaAkses, keluar } from "./akses.js";

const BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
const BULAN_PANJANG = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"];


export const JENIS_SINYAL = {
  anomali_harga: "Harga janggal",
  proyeksi_naik: "Diperkirakan naik",
  risiko_hari_raya: "Risiko hari raya",
  data_terlambat: "Data terlambat",
  drift: "Pola berubah",
};

export const STATUS_SINYAL = {
  baru: "Baru",
  perlu_verifikasi: "Perlu dicek",
  terverifikasi: "Sudah dicek, benar",
  false_alarm: "Salah peringatan",
  ditindaklanjuti: "Sedang ditangani",
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

// ---------- tema: "light" (bawaan), "dark", atau "auto" (mengikuti perangkat)
const KUNCI_TEMA = "tema-tampilan";
export function modeTema() {
  try { const t = localStorage.getItem(KUNCI_TEMA); return ["light", "dark", "auto"].includes(t) ? t : "light"; } catch { return "light"; }
}
const gelapPerangkat = () => matchMedia("(prefers-color-scheme: dark)").matches;
function terapkanTema() {
  const m = modeTema();
  if (m === "dark" || (m === "auto" && gelapPerangkat())) document.documentElement.dataset.theme = "dark";
  else delete document.documentElement.dataset.theme;
}
terapkanTema();

export function temaGelap() {
  return document.documentElement.dataset.theme === "dark";
}

const pendengarTema = new Set();
export function saatTemaBerubah(fn) { pendengarTema.add(fn); }

export function warna(nama) {
  return getComputedStyle(document.documentElement).getPropertyValue(`--${nama}`).trim();
}

// Gaya bawaan Chart.js mengikuti token tema (huruf Plex, garis tipis, tooltip datar).
function aturGayaGrafik() {
  const C = window.Chart;
  if (!C) return;
  C.defaults.font.family = warna("sans") || "sans-serif";
  C.defaults.font.size = 11;
  C.defaults.color = warna("muted");
  C.defaults.borderColor = warna("grid");
  const tip = C.defaults.plugins.tooltip;
  Object.assign(tip, {
    backgroundColor: warna("kaca-atas"), titleColor: warna("ink"), bodyColor: warna("ink-2"),
    borderColor: warna("rule-2"), borderWidth: 1, cornerRadius: 10, padding: 10, boxPadding: 4,
    titleFont: { family: warna("sans"), size: 12, weight: "600" }, bodyFont: { family: warna("sans"), size: 12 },
  });
}
aturGayaGrafik();

export function setTema(mode) {
  try { localStorage.setItem(KUNCI_TEMA, mode); } catch { /* abaikan */ }
  terapkanTema();
  aturGayaGrafik();
  pendengarTema.forEach((f) => f());
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if (modeTema() === "auto") setTema("auto");
});

// ---------- kerangka halaman
export const NAMA_SISTEM = "Lintas Benteng Projection";
// Logo resmi BPS (diambil dari dokumen BPS Kabupaten Bengkulu Tengah).
const LOGO = `<img class="merek-ikon" src="assets/logo-bps.png" alt="" width="38" height="30">`;
const tundaSelamanya = () => new Promise(() => {});

async function ikonUI(nama, ukuran) {
  const { ikon } = await import("./dashboard.js");
  return ikon(nama, ukuran);
}

/** Memasang bilah atas dan kaki halaman, memeriksa hak akses, lalu mengembalikan data meta. */
export async function pasangKerangka(aktif) {
  const izin = periksaAkses(aktif);
  if (izin === "masuk") {
    location.replace(`masuk.html?lanjut=${encodeURIComponent(aktif)}`);
    return tundaSelamanya();
  }
  const peran = peranAktif();
  const pengguna = sesi();
  const { utama: menuUtama, lainnya } = menuPeran(peran);
  const tautan = (m) => `<a href="${m.href}"${m.href === aktif ? ' aria-current="page"' : ""}>${m.label}</a>`;

  const kepala = document.createElement("header");
  kepala.className = "kepala";
  kepala.innerHTML = `
    <div class="kepala-dalam">
      <a class="merek" href="index.html" aria-label="${NAMA_SISTEM}, beranda">
        ${LOGO}
        <span class="merek-teks"><span class="merek-nama">${NAMA_SISTEM}</span><span class="merek-sub">BPS Kabupaten Bengkulu Tengah</span></span>
      </a>
      <nav class="navigasi" aria-label="Menu utama">
        ${menuUtama.map(tautan).join("")}
        ${lainnya.length ? `<div class="lainnya"><button class="lainnya-tombol" type="button" aria-expanded="false" aria-haspopup="true">Lainnya ▾</button>
          <div class="menu-jatuh lainnya-menu" hidden>${lainnya.map(tautan).join("")}</div></div>` : ""}
      </nav>
      <div class="kepala-kanan">
        <span class="status-mini" id="status-mini" hidden><i></i><span></span></span>
        ${pengguna ? `<div class="akun"><button class="akun-tombol" type="button" aria-expanded="false" aria-haspopup="true">
            <span class="avatar">${esc((pengguna.nama || "?").trim().charAt(0).toUpperCase())}</span>
            <span class="akun-nama">${esc(pengguna.nama)}<small>${esc(PERAN[peran].nama)}</small></span></button>
          <div class="menu-jatuh" hidden>
            <div class="kepala-menu"><b>${esc(pengguna.nama)}</b><span>${esc(PERAN[peran].nama)}</span></div>
            <button type="button" data-keluar>Keluar</button>
          </div></div>`
        : `<a class="tombol utama-aksi tombol-masuk" href="masuk.html?lanjut=${encodeURIComponent(aktif)}">Masuk</a>`}
      </div>
    </div>`;
  document.body.prepend(kepala);

  // menu tarik-turun: buka/tutup, tutup saat klik di luar atau tekan Esc
  const pasangMenu = (tombol) => {
    const menu = tombol.nextElementSibling;
    tombol.addEventListener("click", (e) => {
      e.stopPropagation();
      const buka = menu.hidden;
      document.querySelectorAll(".menu-jatuh").forEach((m) => { m.hidden = true; });
      menu.hidden = !buka;
      tombol.setAttribute("aria-expanded", String(buka));
    });
  };
  kepala.querySelectorAll(".akun-tombol, .lainnya-tombol").forEach(pasangMenu);
  document.addEventListener("click", () => kepala.querySelectorAll(".menu-jatuh").forEach((m) => { m.hidden = true; }));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") kepala.querySelectorAll(".menu-jatuh").forEach((m) => { m.hidden = true; }); });
  // Keluar lewat halaman Masuk (yang membersihkan sesi lalu kembali ke beranda), supaya halaman dengan CSP ketat tidak perlu memuat pustaka pihak lain.
  kepala.querySelector("[data-keluar]")?.addEventListener("click", () => { location.href = "masuk.html?keluar=1"; });
  const navAktif = kepala.querySelector('.navigasi [aria-current="page"]');
  const navEl = navAktif?.parentElement;
  if (navEl && navAktif.offsetLeft + navAktif.offsetWidth > navEl.clientWidth) navEl.scrollLeft = Math.max(0, navAktif.offsetLeft - 16);

  const kaki = document.createElement("footer");
  kaki.className = "kaki";
  document.body.append(kaki);
  const IKON_TEMA = {
    auto: '<circle cx="12" cy="12" r="8"/><path d="M12 4v16" /><path d="M12 4a8 8 0 010 16z" fill="currentColor"/>',
    light: '<circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6L7 7M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4"/>',
    dark: '<path d="M20 14.5A8 8 0 019.5 4 8 8 0 1020 14.5z"/>',
  };
  const NAMA_TEMA = { auto: "Otomatis", light: "Terang", dark: "Gelap" };
  const URUT_TEMA = ["auto", "light", "dark"];
  const pasangTema = () => {
    const tombol = kaki.querySelector("[data-tema-ganti]");
    const m = modeTema();
    tombol.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IKON_TEMA[m]}</svg>`;
    tombol.title = `Tampilan: ${NAMA_TEMA[m]}. Klik untuk ganti.`;
    tombol.setAttribute("aria-label", tombol.title);
  };

  if (izin === "tolak") {
    document.querySelector("main")?.replaceChildren();
    const ikonKunci = await ikonUI("gembokPerisai", 26);
    document.querySelector("main").innerHTML = `<section class="kartu tolak"><span class="ind-ikon merah">${ikonKunci}</span>
      <h1>Halaman ini bukan untuk peran Anda</h1><p>Anda masuk sebagai ${esc(PERAN[peran].nama)}. Gunakan menu di atas.</p>
      <a class="tombol utama-aksi" href="index.html">Ke beranda saya</a></section>`;
  }

  let meta = null;
  try {
    meta = await muatMeta();
  } catch (e) {
    kaki.innerHTML = `<p>Data belum tersedia: ${esc(e.message)}. Jalankan pipeline di GitHub Actions terlebih dahulu.</p>`;
    document.body.classList.add("siap");
    return izin === "tolak" ? tundaSelamanya() : null;
  }
  const umurJam = (Date.now() - new Date(meta.dibuat).getTime()) / 3.6e6;
  const status = kepala.querySelector("#status-mini");
  status.hidden = false;
  status.classList.toggle("tua", umurJam >= 36);
  status.title = `Data terakhir ${tgl(meta.tanggal_data_terakhir)} · versi ${meta.versi}`;
  status.lastElementChild.textContent = umurJam < 36 ? `Diperbarui ${waktu(meta.dibuat)}` : `Belum diperbarui ${Math.round(umurJam / 24)} hari`;
  if (meta.mode_demo) {
    const b = document.createElement("div");
    b.className = "pita-contoh";
    b.setAttribute("role", "status");
    b.innerHTML = `<b>Data contoh.</b> Angka di sini masih untuk uji coba, bukan angka resmi.`;
    kepala.after(b);
  }
  kaki.innerHTML = `
    <div class="kaki-teks">
      <p><strong>${NAMA_SISTEM}</strong> · BPS Kabupaten Bengkulu Tengah${meta.url_repo ? ` · <a href="${esc(meta.url_repo)}">Repositori</a>` : ""}</p>
      <p>Angka di sini membantu analisis, bukan angka resmi BPS. ${tautanLayanan(meta.layanan)}</p>
      <p>Sumber: BPS, Pemda, cuaca Open-Meteo (CC BY 4.0), peta © kontributor OpenStreetMap.</p>
    </div>
    <button type="button" class="tema-ikon" data-tema-ganti></button>`;
  kaki.querySelector("[data-tema-ganti]").addEventListener("click", () => {
    setTema(URUT_TEMA[(URUT_TEMA.indexOf(modeTema()) + 1) % URUT_TEMA.length]);
    pasangTema();
  });
  pasangTema();
  // Grafik kanvas baru memakai huruf Plex setelah berkasnya termuat.
  try { await document.fonts?.ready; } catch { /* abaikan */ }
  document.body.classList.add("siap");
  return izin === "tolak" ? tundaSelamanya() : meta;
}

function tautanLayanan(l) {
  if (!l) return "";
  const t = [];
  if (l.url_pengaduan_eksternal) t.push(`<a href="${esc(l.url_pengaduan_eksternal)}">Pengaduan</a>`);
  else if (l.url_pengaduan) t.push(`<a href="${esc(l.url_pengaduan)}">Laporkan data</a>`);
  if (l.url_survei_eksternal) t.push(`<a href="${esc(l.url_survei_eksternal)}">Survei kepuasan</a>`);
  else if (l.url_survei) t.push(`<a href="${esc(l.url_survei)}">Survei kepuasan</a>`);
  return t.join(" · ");
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

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

// ---------- tema (bawaan: terang; "dark" = mode gelap pilihan pengguna)
const KUNCI_TEMA = "tema-tampilan";
function temaTersimpan() {
  try { return localStorage.getItem(KUNCI_TEMA); } catch { return null; }
}
function simpanTema(t) {
  try { localStorage.setItem(KUNCI_TEMA, t); } catch { /* abaikan */ }
}
if (temaTersimpan() === "dark") document.documentElement.dataset.theme = "dark";

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
    backgroundColor: warna("surface-2"), titleColor: warna("ink"), bodyColor: warna("ink-2"),
    borderColor: warna("rule-2"), borderWidth: 1, cornerRadius: 8, padding: 10, boxPadding: 4,
    titleFont: { family: warna("sans"), size: 12, weight: "600" }, bodyFont: { family: warna("sans"), size: 12 },
  });
}
aturGayaGrafik();

// ---------- kerangka halaman
export const NAMA_SISTEM = "Lintas AI Projection";
// Logo resmi BPS (diambil dari dokumen BPS Kabupaten Bengkulu Tengah).
const IKON = `<img class="merek-ikon" src="assets/logo-bps.png" alt="" width="42" height="33">`;

export async function pasangKerangka(aktif) {
  const kepala = document.createElement("header");
  kepala.className = "kepala";
  kepala.innerHTML = `
    <div class="kepala-dalam">
      <a class="merek" href="index.html" aria-label="${NAMA_SISTEM}, beranda">
        ${IKON}
        <span class="merek-teks"><span class="merek-nama">${NAMA_SISTEM}</span><span class="merek-sub">Pemantauan Harga Pangan · BPS Kabupaten Bengkulu Tengah</span></span>
      </a>
      <div class="kepala-kanan">
        <nav class="navigasi" aria-label="Navigasi utama">
          ${HALAMAN.map(([h, n]) => `<a href="${h}"${h === aktif ? ' aria-current="page"' : ""}>${n}</a>`).join("")}
        </nav>
        <button class="tombol tombol-tema" type="button" aria-label="Ganti tampilan terang atau gelap">${temaGelap() ? "Mode terang" : "Mode gelap"}</button>
      </div>
    </div>`;
  document.body.prepend(kepala);
  // di layar sempit navigasi dapat digulir: pastikan halaman aktif terlihat
  const navAktif = kepala.querySelector('.navigasi [aria-current="page"]');
  if (navAktif) navAktif.parentElement.scrollLeft = Math.max(0, navAktif.offsetLeft - 16);
  const tombolTema = kepala.querySelector(".tombol-tema");
  tombolTema.addEventListener("click", () => {
    const baru = temaGelap() ? "light" : "dark";
    if (baru === "dark") document.documentElement.dataset.theme = "dark";
    else delete document.documentElement.dataset.theme;
    simpanTema(baru);
    tombolTema.textContent = temaGelap() ? "Mode terang" : "Mode gelap";
    aturGayaGrafik();
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
  const umurJam = (Date.now() - new Date(meta.dibuat).getTime()) / 3.6e6;
  const telemetri = document.createElement("div");
  telemetri.className = "telemetri";
  telemetri.setAttribute("aria-label", "Status sistem");
  telemetri.innerHTML = `<div>
    <span class="${umurJam < 36 ? "hidup" : ""}">${umurJam < 36 ? "Sistem aktif" : `<b style="color:var(--serious)">Belum diperbarui ${Math.round(umurJam / 24)} hari</b>`}</span>
    <span>Data <b>${esc(tgl(meta.tanggal_data_terakhir))}</b></span>
    <span>Diperbarui <b>${esc(waktu(meta.dibuat))} WIB</b></span>
    <span class="opsional">Observasi <b>${angka(meta.jumlah?.observasi_dipakai)}</b></span>
    <span class="opsional">Wilayah <b>${esc(meta.wilayah_target?.nama || "")}</b></span>
    <span class="opsional">Pipeline <b>v${esc(meta.versi)}</b></span>
    ${meta.mode_demo ? "<span><b style=\"color:var(--demo-ink)\">Mode demo</b></span>" : ""}
  </div>`;
  kepala.after(telemetri);
  if (meta.mode_demo) {
    const b = document.createElement("div");
    b.className = "banner-demo";
    b.setAttribute("role", "status");
    b.innerHTML = `<div><strong>Mode demo.</strong> Angka di halaman ini masih data contoh untuk menguji sistem, bukan angka resmi. Begitu berkas harga pertama masuk ke <code>data/masuk/harga</code>, data asli langsung menggantikannya.</div>`;
    telemetri.after(b);
  }
  const tautanRun = meta.url_run ? ` · <a href="${esc(meta.url_run)}">log proses</a>` : "";
  const tautanRepo = meta.url_repo ? ` · <a href="${esc(meta.url_repo)}">repositori</a>` : "";
  kaki.innerHTML = `
    <p><strong style="color:var(--ink-2)">${NAMA_SISTEM}</strong> · BPS Kabupaten Bengkulu Tengah · Diperbarui ${esc(waktu(meta.dibuat))} WIB · data terakhir ${esc(tgl(meta.tanggal_data_terakhir))} · versi pipeline ${esc(meta.versi)}${meta.commit ? " · commit " + esc(meta.commit.slice(0, 7)) : ""}${tautanRun}${tautanRepo}</p>
    <p>Sinyal dan proyeksi di sini membantu analisis, tetapi tetap perlu dicek petugas sebelum dipakai untuk mengambil keputusan. Angka di dashboard ini bukan rilis resmi BPS.</p>
    <p>Sumber: BPS Kabupaten Bengkulu Tengah (pencatatan harga pasar), Pemda (bila tersedia), cuaca © Open-Meteo (CC BY 4.0), peta © kontributor OpenStreetMap.</p>
    ${tautanLayanan(meta.layanan)}`;
  // Grafik kanvas baru memakai huruf Plex setelah berkasnya termuat.
  try { await document.fonts?.ready; } catch { /* abaikan */ }
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

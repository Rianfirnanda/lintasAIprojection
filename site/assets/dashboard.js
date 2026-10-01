// Ikon garis dan fungsi bersama untuk beranda dashboard (SVG inline, tanpa berkas gambar).

const GARIS = {
  keranjang: '<path d="M3 9.5h18l-2 10H5l-2-10z"/><path d="M8 9.5l3-5.5M16 9.5l-3-5.5M9 13v3.5M12 13v3.5M15 13v3.5"/>',
  kubus: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
  pin: '<path d="M12 21s7-6.2 7-11a7 7 0 10-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.6"/>',
  jam: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5.2l3.2 2"/>',
  peringatan: '<path d="M12 3.5l9.5 16.5h-19L12 3.5z"/><path d="M12 10v4.5M12 17.4v.1"/>',
  roda: '<circle cx="12" cy="12" r="3.2"/><path d="M10.4 3h3.2l.5 2.5 1.6.7 2.1-1.4 2.3 2.3-1.4 2.1.7 1.6 2.5.5v3.2l-2.5.5-.7 1.6 1.4 2.1-2.3 2.3-2.1-1.4-1.6.7-.5 2.5h-3.2l-.5-2.5-1.6-.7-2.1 1.4-2.3-2.3 1.4-2.1-.7-1.6L3 13.6v-3.2l2.5-.5.7-1.6-1.4-2.1 2.3-2.3 2.1 1.4 1.6-.7L10.4 3z"/>',
  peta: '<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2z"/><path d="M9 4v14M15 6v14"/>',
  tren: '<path d="M3 17l6-6 4 4 8-9"/><path d="M15 6h6v6"/>',
  trenTurun: '<path d="M3 7l6 6 4-4 8 9"/><path d="M15 18h6v-6"/>',
  bendera: '<path d="M5 21V4"/><path d="M5 4h12l-2.5 4L17 12H5"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
  timbangan: '<path d="M12 4v16M7 20h10M5 7h14"/><path d="M5 7l-3 6a3 3 0 006 0L5 7zM19 7l-3 6a3 3 0 006 0l-3-6z"/>',
  simpul: '<circle cx="12" cy="5" r="2"/><circle cx="5" cy="18" r="2"/><circle cx="19" cy="18" r="2"/><path d="M11 6.7L6 16.3M13 6.7l5 9.6M7 18h10"/>',
  batang: '<path d="M5 20v-6M10 20V8M15 20v-9M20 20V5"/>',
  lonceng: '<path d="M6 17v-6a6 6 0 1112 0v6l2 2H4l2-2z"/><path d="M10 21h4"/>',
  denyut: '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
  kalender: '<path d="M4 6h16v14H4z"/><path d="M4 10.5h16M8 3v4M16 3v4"/>',
  dokumen: '<path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4M9 12h7M9 16h7"/>',
  gedung: '<path d="M4 21V5l8-2v18M12 8h8v13M2 21h20M7 8h2M7 12h2M7 16h2M15 12h2M15 16h2"/>',
  toko: '<path d="M3 9l1.5-5h15L21 9M3 9c0 1.7 1.3 3 3 3s3-1.3 3-3c0 1.7 1.3 3 3 3s3-1.3 3-3c0 1.7 1.3 3 3 3s3-1.3 3-3M5 12v9h14v-9M9 21v-5h6v5"/>',
  pemda: '<path d="M3 9l9-5 9 5M5 9v9M9.5 9v9M14.5 9v9M19 9v9M3 21h18M3 18h18"/>',
  ai: '<circle cx="12" cy="12" r="9"/><text x="12" y="15.6" font-size="9" font-weight="700" text-anchor="middle" fill="currentColor" stroke="none" font-family="sans-serif">AI</text>',
  database: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
  menara: '<path d="M12 9v12M8 21l4-12 4 12M9.5 16.5h5M6 6a8 8 0 000 6M18 6a8 8 0 010 6M9 8a4 4 0 000 2M15 8a4 4 0 010 2"/>',
  ponsel: '<rect x="7" y="2.5" width="10" height="19" rx="2"/><path d="M11 18.5h2"/>',
  dokumenCentang: '<path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4M9 13.5l2 2 4-4.5"/>',
  sinkron: '<path d="M20 11a8 8 0 00-14-4M4 5v4h4M4 13a8 8 0 0014 4M20 19v-4h-4"/>',
  orang: '<circle cx="12" cy="8" r="3.5"/><path d="M5 21c0-4 3-6.5 7-6.5s7 2.5 7 6.5"/>',
  otak: '<path d="M12 4H9.5A3 3 0 006.6 7 3 3 0 004.5 12a3 3 0 002.1 4.8A3 3 0 009.5 20H12zM12 4h2.5A3 3 0 0117.4 7a3 3 0 012.1 5 3 3 0 01-2.1 4.8A3 3 0 0114.5 20H12M12 4v16M9 9.5h3M12 14.5h3"/>',
  lampu: '<path d="M9 18h6M10 21h4M12 3a6 6 0 00-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0012 3z"/>',
  tim: '<circle cx="8" cy="8" r="2.8"/><circle cx="16.5" cy="9" r="2.3"/><path d="M2.5 19c0-3.3 2.4-5.5 5.5-5.5s5.5 2.2 5.5 5.5M14 14.3c.9-.5 1.7-.7 2.5-.7 2.6 0 4.5 1.9 4.5 4.6"/>',
  papan: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1M9 13l2.2 2.2L15.5 11"/>',
  centang: '<circle cx="12" cy="12" r="9"/><path d="M8 12.3l2.6 2.6L16 9.5"/>',
  cari: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/>',
  awan: '<path d="M7 18a4 4 0 010-8 5.5 5.5 0 0110.5 1.5A3.3 3.3 0 0117 18M12 21v-7M9 16.5l3-3 3 3"/>',
  layar: '<rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M8 20h8M12 16v4M7 13v-3M11 13V8M15 13v-2"/>',
  streaming: '<circle cx="12" cy="12" r="1.8"/><path d="M8 8a5.7 5.7 0 000 8M16 8a5.7 5.7 0 010 8M5.2 5.2a9.6 9.6 0 000 13.6M18.8 5.2a9.6 9.6 0 010 13.6"/>',
  tautan: '<path d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3A4 4 0 0011 18.7l1-1"/>',
  gudang: '<rect x="4" y="4" width="16" height="6" rx="1.5"/><rect x="4" y="14" width="16" height="6" rx="1.5"/><path d="M7.5 7h.01M7.5 17h.01M11 7h5M11 17h5"/>',
  perisai: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
  gembokPerisai: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z"/><rect x="9" y="11" width="6" height="5" rx="1"/><path d="M10.2 11V9.5a1.8 1.8 0 013.6 0V11"/>',
  pencilan: '<circle cx="6" cy="14" r="1.6"/><circle cx="11" cy="11" r="1.6"/><circle cx="9" cy="17" r="1.6"/><circle cx="17" cy="6" r="1.6"/><circle cx="18" cy="15" r="1.6"/>',
  kurang: '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>',
  tukar: '<path d="M4 8h14M14 4l4 4-4 4M20 16H6M10 12l-4 4 4 4"/>',
  keranjangBelanja: '<path d="M3 4h3l2.5 11h9.5l2-8H7M9.5 20h.01M17 20h.01"/>',
  gunung: '<path d="M2 20l6-9 4 5 3-4 7 8H2z"/>',
  silang: '<path d="M6 6l12 12M18 6L6 18"/>',
  kanan: '<path d="M9.5 6l6 6-6 6"/>',
};

export function ikon(nama, ukuran = 20) {
  return `<svg class="ikon" width="${ukuran}" height="${ukuran}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${GARIS[nama] || ""}</svg>`;
}

// Ilustrasi komoditas ada di gambar-komoditas.js (per varian, mis. cabai rawit hijau berwarna hijau).
export { gambarKomoditas } from "./gambar-komoditas.js";

const BULAN_PANJANG = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
export function bulanTahun(iso) {
  if (!iso) return "–";
  const [y, m] = iso.split("-").map(Number);
  return `${BULAN_PANJANG[m - 1]} ${y}`;
}

/* ---------- fungsi bersama beranda dan halaman Alur & Arsitektur */
import { angka } from "./app.js";

function median(a) {
  const s = a.filter((x) => x !== null && x !== undefined && !Number.isNaN(x)).sort((x, y) => x - y);
  if (!s.length) return null;
  const t = Math.floor(s.length / 2);
  return s.length % 2 ? s[t] : (s[t - 1] + s[t]) / 2;
}

/** Enam ukuran mutu model (sMAPE, bias, F1, recall, false alarm, drift) lengkap dengan status dan catatan target. */
export function hitungMutu(m, daftarSinyal) {
  const r = m.ringkasan, e = m.evaluasi_anomali, t = m.target;
  const n = r.varian_dinilai;
  const ada = (x) => x !== null && x !== undefined;
  const bias = median(m.per_varian.map((v) => { const x = v.metrik?.[v.model_terpilih]; return x ? Math.abs(x.bias_persen) : null; }));
  const drift = daftarSinyal.filter((x) => x.jenis === "drift" && x.aktif).length;
  const kosong = ["Belum ada data", "netral"];
  const ok = (lolos, tulisan = "Baik") => (lolos ? [tulisan, "baik"] : ["Perhatian", "perhatian"]);
  return [
    { ikon: "target", nama: "sMAPE", arti: "Rata-rata meleset", nilai: ada(r.smape_median) ? `${angka(r.smape_median, 1)}%` : "–", status: n ? ok(r.lolos_smape === n) : kosong,
      catatan: `Rata-rata meleset prakiraan. ${r.lolos_smape} dari ${n} varian lebih tepat minimal ${t.perbaikan_smape_persen}% dibanding cara sederhana` },
    { ikon: "timbangan", nama: "Bias", arti: "Condong tinggi atau rendah", nilai: ada(bias) ? `${angka(bias, 1)}%` : "–", status: n ? ok(r.lolos_bias === n) : kosong,
      catatan: `Condong terlalu tinggi atau rendah. Target paling besar ${t.bias_absolut_maks_persen}%` },
    { ikon: "simpul", nama: "F1-score", arti: "Nilai gabungan", nilai: ada(e?.f1) ? angka(e.f1, 2) : "–", status: ada(e?.f1) ? ok(e.f1 >= t.f1_min) : kosong,
      catatan: `Nilai gabungan ketepatan peringatan. Target minimal ${angka(t.f1_min, 2)}${e?.sumber_label ? ` (${e.sumber_label})` : ""}` },
    { ikon: "batang", nama: "Recall", arti: "Lonjakan tertangkap", nilai: ada(e?.recall) ? angka(e.recall, 2) : "–", status: ada(e?.recall) ? ok(e.recall >= t.recall_min) : kosong,
      catatan: `Lonjakan harga yang berhasil tertangkap. Target minimal ${angka(t.recall_min, 2)}` },
    { ikon: "lonceng", nama: "False alarm", arti: "Peringatan yang salah", nilai: ada(e?.false_positive_rate) ? `${angka(e.false_positive_rate * 100, 1)}%` : "–",
      status: ada(e?.false_positive_rate) ? ok(e.false_positive_rate <= t.fpr_maks, "Terkendali") : kosong, catatan: `Peringatan yang ternyata salah. Target paling besar ${t.fpr_maks * 100}%` },
    { ikon: "denyut", nama: "Drift data", arti: "Pola berubah", nilai: drift ? `${drift} varian` : "Normal", status: drift ? ["Waspada", "perhatian"] : ["Stabil", "baik"],
      catatan: "Pola harga berubah dari biasanya, atau prakiraan mulai meleset" },
  ];
}

/** Sinyal prioritas (aktif dan keparahan tinggi) beserta rincian status tindak lanjutnya. */
export function ringkasSinyalPrioritas(daftar) {
  const p = daftar.filter((s) => s.aktif && s.keparahan === "tinggi");
  const hitung = (st) => p.filter((s) => s.status === st).length;
  return { total: p.length, diverifikasi: hitung("terverifikasi"), ditindaklanjuti: hitung("ditindaklanjuti"), selesai: hitung("selesai") };
}

export function nilaiUptime(kinerja) {
  const u = kinerja?.indikator?.find((i) => i.kode === "L1")?.capaian;
  return u === null || u === undefined ? null : u;
}

/** Langkah berikutnya yang disarankan untuk tiap jenis sinyal. */
export const LANGKAH_SINYAL = {
  anomali_harga: "Cek pasokan dan distribusi di pasar",
  proyeksi_naik: "Pantau harga 7 hari ke depan",
  risiko_hari_raya: "Siapkan pemantauan intensif",
  data_terlambat: "Hubungi petugas pencatat",
  drift: "Cek ulang cara prakiraan",
};

/* ---------- selisih harga dalam rupiah (logika murni ada di selisih.js supaya bisa diuji di Node) */
export { tglPendek, selisihHarga, teksSelisih, arahSelisih, TANDA_ARAH, htmlSelisih } from "./selisih.js";

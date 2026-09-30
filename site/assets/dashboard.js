// Ikon garis dan ilustrasi komoditas untuk beranda dashboard (SVG inline, tanpa berkas gambar).

const GARIS = {
  keranjang: '<path d="M3 9.5h18l-2 10H5l-2-10z"/><path d="M8 9.5l3-5.5M16 9.5l-3-5.5M9 13v3.5M12 13v3.5M15 13v3.5"/>',
  kubus: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
  pin: '<path d="M12 21s7-6.2 7-11a7 7 0 10-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.6"/>',
  jam: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5.2l3.2 2"/>',
  peringatan: '<path d="M12 3.5l9.5 16.5h-19L12 3.5z"/><path d="M12 10v4.5M12 17.4v.1"/>',
  roda: '<circle cx="12" cy="12" r="3.2"/><path d="M10.4 3h3.2l.5 2.5 1.6.7 2.1-1.4 2.3 2.3-1.4 2.1.7 1.6 2.5.5v3.2l-2.5.5-.7 1.6 1.4 2.1-2.3 2.3-2.1-1.4-1.6.7-.5 2.5h-3.2l-.5-2.5-1.6-.7-2.1 1.4-2.3-2.3 1.4-2.1-.7-1.6L3 13.6v-3.2l2.5-.5.7-1.6-1.4-2.1 2.3-2.3 2.1 1.4 1.6-.7L10.4 3z"/>',
  peta: '<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2-6-2z"/><path d="M9 4v14M15 6v14"/>',
  tren: '<path d="M3 17l6-6 4 4 8-9"/><path d="M15 6h6v6"/>',
  bendera: '<path d="M5 21V4"/><path d="M5 4h12l-2.5 4L17 12H5"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
  timbangan: '<path d="M12 4v16M7 20h10M5 7h14"/><path d="M5 7l-3 6a3 3 0 006 0L5 7zM19 7l-3 6a3 3 0 006 0l-3-6z"/>',
  simpul: '<circle cx="12" cy="5" r="2"/><circle cx="5" cy="18" r="2"/><circle cx="19" cy="18" r="2"/><path d="M11 6.7L6 16.3M13 6.7l5 9.6M7 18h10"/>',
  batang: '<path d="M5 20v-6M10 20V8M15 20v-9M20 20V5"/>',
  lonceng: '<path d="M6 17v-6a6 6 0 1112 0v6l2 2H4l2-2z"/><path d="M10 21h4"/>',
  denyut: '<path d="M3 12h4l2-6 4 12 2-6h6"/>',
  kalender: '<path d="M4 6h16v14H4z"/><path d="M4 10.5h16M8 3v4M16 3v4"/>',
  dokumen: '<path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4M9 12h7M9 16h7"/>',
  gunung: '<path d="M2 20l6-9 4 5 3-4 7 8H2z"/>',
};

export function ikon(nama, ukuran = 20) {
  return `<svg class="ikon" width="${ukuran}" height="${ukuran}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${GARIS[nama] || ""}</svg>`;
}

// Ilustrasi datar sederhana per komoditas (kode_komoditas dari master.json).
const TUJUAN = {
  CRW: `<path d="M8 38C22 37 38 30 54 14" stroke="#c9281c" stroke-width="7" stroke-linecap="round" fill="none"/>
        <path d="M10 36C24 35 38 29 52 15" stroke="#f0644d" stroke-width="2" stroke-linecap="round" fill="none"/>
        <path d="M6 28C18 28 30 22 42 10" stroke="#dc3a2b" stroke-width="6" stroke-linecap="round" fill="none"/>
        <path d="M54 14l4-5M42 10l3-5" stroke="#3f8f3a" stroke-width="3" stroke-linecap="round"/>`,
  CMR: `<path d="M6 36C22 36 42 28 56 12" stroke="#b81f17" stroke-width="8" stroke-linecap="round" fill="none"/>
        <path d="M9 34C24 34 42 27 54 13" stroke="#ea5443" stroke-width="2.4" stroke-linecap="round" fill="none"/>
        <path d="M56 12l4-6" stroke="#3f8f3a" stroke-width="3.4" stroke-linecap="round"/>`,
  BWM: `<path d="M32 5c2 6 13 10 13 22a13 13 0 01-26 0c0-12 11-16 13-22z" fill="#8c3d8e"/>
        <path d="M32 5v9M26 18c-3 6-3 14 0 20M38 18c3 6 3 14 0 20" stroke="#c98bc6" stroke-width="1.6" fill="none" stroke-linecap="round"/>
        <path d="M32 40v4" stroke="#cbb9a0" stroke-width="2" stroke-linecap="round"/>`,
  BWP: `<path d="M32 6c3 5 14 8 14 22 0 9-6 14-14 14S18 37 18 28C18 14 29 11 32 6z" fill="#f4ecdb" stroke="#d3c19b" stroke-width="1.4"/>
        <path d="M32 10v30M25 15c-3 8-3 18 0 24M39 15c3 8 3 18 0 24" stroke="#d3c19b" stroke-width="1.4" fill="none" stroke-linecap="round"/>`,
  BRS: `<path d="M6 27h52a26 19 0 01-52 0z" fill="#c69a5d"/>
        <path d="M10 27c3-15 41-15 44 0z" fill="#fbfbf8" stroke="#e3e3dc" stroke-width="1.2"/>
        <path d="M22 20l3 1M32 16l3 1M40 21l3 1M28 23l3 1" stroke="#d5d5cb" stroke-width="1.6" stroke-linecap="round"/>`,
  TLR: `<ellipse cx="23" cy="29" rx="12" ry="15" fill="#f6e3bb"/><ellipse cx="42" cy="31" rx="11" ry="14" fill="#efd39b"/>
        <path d="M17 22c1-4 4-7 8-7" stroke="#fff6df" stroke-width="2.4" stroke-linecap="round" fill="none"/>`,
  DAY: `<path d="M14 35c-4-11 3-23 15-25 10-1 17 8 12 17-4 8-14 6-19 13-3 3-6 2-8-5z" fill="#d98a3d"/>
        <path d="M20 40l-7 7" stroke="#f3efe6" stroke-width="4.5" stroke-linecap="round"/><circle cx="11" cy="46" r="2.6" fill="#f3efe6"/>
        <path d="M24 18c4-3 9-2 12 1" stroke="#efb572" stroke-width="2.4" stroke-linecap="round" fill="none"/>`,
  DSP: `<path d="M7 25c0-11 15-17 30-15 13 2 21 9 19 19-2 11-17 13-31 11C13 38 7 33 7 25z" fill="#c23a3a"/>
        <path d="M17 21c7 2 11 0 16 4M25 32c7-2 13 0 20-5M38 15c3 3 6 3 10 2" stroke="#f0c2c2" stroke-width="2.4" stroke-linecap="round" fill="none"/>`,
  MGR: `<rect x="24" y="15" width="17" height="28" rx="4.5" fill="#f2c230"/><rect x="28" y="7" width="9" height="9" rx="2" fill="#d9a21a"/>
        <rect x="27" y="22" width="11" height="12" rx="2" fill="#fffaf0"/><path d="M29 26h7M29 30h5" stroke="#d9a21a" stroke-width="1.6" stroke-linecap="round"/>`,
  GLP: `<rect x="10" y="22" width="20" height="20" rx="3" fill="#faf9f5" stroke="#d3cfc2" stroke-width="1.4"/>
        <rect x="32" y="24" width="20" height="18" rx="3" fill="#f3f1ea" stroke="#d3cfc2" stroke-width="1.4"/>
        <rect x="20" y="8" width="20" height="20" rx="3" fill="#ffffff" stroke="#d3cfc2" stroke-width="1.4"/>`,
};

export function gambarKomoditas(kodeKomoditas) {
  const isi = TUJUAN[kodeKomoditas] || TUJUAN.BRS;
  return `<svg class="gambar-komoditas" viewBox="0 0 64 48" aria-hidden="true">${isi}</svg>`;
}

const BULAN_PANJANG = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
export function bulanTahun(iso) {
  if (!iso) return "–";
  const [y, m] = iso.split("-").map(Number);
  return `${BULAN_PANJANG[m - 1]} ${y}`;
}

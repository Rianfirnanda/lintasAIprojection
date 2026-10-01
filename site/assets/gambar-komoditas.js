// Ilustrasi datar tiap komoditas dan varian (SVG inline, tanpa berkas gambar dan tanpa foto dari internet).
// Kunci boleh kode varian (mis. CRW01) atau kode komoditas (mis. CRW). Varian tanpa gambar khusus memakai gambar komoditasnya.
// Semua gambar memakai kanvas 64 x 48 dan bayangan dasar yang sama supaya tampak satu keluarga.

const bayang = (cx = 32, rx = 22) => `<ellipse cx="${cx}" cy="44.6" rx="${rx}" ry="2.2" fill="#0b1a2e" opacity=".13"/>`;

/* ---------- cabai: satu bentuk dasar per jenis, dipakai berulang dengan posisi dan sudut berbeda */
const BENTUK_CABAI = {
  rawit: {
    badan: "M0 -3.3C5.4 -3.7 11.4 -2.6 17.6 1.2C18.4 1.7 18.1 2.5 17.2 2.4C11.2 2 5.4 3.4 0 3.3Z",
    gelap: "M0 1C5.4 1.4 11.4 .8 17.6 1.6C18.1 2.2 17.7 2.5 17.2 2.4C11.2 2 5.4 3.4 0 3.3Z",
    kilau: "M2.4 -1.5C6 -1.9 10 -1.5 13 -.5",
    kelopak: "M-1.3 -3.6C.9 -3.9 2.8 -2.7 3.5 -1.9C2.6 -.5 2.6 .7 3.5 1.9C2.8 2.9 .9 3.9 -1.3 3.6C-2.2 1.4 -2.2 -1.4 -1.3 -3.6Z",
    tangkai: "M-1 0C-3.5 -.3 -5.5 -1.6 -6.8 -3.6", tebal: 1.7,
  },
  besar: {
    badan: "M0 -4.6C10 -5.6 22 -4.8 32 -.6C36 1.2 39 3.6 40.5 6.2C41 7.4 40 8 39 7.2C35 4.4 29 3.4 22 3.6C14 3.9 7 5.2 0 4.6Z",
    gelap: "M0 1.6C8 2 16 1.2 24 1.2C31 1.4 36 3.4 40.5 6.4C41 7.4 40 8 39 7.2C35 4.4 29 3.4 22 3.6C14 3.9 7 5.2 0 4.6Z",
    kilau: "M3.5 -2.8C10 -3.6 18 -3.2 26 -1.2",
    kelopak: "M-2 -5C1 -5.6 4 -4.6 5.2 -3.2C4 -1.2 4 1.2 5.2 3.2C4 4.6 1 5.6 -2 5C-3 2 -3 -2 -2 -5Z",
    tangkai: "M-1.5 0C-5 -.5 -8 -2.6 -9.6 -5.6", tebal: 2.6,
  },
  keriting: {
    badan: "M0 -2.3C6 -3.2 10 -.6 16 -1.2C22 -1.8 26 -4 32 -2C37 -.4 40 3 43 6.4C43.6 7.2 42.8 7.8 42 7.1C38.8 4.4 35.8 2.2 31.6 1.8C26 1.4 22 2.6 16 3C10 3.4 6 1.8 0 2.3Z",
    gelap: "M0 .6C6 .4 10 1.6 16 1.2C22 .8 27 -.4 32 .2C37 1 40 3.6 43 6.6C43.6 7.2 42.8 7.8 42 7.1C38.8 4.4 35.8 2.2 31.6 1.8C26 1.4 22 2.6 16 3C10 3.4 6 1.8 0 2.3Z",
    kilau: "M3 -1.3C7 -1.9 10 -.3 14 -.5",
    kerut: "M8.5 -1.2l1 1.8M19.5 -2l.9 1.9M27.5 -2.4l1.2 1.8M35.5 .4l.9 1.7",
    kelopak: "M-1.4 -3C.8 -3.4 2.8 -2.4 3.6 -1.6C2.8 -.4 2.8 .6 3.6 1.6C2.8 2.6 .8 3.4 -1.4 3C-2.2 1.2 -2.2 -1.2 -1.4 -3Z",
    tangkai: "M-1 0C-4 -.4 -6.5 -2 -8 -4.4", tebal: 2,
  },
};
const WARNA_CABAI = {
  merah: { badan: "#e2271c", gelap: "#b5170f", kilau: "#ff9d88", kelopak: "#3f8a2e", tangkai: "#5c9a3a" },
  merahTua: { badan: "#d1231b", gelap: "#a0140e", kilau: "#ff8f7a", kelopak: "#3f8a2e", tangkai: "#5c9a3a" },
  hijau: { badan: "#58ad3f", gelap: "#2f7d24", kilau: "#c2eca6", kelopak: "#25601a", tangkai: "#7da64a" },
};
function cabai(jenis, warna, x, y, sudut = 0, skala = 1) {
  const b = BENTUK_CABAI[jenis], w = WARNA_CABAI[warna];
  return `<g transform="translate(${x} ${y}) rotate(${sudut}) scale(${skala})">
    <path d="${b.badan}" fill="${w.badan}"/><path d="${b.gelap}" fill="${w.gelap}"/>
    ${b.kerut ? `<path d="${b.kerut}" stroke="${w.gelap}" stroke-width=".9" stroke-linecap="round" fill="none"/>` : ""}
    <path d="${b.kilau}" stroke="${w.kilau}" stroke-width="1.1" stroke-linecap="round" fill="none" opacity=".85"/>
    <path d="${b.kelopak}" fill="${w.kelopak}"/>
    <path d="${b.tangkai}" stroke="${w.tangkai}" stroke-width="${b.tebal}" stroke-linecap="round" fill="none"/></g>`;
}

/* ---------- bentuk lain yang dipakai berulang */
const TELUR = "M0 -11C6 -11 9.5 -3 9.5 3C9.5 9 5.5 12 0 12C-5.5 12 -9.5 9 -9.5 3C-9.5 -3 -6 -11 0 -11Z";
const telur = (x, y, s = 1) => `<g transform="translate(${x} ${y}) scale(${s})">
  <path d="${TELUR}" fill="#d99c63"/>
  <path d="M9.5 3C9.5 9 5.5 12 0 12C-4 12 -7.4 10.4 -8.8 7.4C-5 9.6 2 9.4 6 5C8.4 2.2 8.8 -2 8 -5.6C9 -3 9.5 0 9.5 3Z" fill="#bf7f45"/>
  <ellipse cx="-3.6" cy="-3.8" rx="1.9" ry="3.4" transform="rotate(18 -3.6 -3.8)" fill="#f6d4aa"/></g>`;

const UMBI_MERAH = "M0 -11C1.5 -7.5 7.5 -5 8.5 1.5C9.2 7 5 10.5 0 10.5C-5 10.5 -9.2 7 -8.5 1.5C-7.5 -5 -1.5 -7.5 0 -11Z";
const bawangMerah = (x, y, s = 1, gelap = false) => `<g transform="translate(${x} ${y}) scale(${s})">
  <path d="${UMBI_MERAH}" fill="${gelap ? "#9a3352" : "#b4425f"}"/>
  <path d="M8.5 1.5C9.2 7 5 10.5 0 10.5C-3 10.5 -6 9.2 -7.6 6.8C-3 8.6 3.6 7.6 6.4 3C7.6 1 7.8 -1.4 7 -3.4C7.9 -1.8 8.3 -.3 8.5 1.5Z" fill="#7f2443"/>
  <path d="M-4 -3.4C-5.6 .6 -5.2 5.6 -3 9M0 -7.2C-.4 -2 -.2 4 0 10M4 -3.4C5.6 .6 5.2 5.6 3 9" stroke="#e294a8" stroke-width=".8" fill="none" opacity=".75"/>
  <path d="M0 -11C.6 -13 -.6 -14.6 1 -16.2" stroke="#c49a6a" stroke-width="1.3" stroke-linecap="round" fill="none"/>
  <path d="M-2.2 10.4l-1 1.7M0 10.6v1.9M2.2 10.4l1 1.7" stroke="#dcc39c" stroke-width=".8" stroke-linecap="round"/></g>`;

const tumpukanButir = (titik, warna, rx = 1.35, ry = .62) =>
  titik.map(([x, y, r]) => `<ellipse cx="${x}" cy="${y}" rx="${rx}" ry="${ry}" transform="rotate(${r} ${x} ${y})" fill="${warna}"/>`).join("");
const kristal = (titik, warna) => titik.map(([x, y, r = 0]) => `<rect x="${x - .8}" y="${y - .8}" width="1.6" height="1.6" transform="rotate(${45 + r} ${x} ${y})" fill="${warna}"/>`).join("");
const kilauBintang = (x, y, u = 2.2) => { const t = u * .22;
  return `<path d="M${x} ${y - u}L${x + t} ${y - t}L${x + u} ${y}L${x + t} ${y + t}L${x} ${y + u}L${x - t} ${y + t}L${x - u} ${y}L${x - t} ${y - t}Z" fill="#ffffff"/>`; };

const botolMinyak = (label) => `${bayang(32, 15)}
  <path d="M28 9.5h8v3.2c0 2.1 6.3 3.1 6.3 6.6H21.7c0-3.5 6.3-4.5 6.3-6.6z" fill="#f5c23a"/>
  <rect x="20" y="18" width="24" height="25.5" rx="4.5" fill="#f5c23a"/>
  <path d="M37.5 18h2a4.5 4.5 0 0 1 4.5 4.5v16.5a4.5 4.5 0 0 1-4.5 4.5h-2c2-4 2.6-20 0-25.5z" fill="#dd9e17"/>
  <rect x="26.6" y="4.2" width="10.8" height="5.8" rx="1.4" fill="#e04f2c"/>
  <path d="M28.6 5.4v3.4M31 5.4v3.4M33.4 5.4v3.4M35.8 5.4v3.4" stroke="#b83a1e" stroke-width=".7"/>
  <rect x="20" y="25" width="24" height="12" fill="${label}"/>
  <path d="M32 27.3c2.1 2.6 3.1 4.2 3.1 5.7a3.1 3.1 0 0 1-6.2 0c0-1.5 1-3.1 3.1-5.7z" fill="#fde68a"/>
  <path d="M23.2 20.5v3M23.2 38.6v2.6" stroke="#ffffff" stroke-width="1.5" stroke-linecap="round" opacity=".7"/>`;

const mangkuk = (warna, bibir, gelap) => `<path d="M10 29.5h44c-1 8-9 12.8-22 12.8S11 37.5 10 29.5z" fill="${warna}"/>
  <path d="M54 29.5c-1 8-9 12.8-22 12.8-4 0-7.5-.4-10.4-1.3 14 .6 25.6-3.6 28.4-11.5z" fill="${gelap}"/>
  <ellipse cx="32" cy="29.6" rx="22" ry="2.4" fill="${bibir}"/>`;

/* ---------- gambar per kode */
const GAMBAR = {
  // Beras: karung terbuka berisi beras, beberapa butir tercecer.
  BRS: `${bayang(32, 21)}
    <path d="M17 16c-2.2 8-3 16.5-1.6 24.4.4 1.8 2 2.6 4.6 2.6h24c2.6 0 4.2-.8 4.6-2.6 1.4-7.9.6-16.4-1.6-24.4z" fill="#efe7d4" stroke="#cfc2a3" stroke-width=".8"/>
    <path d="M41.5 16H47c2.2 8 3 16.5 1.6 24.4-.4 1.8-2 2.6-4.6 2.6h-3c3-9 3.6-18 .5-27z" fill="#ddd1b5"/>
    <path d="M16.6 24.5h30.8M15.9 33h32.2" stroke="#d8ccb1" stroke-width=".8"/>
    <rect x="21" y="27" width="22" height="9.5" rx="1.6" fill="#2f7fbf"/>
    <path d="M25 30.2h14M27.5 33.4h9" stroke="#ffffff" stroke-width="1.2" stroke-linecap="round" opacity=".9"/>
    <path d="M17.6 16.4c3-6.6 10.4-9.4 14.4-9.4s11.4 2.8 14.4 9.4c-7.4-1.8-21.4-1.8-28.8 0z" fill="#fbfaf3" stroke="#d9d3bf" stroke-width=".7"/>
    ${tumpukanButir([[25, 12.4, -20], [29.5, 10.2, 15], [34.5, 10.4, -10], [38.6, 12.6, 25], [31.6, 13.6, 0], [27, 15.1, 10], [36.5, 15, -15], [42, 15.2, 5], [21.6, 15.4, -30]], "#e3dfcf")}
    <path d="M15.4 15.4c4.6-3.2 28.6-3.2 33.2 0l-.8 3.6c-5-2.2-26.6-2.2-31.6 0z" fill="#e3d8be" stroke="#cfc2a3" stroke-width=".7"/>
    ${tumpukanButir([[51.5, 42.6, 20], [54.6, 41.6, -25], [53, 43.8, 70], [11.4, 42.8, -15]], "#d8d1bb")}`,

  // Daging ayam ras segar: ayam utuh mentah (kulit pucat) dengan dua paha terangkat.
  DAY: `${bayang(32, 21)}
    <path d="M37.6 20.4C39 14.6 42 10.6 45.4 8.8" stroke="#e3a97f" stroke-width="7.4" stroke-linecap="round" fill="none"/>
    <path d="M45 9.2l2.8-2.2" stroke="#fbf3e6" stroke-width="2.6" stroke-linecap="round"/>
    <circle cx="48.4" cy="5.6" r="1.9" fill="#fbf3e6"/><circle cx="49.6" cy="7.8" r="1.9" fill="#fbf3e6"/>
    <path d="M12.2 30c-1-8 5.8-14 15.8-14.5 12-.5 22 3.5 24 11.5 1.5 7-6 12.5-19 12.8-12 .2-19.8-2.8-20.8-9.8z" fill="#f5d0ae"/>
    <path d="M12.6 32c2.4 5 9.4 8 20.4 7.8 13-.3 20-5.3 19.2-11.3-3.2 5.5-11.2 8-20.2 8.1-9 .1-16-1.6-19.4-4.6z" fill="#e2a87f"/>
    <path d="M41.6 24.4C44 18.4 48.4 14.6 52.6 13.2" stroke="#eab48a" stroke-width="8.4" stroke-linecap="round" fill="none"/>
    <path d="M42.6 23C45 18.6 48 16 51 14.8" stroke="#f6d3b2" stroke-width="2" stroke-linecap="round" fill="none" opacity=".8"/>
    <path d="M52 13.4l3.4-1.6" stroke="#fbf3e6" stroke-width="2.8" stroke-linecap="round"/>
    <circle cx="56.6" cy="10" r="2" fill="#fbf3e6"/><circle cx="57.2" cy="12.6" r="2" fill="#fbf3e6"/>
    <path d="M14.4 23.6c-3.8-2-6.6-.2-6.3 2.8.3 3 3.8 4.4 6.6 3.6z" fill="#eab48a"/>
    <path d="M19.6 21.4c5-2.6 12-3.2 17.4-2.2" stroke="#fde9d6" stroke-width="2" stroke-linecap="round" fill="none"/>
    <g fill="#e6b38c"><circle cx="24" cy="27" r=".7"/><circle cx="29" cy="25.5" r=".7"/><circle cx="34" cy="28" r=".7"/><circle cx="27" cy="31" r=".7"/><circle cx="21" cy="31.5" r=".7"/></g>`,

  // Telur ayam ras: tiga butir telur cokelat.
  TLR: `${bayang(32, 20)}${telur(22, 24.6, .95)}${telur(42, 24.2, .95)}${telur(32, 30.4, 1.05)}`,

  // Daging sapi: potongan daging merah berlemak di atas talenan (supaya tidak tertukar dengan buah).
  DSP: `${bayang(32, 25)}
    <rect x="4.5" y="34.4" width="55" height="7.2" rx="3.6" fill="#b17646"/>
    <rect x="4.5" y="33.2" width="55" height="5" rx="2.5" fill="#d7a36b"/>
    <path d="M9 23.8V27c0 4.6 5 7.2 13 7.6 8 .4 22 .4 28-1 4-1 6-3.6 6-7.2v-2.6z" fill="#8f1f29"/>
    <path d="M44 34.2c3.4-.3 5.6-.8 6.6-1.2 3.8-1.2 5.4-3.6 5.4-6.8v-2.4c-1.2 3.2-4.6 5.4-12 6.4z" fill="#e7cdb3"/>
    <path d="M9 24c-1-7 5-11.6 15-12.1 10-.5 21 0 27 2.5 5 2 6.6 5.6 5 9.6-1.5 4.5-9 6.5-21 6.6-13 .1-25-1.1-26-6.6z" fill="#cf3b41"/>
    <path d="M44 12.6c6 .7 11 3.2 12.6 7.2.8 2.1.4 4-.6 5.7-1-2.4-2.5-4.8-5-6.6-2.2-1.6-4.6-2.3-7.6-2.8z" fill="#f6e6d4"/>
    <path d="M15 20.2c4-2 7 1 11-1M23.5 25.4c4-1.6 7 1 11-.8M32.6 16.6c3-1 6 1 9 0M39.6 23c3-1.4 6 .6 9-.8M17.4 26.6c2-.8 3.5 0 5-.4" stroke="#f8d9d2" stroke-width="1.1" stroke-linecap="round" fill="none" opacity=".9"/>`,

  // Bawang merah: tiga umbi kecil kemerahan.
  BWM: `${bayang(32, 20)}${bawangMerah(21.5, 28.4, .95, true)}${bawangMerah(42.5, 28, .95, true)}${bawangMerah(32, 31, 1.1)}`,

  // Bawang putih: satu bonggol bersiung dan satu siung lepas.
  BWP: `${bayang(32, 19)}
    <g transform="translate(28 28.6) scale(1.12)">
      <path d="M0 -14C1.5 -10.5 4 -9 8.5 -6.5C14.5 -3 15 7 9 10.5C5 12.6 -5 12.6 -9 10.5C-15 7 -14.5 -3 -8.5 -6.5C-4 -9 -1.5 -10.5 0 -14Z" fill="#f6efe1" stroke="#d6c4a0" stroke-width=".7"/>
      <path d="M9 10.5C5 12.6 -1 12.8 -5 12C1 11 8 8 10 2C11 -1 10.6 -4 9.4 -6C14.6 -2.4 14.8 7 9 10.5Z" fill="#e3d4ba"/>
      <path d="M0 -9.5C-4 -5 -5 5 -2.5 12M0 -9.5C4 -5 5 5 2.5 12M-3 -8C-10 -4 -11.5 5 -7 10.8M3 -8C10 -4 11.5 5 7 10.8" stroke="#cdb894" stroke-width=".9" fill="none"/>
      <path d="M-5.6 -3C-6.6 1 -6.4 5 -5 8.6M5.4 -2C6.2 1.6 6 5 4.8 8" stroke="#c8a2c4" stroke-width="1" stroke-linecap="round" fill="none" opacity=".7"/>
      <path d="M0 -14C.2 -16 1 -17.5 2.4 -18.5" stroke="#d6c29c" stroke-width="1.6" stroke-linecap="round" fill="none"/>
      <path d="M-4 12l-1.2 1.6M-1.5 12.4l-.4 1.8M1.5 12.4l.4 1.8M4 12l1.2 1.6" stroke="#cbb48a" stroke-width=".8" stroke-linecap="round"/></g>
    <g transform="translate(49 33.6) rotate(18)">
      <path d="M0 -6.4C4.2 -5.4 6.4 -1.2 5.8 3C5.2 6.2 2 7.8 -1.2 7.2C1 4.2 1.6 -1 0 -6.4Z" fill="#f2e9d7" stroke="#d2bf9b" stroke-width=".8"/>
      <path d="M0 -6.4C.6 -7.6 1.4 -8.4 2.4 -8.8" stroke="#d6c29c" stroke-width="1" stroke-linecap="round"/></g>`,

  // Cabai merah besar: dua cabai panjang dan gemuk.
  CMR01: `${bayang(33, 22)}${cabai("besar", "merahTua", 14, 15, 6, 1)}${cabai("besar", "merah", 12, 26, 10, 1.05)}`,
  // Cabai merah keriting: tiga cabai panjang, ramping, dan berkerut.
  CMR02: `${bayang(33, 22)}${cabai("keriting", "merahTua", 13, 13.5, 8, .98)}${cabai("keriting", "merah", 11, 22, 6, 1)}${cabai("keriting", "merah", 14, 30.5, 2, .98)}`,
  // Cabai rawit hijau dan merah: tiga cabai kecil runcing.
  CRW01: `${bayang(32, 20)}${cabai("rawit", "hijau", 17, 18, -10, 1.25)}${cabai("rawit", "hijau", 22, 33, 6, 1.3)}${cabai("rawit", "hijau", 34, 26.5, -26, 1.2)}`,
  CRW02: `${bayang(32, 20)}${cabai("rawit", "merahTua", 17, 18, -10, 1.25)}${cabai("rawit", "merah", 22, 33, 6, 1.3)}${cabai("rawit", "merah", 34, 26.5, -26, 1.2)}`,

  // Minyak goreng curah: kantong plastik bening berisi minyak, diikat karet.
  MGR01: `${bayang(32, 17)}
    <path d="M27 11.4c-2 4-10 8-11.5 18C14 38 21 43.2 32 43.2S50 38 48.5 29.4C47 19.4 39 15.4 37 11.4z" fill="#eef4f8" opacity=".75" stroke="#c9d6e0" stroke-width=".8"/>
    <path d="M17.6 22.4c7.4 2 21.4 2 28.8 0 2 2.8 2.6 4.8 2.2 7.4C49.6 38 43 43.2 32 43.2S14.4 38 15.4 29.8c-.4-2.6.2-4.6 2.2-7.4z" fill="#f3b322"/>
    <path d="M48.6 29.8C49.6 38 43 43.2 32 43.2c-3.6 0-6.8-.6-9.4-1.6 12.4.4 22.2-4.6 23.6-14.6.6-1.6.8-2.8.6-4.2 1.6 2.6 2 4.6 1.8 7z" fill="#d68f0e"/>
    <path d="M18.8 26.6c-1 4.6-.4 9.2 2.8 12.2" stroke="#ffffff" stroke-width="1.6" stroke-linecap="round" fill="none" opacity=".65"/>
    <path d="M27.6 10c-3.6-3.6-6.8-2.8-5.8-.2 1 1.6 4 1.2 5.8.2zM36.4 10c3.6-3.6 6.8-2.8 5.8-.2-1 1.6-4 1.2-5.8.2z" fill="#f4f8fb" stroke="#c9d6e0" stroke-width=".7"/>
    <path d="M27.4 11.6h9.2" stroke="#e0493a" stroke-width="1.6" stroke-linecap="round"/>`,
  // Minyak goreng kemasan bermerek I dan II: botol berlabel (warna label berbeda karena mereknya berbeda).
  MGR02: botolMinyak("#2f9a4a"),
  MGR03: botolMinyak("#2c6fb7"),

  // Gula pasir lokal: gula agak krem di dalam mangkuk.
  GLP01: `${bayang(32, 21)}
    <path d="M14.4 30c2-11.6 11-17.6 17.6-17.6S47.6 18.4 49.6 30z" fill="#f3eacf" stroke="#d9cba6" stroke-width=".7"/>
    <path d="M36.4 13.2c6.6 2.4 11.8 8.2 13.2 16.8H40.2c.2-6.8-1-12.4-3.8-16.8z" fill="#e2d6b6"/>
    ${kristal([[22, 25], [26, 20.5], [31, 17.4], [35.6, 21.4], [29, 26.4], [40.6, 25.6], [24.6, 28.4], [34, 27.6], [44.4, 27.8], [38.2, 18.6]], "#d2c299")}
    ${kristal([[24, 22.8], [33.2, 23.6], [28.6, 21.2], [37.6, 27.6]], "#ffffff")}
    ${kilauBintang(30, 16.6)}${kilauBintang(42.6, 22.2, 1.8)}
    ${mangkuk("#4f86c2", "#78a6d8", "#3b6ea8")}`,
  // Gula pasir premium: kemasan putih berlabel dan gula putih bersih.
  GLP02: `${bayang(32, 22)}
    <rect x="25" y="7" width="23" height="35" rx="2.6" fill="#fdfdfb" stroke="#cfd7e2" stroke-width=".9"/>
    <path d="M25.4 7.4h22.2v4.2H25.4z" fill="#2c6fb7"/>
    <path d="M25.4 11.6l1.8-1.4 1.8 1.4 1.8-1.4 1.8 1.4 1.8-1.4 1.8 1.4 1.8-1.4 1.8 1.4 1.8-1.4 1.8 1.4 1.8-1.4 1.8 1.4" stroke="#1f5b99" stroke-width=".6" fill="none"/>
    <rect x="25.4" y="21" width="22.2" height="9" fill="#2c6fb7"/>
    ${kristal([[31, 25.4], [35, 24.4], [39, 26], [43, 25]], "#ffffff")}
    <path d="M43.6 7.4h1.8a2.2 2.2 0 0 1 2.2 2.2v29.8a2.2 2.2 0 0 1-2.2 2.2h-1.8z" fill="#0b1a2e" opacity=".07"/>
    <path d="M8 42.6c2-7.6 7-12 12-12s10 4.4 12 12z" fill="#ffffff" stroke="#cdd6e2" stroke-width=".8"/>
    <path d="M23.4 31.4c3.4 1.8 6.6 5.6 8.6 11.2h-6.4c0-4.6-.6-8.4-2.2-11.2z" fill="#e5eaf1"/>
    ${kristal([[14, 38.6], [18, 35.4], [21.4, 39.4], [26.6, 39], [16.6, 41.4]], "#cfd8e4")}
    ${kilauBintang(17.4, 33.2, 1.8)}`,

  /* ---------- komoditas kajian (belum aktif, tetap disiapkan) */
  // Ikan kembung: punggung hijau kebiruan berbintik, perut perak.
  IKN01: `${bayang(32, 23)}
    <path d="M50.6 23.4l8-7.4c-.8 4.4-.8 10.6 0 15z" fill="#4c7a8f"/>
    <path d="M7.4 24.2c6-9 22-12 34-8.6 4.6 1.4 8 4.4 10 7.8-2 3.4-5.4 6.4-10 7.8-12 3.4-28 .4-34-7z" fill="#dfe7ec"/>
    <path d="M7.4 24.2c6-9 22-12 34-8.6 4.6 1.4 8 4.4 10 7.8-9.4-2.4-30.6-2.4-44 .8z" fill="#4f8096"/>
    <path d="M26 15.4l5-4 4 4.6zM30 32.2l4 3 2.4-3.4z" fill="#3f6b80"/>
    <g fill="#24485a"><circle cx="24" cy="19" r=".9"/><circle cx="29" cy="18" r=".9"/><circle cx="34" cy="18.4" r=".9"/><circle cx="39" cy="19.2" r=".9"/><circle cx="44" cy="20.4" r=".9"/><circle cx="31.6" cy="21" r=".7"/><circle cx="37" cy="21.4" r=".7"/></g>
    <path d="M18.4 18.6c1.8 3.4 1.8 7.4 0 10.6" stroke="#3a6175" stroke-width="1" fill="none"/>
    <path d="M14 27.4c8 2.2 22 2.4 31 .2" stroke="#ffffff" stroke-width="1.2" stroke-linecap="round" fill="none" opacity=".8"/>
    <circle cx="13.6" cy="22.6" r="2.2" fill="#ffffff"/><circle cx="13.6" cy="22.6" r="1.1" fill="#16232c"/>`,
  // Ikan tongkol: badan gemuk, punggung biru tua bergaris.
  IKN02: `${bayang(32, 23)}
    <path d="M49.4 24l9.4-10c-2 6.4-2 13.6 0 20z" fill="#25395a"/>
    <path d="M6.6 24.4c5.4-10.6 24-13.6 36-9 4 1.6 6.6 4.8 7.6 8.6-1 3.8-3.6 7-7.6 8.6-12 4.6-30.6 1.4-36-8.2z" fill="#dce3ea"/>
    <path d="M6.6 24.4c5.4-10.6 24-13.6 36-9 4 1.6 6.6 4.8 7.6 8.6-9.6-3-32-3.4-43.6.4z" fill="#2a4469"/>
    <path d="M21 17.4c2 2.4 2 4 0 6M27 16.2c2 2.6 2 4.6 0 7M33 16c2 2.6 2 4.6 0 7M39 16.6c2 2.4 2 4.4 0 6.6" stroke="#1a2d48" stroke-width="1.2" fill="none"/>
    <path d="M41 14.6l3-3.4 1.6 3.6zM44.6 32.6l2.4 2.6 1-3.2z" fill="#1f3354"/>
    <path d="M46 19.4l1.2-1.2.6 1.6zM46.4 28.4l1.2 1.2.6-1.6z" fill="#e8c34a"/>
    <path d="M17.4 18.4c1.8 3.6 1.8 7.6 0 11" stroke="#2c4566" stroke-width="1" fill="none"/>
    <circle cx="12.6" cy="22.8" r="2.3" fill="#ffffff"/><circle cx="12.6" cy="22.8" r="1.15" fill="#16232c"/>`,
  // Tepung terigu: kantong kertas bergambar gandum dan sedikit tepung.
  TPG01: `${bayang(32, 22)}
    <g transform="translate(-4 0)"><path d="M17 13.4l1.2-3.4 2.4 2 2.4-2 2.4 2 2.4-2 2.4 2 2.4-2 2.4 2 2.4-2 2.4 2 2.4-2 1.2 3.4 1.4 28.4a1.6 1.6 0 0 1-1.6 1.7H17.2a1.6 1.6 0 0 1-1.6-1.7z" fill="#f7f2e7" stroke="#d8ccb4" stroke-width=".8"/>
    <path d="M40.6 12l2.4-2 1.2 3.4 1.4 28.4a1.6 1.6 0 0 1-1.6 1.7h-4c1.4-9 2-20 .6-31.5z" fill="#e6dcc8"/>
    <path d="M30 38V22" stroke="#c8962f" stroke-width="1.2" stroke-linecap="round"/>
    <g fill="#e2b14a"><ellipse cx="28" cy="24.6" rx="1.4" ry="2.4" transform="rotate(-30 28 24.6)"/><ellipse cx="32" cy="24.6" rx="1.4" ry="2.4" transform="rotate(30 32 24.6)"/>
      <ellipse cx="28" cy="28.6" rx="1.4" ry="2.4" transform="rotate(-30 28 28.6)"/><ellipse cx="32" cy="28.6" rx="1.4" ry="2.4" transform="rotate(30 32 28.6)"/>
      <ellipse cx="28" cy="32.6" rx="1.4" ry="2.4" transform="rotate(-30 28 32.6)"/><ellipse cx="32" cy="32.6" rx="1.4" ry="2.4" transform="rotate(30 32 32.6)"/>
      <ellipse cx="30" cy="21" rx="1.2" ry="2.2"/></g></g>
    <path d="M41 43.4c1.6-5.6 4.6-7.8 8-7.8s6.2 2.2 7.6 7.8z" fill="#fdfcf8" stroke="#dcd5c4" stroke-width=".7"/>
    <path d="M50.6 35.8c3 1 5 3.6 6 7.6h-4c0-3-.6-5.6-2-7.6z" fill="#e9e4d8"/>`,
  // Kedelai: biji kuning di dalam mangkuk kayu.
  KDL01: `${bayang(32, 21)}
    <g stroke="#c9a03f" stroke-width=".5" fill="#e9c768">
      <circle cx="20" cy="27.6" r="2.8"/><circle cx="25.4" cy="25.6" r="2.8"/><circle cx="31" cy="24.6" r="2.8"/><circle cx="36.6" cy="25" r="2.8"/><circle cx="42.2" cy="26.4" r="2.8"/><circle cx="46" cy="28.2" r="2.6"/>
      <circle cx="22.6" cy="22.4" r="2.8"/><circle cx="28.2" cy="20.6" r="2.8"/><circle cx="33.8" cy="20.2" r="2.8"/><circle cx="39.4" cy="21.6" r="2.8"/>
      <circle cx="25.6" cy="17.2" r="2.7"/><circle cx="31" cy="16" r="2.7"/><circle cx="36.4" cy="17" r="2.7"/></g>
    <g fill="#b58a35"><circle cx="21" cy="28.4" r=".5"/><circle cx="31.6" cy="25.4" r=".5"/><circle cx="29" cy="21.4" r=".5"/><circle cx="37.2" cy="17.8" r=".5"/><circle cx="43" cy="27.2" r=".5"/></g>
    <g fill="#f7e2a0"><circle cx="24.6" cy="24.6" r=".8"/><circle cx="30.2" cy="15.2" r=".8"/><circle cx="35.8" cy="24" r=".8"/></g>
    ${mangkuk("#a8733f", "#c68f55", "#8a5a2c")}`,
  // Tempe: balok tempe putih berbintik di atas daun pisang.
  TMP01: `${bayang(32, 25)}
    <path d="M3 33.4c10 8.4 40 12 58-2.6-10 10-40 14-58 2.6z" fill="#3f8a33"/>
    <path d="M3 33.4c18-6 40-6.6 58-2.6-18 12-48 10.8-58 2.6z" fill="#5aa845"/>
    <path d="M6 33.4c16-3.4 36-4.4 52-2.2" stroke="#8fce6e" stroke-width=".8" fill="none"/>
    <path d="M10 23.6l25.6-9.4 20.4 7-25.4 9.8z" fill="#f6f2e6"/>
    <path d="M10 23.6l20.6 7.4v6.8L10 30.4z" fill="#e7dcc1"/>
    <path d="M30.6 31l25.4-9.8v6.8l-25.4 9.8z" fill="#d6c7a5"/>
    <g fill="#dcc79a"><circle cx="20" cy="22.6" r="1"/><circle cx="26" cy="20.8" r="1"/><circle cx="32" cy="18.6" r="1"/><circle cx="38" cy="18.8" r="1"/><circle cx="44" cy="20.8" r="1"/><circle cx="30" cy="24.4" r="1"/><circle cx="36" cy="22.4" r="1"/><circle cx="42" cy="24.6" r="1"/><circle cx="24" cy="25.6" r="1"/><circle cx="48" cy="22.6" r="1"/></g>
    <g fill="#bea36b"><circle cx="15" cy="28.4" r="1"/><circle cx="20" cy="30.6" r="1"/><circle cx="25.4" cy="32.6" r="1"/><circle cx="35" cy="33.4" r="1"/><circle cx="41" cy="31" r="1"/><circle cx="47" cy="28.8" r="1"/><circle cx="52" cy="26.8" r="1"/></g>`,
  // Susu kental manis: kaleng berlabel dengan lelehan susu.
  SKM01: `${bayang(32, 15)}
    <path d="M20 12h24v28c0 1.8-5.4 3.2-12 3.2S20 41.8 20 40z" fill="#c9d0d9"/>
    <rect x="20" y="16.4" width="24" height="20.6" fill="#2c6fb7"/>
    <path d="M20 16.4h24v4.4H20z" fill="#ffffff"/>
    <path d="M32 22.6c2.6 3.2 4 5.2 4 7a4 4 0 0 1-8 0c0-1.8 1.4-3.8 4-7z" fill="#fffaf0"/>
    <path d="M30.4 29.4a1.8 1.8 0 0 0 1.8 1.8" stroke="#c9d6e6" stroke-width=".9" stroke-linecap="round" fill="none"/>
    <path d="M38.6 12H44v28c0 1-1.6 2-4 2.6 1-9 .6-20.6-1.4-30.6z" fill="#000" opacity=".1"/>
    <ellipse cx="32" cy="12" rx="12" ry="3.2" fill="#dde3ea"/><ellipse cx="32" cy="12" rx="9.6" ry="2.2" fill="#c3cbd5"/>
    <path d="M22.4 18.6h6" stroke="#2c6fb7" stroke-width="1.2" stroke-linecap="round"/>`,
  // Garam halus: kemasan plastik berlabel biru dan sejumput garam putih.
  GRM01: `${bayang(32, 21)}
    <path d="M24 10h22l1.6 30c-6.6 1.8-18.6 1.8-25.2 0z" fill="#fdfdfd" stroke="#cfd7e2" stroke-width=".9"/>
    <path d="M24 10h22v3.4H24z" fill="#e1e6ed"/>
    <rect x="23.4" y="20" width="23.6" height="10" fill="#1f8fd0"/>
    ${kristal([[30, 25], [35, 24], [40, 25.4]], "#ffffff")}
    <path d="M8 42.8c2-6.6 6.4-10 11-10s9 3.4 11 10z" fill="#ffffff" stroke="#cdd6e2" stroke-width=".8"/>
    <path d="M22.4 33.4c3 1.8 6 5 7.6 9.4h-5.4c0-3.8-.6-7-2.2-9.4z" fill="#e3e9f0"/>
    <g fill="#c9d3df"><circle cx="13" cy="39.6" r=".6"/><circle cx="16.4" cy="37" r=".6"/><circle cx="19.6" cy="40.4" r=".6"/><circle cx="22" cy="37.8" r=".6"/><circle cx="25.6" cy="40.8" r=".6"/></g>`,
  // Mi instan: lempeng mi kering yang bergelombang.
  MIE01: `${bayang(32, 20)}
    <rect x="13" y="12" width="38" height="29" rx="6" fill="#f1c25a"/>
    <path d="M51 18v17a6 6 0 0 1-6 6H19a6 6 0 0 1-5.4-3.4c7 1 30 1.4 35.4-4.4 1-3.6 1.4-10 2-15.2z" fill="#d9a23a"/>
    <path d="M17 17.4c2.4-2 3.6 2 6 0s3.6 2 6 0 3.6 2 6 0 3.6 2 6 0 3.6 2 6 0M17 23.4c2.4-2 3.6 2 6 0s3.6 2 6 0 3.6 2 6 0 3.6 2 6 0 3.6 2 6 0M17 29.4c2.4-2 3.6 2 6 0s3.6 2 6 0 3.6 2 6 0 3.6 2 6 0 3.6 2 6 0M17 35.4c2.4-2 3.6 2 6 0s3.6 2 6 0 3.6 2 6 0 3.6 2 6 0" stroke="#c98d24" stroke-width="1.2" stroke-linecap="round" fill="none"/>
    <path d="M16.6 14.6c4-1.2 10-1.4 14-.8" stroke="#fde3a2" stroke-width="1.6" stroke-linecap="round" fill="none"/>`,
  // Margarin sachet: kemasan kecil kuning bergerigi.
  MRG01: `${bayang(32, 21)}
    <rect x="11" y="13" width="42" height="26" rx="3" fill="#f6cf43"/>
    <path d="M11 16.4h1.6M11 19.6h1.6M11 22.8h1.6M11 26h1.6M11 29.2h1.6M11 32.4h1.6M11 35.6h1.6M51.4 16.4H53M51.4 19.6H53M51.4 22.8H53M51.4 26H53M51.4 29.2H53M51.4 32.4H53M51.4 35.6H53" stroke="#d9a91c" stroke-width="1"/>
    <path d="M53 22v14a3 3 0 0 1-3 3H16c10-1.6 30-4.4 37-17z" fill="#e2b324"/>
    <ellipse cx="32" cy="25.6" rx="10.6" ry="7" fill="#fff4bf"/>
    <path d="M26 26.6c2.4-3.6 7.6-4 10.4-1.4 1.6 1.6.6 3.6-1.8 3.4-2.2-.2-2.6-2.6-.6-3.2" stroke="#efbd2a" stroke-width="1.4" stroke-linecap="round" fill="none"/>`,

  // Cadangan untuk komoditas yang belum punya gambar: keranjang belanja.
  UMUM: `${bayang(32, 20)}
    <path d="M22 18c0-6 4.4-10 10-10s10 4 10 10" stroke="#9a6a3a" stroke-width="2.4" fill="none"/>
    <path d="M24 18c-2-4.6 1.4-9.6 6-8.6M40 18c2-4.6-1.4-9.6-6-8.6" stroke="#4f9a3c" stroke-width="3" stroke-linecap="round" fill="none"/>
    <path d="M10 18h44l-4.4 23.4a2.6 2.6 0 0 1-2.6 2.1H17a2.6 2.6 0 0 1-2.6-2.1z" fill="#c68f55"/>
    <path d="M12 24h40M13 30h38M14.2 36h35.6M22 18l2 25.4M32 18v25.4M42 18l-2 25.4" stroke="#a8733f" stroke-width="1.1"/>
    <rect x="8" y="16" width="48" height="4" rx="2" fill="#a8733f"/>`,
};

/** Kode gambar yang tersedia (untuk uji). */
export const KODE_GAMBAR = Object.keys(GAMBAR);

/** SVG ilustrasi untuk kode varian (mis. "CRW01") atau kode komoditas (mis. "CRW"). */
export function gambarKomoditas(kode) {
  const k = String(kode || "");
  const isi = GAMBAR[k] || GAMBAR[k.slice(0, 3)] || GAMBAR[`${k.slice(0, 3)}01`] || GAMBAR.UMUM;
  return `<svg class="gambar-komoditas" viewBox="0 0 64 48" aria-hidden="true" focusable="false">${isi}</svg>`;
}

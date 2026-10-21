// Hitungan inflasi resmi BPS yang dipakai Dasbor TPID dan Mode Videotron. Murni tanpa DOM supaya bisa diuji di Node.

// Sasaran inflasi nasional yang ditetapkan pemerintah bersama Bank Indonesia: 2,5 ± 1 persen untuk 2024 sampai 2027.
// Tahun yang sasarannya belum ditetapkan tidak diberi penanda.
const SASARAN = { 2024: [2.5, 1], 2025: [2.5, 1], 2026: [2.5, 1], 2027: [2.5, 1] };
const ada = (x) => x !== null && x !== undefined && Number.isFinite(Number(x));
const koma = (x, d) => Number(x).toLocaleString("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d });

export function sasaran(periode) {
  const s = SASARAN[Number(String(periode || "").slice(0, 4))];
  return s ? { tengah: s[0], bawah: s[0] - s[1], atas: s[0] + s[1], teks: `${koma(s[0], 1)} ± ${koma(s[1], 0)}%` } : null;
}

/** ["Dalam sasaran", "baik"], ["Di atas sasaran", "perhatian"], ["Di bawah sasaran", "netral"], atau null. */
export function statusSasaran(x, periode) {
  const s = sasaran(periode);
  if (!s || !ada(x)) return null;
  if (x > s.atas) return ["Di atas sasaran", "perhatian"];
  if (x < s.bawah) return ["Di bawah sasaran", "netral"];
  return ["Dalam sasaran", "baik"];
}

/** Angka utama: Berita Resmi Statistik bila lebih baru daripada tabel Web API, selain itu angka tabel. */
export function angkaUtama(ib) {
  const r = ib?.rilis?.[0];
  if (r && (!ib.periode || r.periode > ib.periode)) {
    return { periode: r.periode, yoy: r.yoy, mtm: r.mtm ?? null, ytd: null, asal: "rilis", tanggal: r.tanggal, url: r.url };
  }
  return { periode: ib?.periode, yoy: ib?.umum?.yoy ?? null, mtm: ib?.umum?.mtm ?? null, ytd: ib?.umum?.ytd ?? null, asal: "tabel" };
}

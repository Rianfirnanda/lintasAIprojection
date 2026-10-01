// Selisih harga sekarang dengan harga pembanding (mis. sebulan lalu), dalam rupiah dan persen.
// Murni logika tanpa DOM, jadi bisa diuji di Node. Format angka sama dengan rp() dan persen() di app.js.

const rp = (x) => `Rp${Math.round(x).toLocaleString("id-ID")}`;
const persen = (x) => `${x > 0 ? "+" : ""}${Number(x).toLocaleString("id-ID", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;

const BULAN_SINGKAT = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
/** Tanggal singkat tanpa tahun, mis. "1 Sep". */
export function tglPendek(iso) {
  if (!iso) return "–";
  const [, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${d} ${BULAN_SINGKAT[m - 1]}`;
}

/** Harga sekarang dibanding harga pembanding (default sebulan lalu): { kini, lalu, tanggal, selisih, persen } atau null. */
export function selisihHarga(v, periode = "bulanan") {
  const acuan = v?.harga_acuan?.[periode];
  if (!acuan || v.harga_terakhir === null || v.harga_terakhir === undefined) return null;
  return { kini: v.harga_terakhir, lalu: acuan.harga, tanggal: acuan.tanggal, selisih: v.harga_terakhir - acuan.harga, persen: v.perubahan?.[periode] ?? null };
}

/** "Naik Rp20.000", "Turun Rp1.250", atau "Tetap". */
export function teksSelisih(selisih) {
  if (!selisih) return "Tetap";
  return `${selisih > 0 ? "Naik" : "Turun"} ${rp(Math.abs(selisih))}`;
}

/** Arah perubahan untuk warna dan tanda: naik, turun, atau datar. */
export const arahSelisih = (s) => (!s || !s.selisih ? "datar" : s.selisih > 0 ? "naik" : "turun");
export const TANDA_ARAH = { naik: "▲", turun: "▼", datar: "▬" };

/** Satu baris ringkas "▲ Naik Rp20.000 (+44,2%)" untuk kartu dan daftar. */
export function htmlSelisih(s, { kelas = "" } = {}) {
  if (!s) return `<span class="selisih datar ${kelas}">Belum ada pembanding</span>`;
  const a = arahSelisih(s);
  return `<span class="selisih ${a} ${kelas}"><span class="segitiga" aria-hidden="true">${TANDA_ARAH[a]}</span>${teksSelisih(s.selisih)}` +
    `${s.persen !== null && s.persen !== undefined && s.selisih ? ` <small>(${persen(s.persen)})</small>` : ""}</span>`;
}

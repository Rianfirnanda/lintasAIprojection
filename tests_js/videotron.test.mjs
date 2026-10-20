// Mode Videotron: tampilan lengkap dari data, harga dibagi rata per layar, angka cara Indonesia, tanpa tombol.
import assert from "node:assert/strict";
import test from "node:test";
import { susunTampilan, teksBerjalan, teksUbah, garisSvg, wakilKomoditas, arah } from "../site/assets/videotron-isi.js";

const v = (kode, nama, komoditas, kini, mingguLalu, bulanLalu, ekstra = {}) => ({
  kode, nama, kode_komoditas: kode.slice(0, 3), komoditas, satuan: "kg", harga_terakhir: kini, tanggal_terakhir: "2026-10-20",
  harga_acuan: { mingguan: { harga: mingguLalu, tanggal: "2026-10-13" }, bulanan: { harga: bulanLalu, tanggal: "2026-09-20" } },
  perubahan: { mingguan: ((kini - mingguLalu) / mingguLalu) * 100, bulanan: ((kini - bulanLalu) / bulanLalu) * 100 }, ...ekstra,
});
const VARIAN = [
  v("CRW01", "Cabai Rawit Hijau", "Cabai Rawit", 80000, 70000, 55000, { sinyal: "tinggi", proyeksi_h7: { prediksi: 84000, bawah: 78000, atas: 90000 } }),
  v("CMR01", "Cabai Merah Besar", "Cabai Merah", 78000, 70000, 50000),
  v("BRS03", "Beras Kualitas Medium I", "Beras", 14375, 14375, 14375, { proyeksi_h7: { prediksi: 14375, bawah: 14100, atas: 14600 } }),
  v("DAM01", "Daging Ayam Ras Segar", "Daging Ayam", 35000, 37000, 40000),
];
const DATA = {
  ringkasan: { varian: VARIAN, hari_raya: { berikutnya: { nama: "Hari Raya Natal", tanggal: "2026-12-25", hari_menuju: 66, status: "pasti" },
    profil_top: [{ kode: "CMR01", nama: "Cabai Merah Besar", kenaikan_puncak_persen: 6.7 }] } },
  sinyal: { sinyal: [
    { aktif: true, jenis: "anomali_harga", keparahan: "tinggi", kode_varian: "CRW01", judul: "Harga Cabai Rawit Hijau naik 45%", nilai_aktual: 80000, baseline: 55000 },
    { aktif: true, jenis: "data_terlambat", keparahan: "tinggi", judul: "Data Pasar A belum masuk" },
  ] },
  seri: { CRW01: { aktual: Array.from({ length: 40 }, (_, i) => 50000 + i * 800) }, CMR01: { aktual: Array.from({ length: 40 }, () => 78000) } },
};

test("semua tampilan tersusun dengan angka rupiah dan tanggal Indonesia", () => {
  const t = susunTampilan(DATA, { perHalaman: 12 });
  assert.deepEqual(t.map((x) => x.kunci), ["ringkasan", "harga-1", "gerak", "tren", "peringatan", "perkiraan", "hariraya"]);
  const semua = t.map((x) => x.isi).join(" ");
  assert.match(semua, /Rp80\.000/);
  assert.match(t[0].isi, /2 harga naik|<b>2<\/b><span>harga naik/);
  assert.match(t.find((x) => x.kunci === "peringatan").isi, /Sekarang <b>Rp80\.000\/kg<\/b>, biasanya Rp55\.000\/kg/);
  assert.doesNotMatch(t.find((x) => x.kunci === "peringatan").isi, /Pasar A/); // catatan data tidak tampil di videotron
  assert.match(t.find((x) => x.kunci === "hariraya").isi, /66<\/b>.*25 Desember 2026/s);
  assert.doesNotMatch(semua, /<button/);
  assert.doesNotMatch(semua, /undefined|NaN|null/);
});

test("harga dibagi rata per layar", () => {
  const banyak = Array.from({ length: 21 }, (_, i) => v(`BRS${String(i).padStart(2, "0")}`, `Barang ${i}`, "Beras", 10000, 10000, 10000));
  const hitung = (n) => susunTampilan({ ringkasan: { varian: banyak }, sinyal: null }, { perHalaman: n })
    .filter((x) => x.kunci.startsWith("harga")).map((x) => (x.isi.match(/class="vt-harga /g) || []).length);
  assert.deepEqual(hitung(12), [11, 10]);
  assert.deepEqual(hitung(4), [4, 4, 4, 3, 3, 3]);
});

test("perubahan, garis tren, teks berjalan, dan wakil komoditas", () => {
  assert.equal(teksUbah(VARIAN[0]).teks, "▲ Rp10.000 (+14,3%)");
  assert.equal(teksUbah(VARIAN[2]).teks, "▬ Tetap");
  assert.equal(teksUbah(VARIAN[3]).arah, "turun");
  assert.equal(arah(0.3), "datar");
  assert.match(garisSvg([1, 2, null, 4]), /<path class="vt-jalur" d="M0\.0 /);
  assert.equal(garisSvg([5]), "");
  assert.match(teksBerjalan(VARIAN), /Cabai Rawit Hijau<\/b> Rp80\.000\/kg/);
  assert.deepEqual(wakilKomoditas([...VARIAN, v("CRW02", "Cabai Rawit Merah", "Cabai Rawit", 80000, 80000, 79000)]).map((x) => x.kode), ["CRW01", "CMR01", "BRS03", "DAM01"]);
});

test("tanpa data harga tidak rusak", () => {
  const t = susunTampilan({ ringkasan: { varian: [] }, sinyal: null });
  assert.equal(t.length, 1);
  assert.match(t[0].isi, /belum tersedia/);
});

test("perkiraan: yang bergeser di bawah 0,5% ditulis tetap; bila semua tetap, kisaran terlebar tampil dulu", () => {
  const p = susunTampilan(DATA, { perHalaman: 12 }).find((x) => x.kunci === "perkiraan");
  assert.match(p.isi, /Cabai Rawit Hijau/);
  assert.doesNotMatch(p.isi, /Beras Kualitas Medium I/); // tetap, tidak masuk daftar yang berubah
  const tetap = structuredClone(DATA);
  tetap.ringkasan.varian[0].proyeksi_h7 = { prediksi: 80000, bawah: 70000, atas: 95000 };
  const q = susunTampilan(tetap, { perHalaman: 12 }).find((x) => x.kunci === "perkiraan");
  assert.match(q.sub, /Semua harga diperkirakan tetap/);
  assert.match(q.isi, /Belum ada tanda harga akan naik atau turun/);
  assert.ok(q.isi.indexOf("Cabai Rawit Hijau") < q.isi.indexOf("Beras Kualitas Medium I"));
  assert.doesNotMatch(q.isi, /Rp80\.000<\/b>/);
});

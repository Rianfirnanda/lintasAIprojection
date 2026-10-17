// Mesin jawab Tanya Takar: menjawab dari data, angka cara Indonesia, tanpa istilah teknis, dan jujur bila tidak tahu.
import assert from "node:assert/strict";
import test from "node:test";
import { jawab, kenaliBarang, konteksAi } from "../site/assets/tanya-mesin.js";
import { ISTILAH_TEKNIS } from "./istilah-daftar.mjs";

const v = (kode, nama, komoditas, kini, mingguLalu, bulanLalu, ekstra = {}) => ({
  kode, nama, komoditas, satuan: "kg", harga_terakhir: kini, tanggal_terakhir: "2026-10-16",
  harga_acuan: { mingguan: { harga: mingguLalu, tanggal: "2026-10-09" }, bulanan: { harga: bulanLalu, tanggal: "2026-09-16" } },
  perubahan: { mingguan: ((kini - mingguLalu) / mingguLalu) * 100, bulanan: ((kini - bulanLalu) / bulanLalu) * 100 }, ...ekstra,
});
const DATA = {
  meta: { tanggal_data_terakhir: "2026-10-16", dibuat: "2026-10-17T02:02:00+07:00" },
  ringkasan: {
    varian: [
      v("CRW01", "Cabai Rawit Hijau", "Cabai Rawit", 80000, 70000, 55000, { sinyal: "tinggi", proyeksi_h7: { prediksi: 82000, bawah: 76000, atas: 88000 } }),
      v("CRW02", "Cabai Rawit Merah", "Cabai Rawit", 80000, 80000, 60000),
      v("CMR01", "Cabai Merah Besar", "Cabai Merah", 78000, 70000, 50000),
      v("CMR02", "Cabai Merah Keriting", "Cabai Merah", 80000, 80000, 55000),
      v("BRS03", "Beras Kualitas Medium I", "Beras", 14375, 14375, 14375, { proyeksi_h7: { prediksi: 14375, bawah: 13417, atas: 15402 } }),
      v("DAM01", "Daging Ayam Ras Segar", "Daging Ayam", 35000, 35000, 40000),
    ],
    hari_raya: { berikutnya: { nama: "Hari Raya Natal", tanggal: "2026-12-25", hari_menuju: 69, status: "pasti" },
      profil_top: [{ nama: "Cabai Merah Besar", kenaikan_puncak_persen: 7 }] },
  },
  sinyal: { sinyal: [{ id: "abc", aktif: true, keparahan: "tinggi", kode_varian: "CRW01", varian: "Cabai Rawit Hijau",
    judul: "Harga Cabai Rawit Hijau naik 45% dari harga normal", narasi: "Curah hujan 7 hari terakhir 41 mm, masih wajar." }] },
};
const teks = (r) => r.baris.join(" ");

test("mengenali barang dari kalimat sehari-hari", () => {
  assert.deepEqual(kenaliBarang("berapa harga cabai rawit hari ini?", DATA.ringkasan.varian).map((x) => x.kode), ["CRW01", "CRW02"]);
  assert.deepEqual(kenaliBarang("harga cabai rawit merah", DATA.ringkasan.varian).map((x) => x.kode), ["CRW02"]);
  assert.equal(kenaliBarang("harga cabai", DATA.ringkasan.varian).length, 4);
  assert.deepEqual(kenaliBarang("beras medium naik?", DATA.ringkasan.varian).map((x) => x.kode), ["BRS03"]);
  assert.deepEqual(kenaliBarang("halo", DATA.ringkasan.varian), []);
});

test("harga barang dijawab dengan rupiah, tanggal, dan perubahan", async () => {
  const r = await jawab("Berapa harga cabai rawit hijau?", DATA);
  assert.equal(r.niat, "harga");
  assert.match(teks(r), /Cabai Rawit Hijau sekarang Rp80\.000 per kg \(data 16 Oktober 2026\)/);
  assert.match(teks(r), /minggu lalu naik Rp10\.000 \(\+14,3%\)/);
  assert.match(teks(r), /perlu diwaspadai/);
  assert.equal(r.tautan[0].href, "harga.html#barang=CRW01");
  assert.equal(r.perluAi, false);
  const banyak = await jawab("harga cabai", DATA);
  assert.equal(banyak.baris[0], "Ada 4 jenis cabai:");
});

test("naik paling tinggi, perkiraan, peringatan, hari raya, dan data", async () => {
  const naik = await jawab("apa yang naik paling tinggi?", DATA);
  assert.match(naik.baris[1], /^1\. Cabai Merah Besar: Rp78\.000\/kg, naik Rp28\.000 \(\+56,0%\)/);
  const turun = await jawab("apa yang turun paling banyak?", DATA);
  assert.match(teks(turun), /Daging Ayam Ras Segar.*turun Rp5\.000/);
  const kira = await jawab("perkiraan harga cabai rawit hijau minggu depan", DATA);
  assert.match(teks(kira), /sekitar Rp82\.000 per kg dalam 7 hari .*naik Rp2\.000.*Kisarannya Rp76\.000 sampai Rp88\.000/);
  const kira30 = await jawab("perkiraan harga beras medium 30 hari", DATA,
    async () => ({ proyeksi: Array.from({ length: 30 }, (_, i) => ({ prediksi: 14000 + i * 10, bawah: 13000, atas: 15000 })) }));
  assert.match(teks(kira30), /sekitar Rp14\.290 per kg dalam 30 hari/);
  assert.match(teks(await jawab("ada peringatan apa?", DATA)), /1 peringatan aktif, 1 di antaranya tingkat tinggi/);
  assert.match(teks(await jawab("kapan lebaran atau natal?", DATA)), /Hari Raya Natal, 25 Desember 2026, 69 hari lagi/);
  assert.match(teks(await jawab("kapan data terakhir diperbarui?", DATA)), /16 Oktober 2026/);
});

test("pertanyaan penyebab jujur dan boleh diteruskan ke AI; pertanyaan asing tidak dikarang", async () => {
  const k = await jawab("kenapa cabai rawit hijau naik?", DATA);
  assert.match(teks(k), /tidak bisa memastikan penyebabnya/);
  assert.match(teks(k), /Curah hujan 7 hari/);
  assert.equal(k.perluAi, true);
  const asing = await jawab("siapa presiden pertama?", DATA);
  assert.equal(asing.niat, "tidak_dikenal");
  assert.equal(asing.perluAi, true);
  assert.doesNotMatch(teks(asing), /\d/);
});

test("jawaban tanpa istilah teknis; konteks AI ringkas dan berisi angka situs", async () => {
  for (const q of ["harga cabai", "apa yang naik paling tinggi", "perkiraan harga beras medium minggu depan", "ada peringatan apa", "halo"]) {
    assert.doesNotMatch(teks(await jawab(q, DATA)), ISTILAH_TEKNIS, q);
  }
  const k = konteksAi(DATA);
  assert.match(k, /Cabai Rawit Hijau: Rp80\.000\/kg/);
  assert.ok(k.length < 9001);
});

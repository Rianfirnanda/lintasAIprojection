import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { KODE_GAMBAR, gambarKomoditas } from "../site/assets/gambar-komoditas.js";
import { arahSelisih, bandingPerkiraan, htmlSelisih, ringkasHariIni, selisihHarga, teksPerkiraan, teksSelisih, tglPendek } from "../site/assets/selisih.js";

const varianCsv = readFileSync(new URL("../config/komoditas.csv", import.meta.url), "utf-8")
  .trim().split("\n").slice(1).map((baris) => baris.split(",")[2]);
const umum = gambarKomoditas("ZZZ99");

test("setiap varian di komoditas.csv punya gambar sendiri, bukan gambar cadangan", () => {
  assert.ok(varianCsv.length >= 21);
  for (const kode of varianCsv) assert.notEqual(gambarKomoditas(kode), umum, `${kode} memakai gambar cadangan`);
});

test("varian yang berbeda rupa punya gambar berbeda", () => {
  assert.notEqual(gambarKomoditas("CRW01"), gambarKomoditas("CRW02"), "rawit hijau dan merah harus beda");
  assert.notEqual(gambarKomoditas("CMR01"), gambarKomoditas("CMR02"), "cabai besar dan keriting harus beda");
  assert.notEqual(gambarKomoditas("MGR01"), gambarKomoditas("MGR02"), "minyak curah dan kemasan harus beda");
  assert.notEqual(gambarKomoditas("GLP01"), gambarKomoditas("GLP02"));
  assert.match(gambarKomoditas("CRW01"), /#58ad3f/, "rawit hijau digambar hijau");
  assert.doesNotMatch(gambarKomoditas("CRW01"), /#e2271c/, "rawit hijau tidak boleh merah");
});

test("kode komoditas dan varian tanpa gambar khusus memakai gambar komoditasnya", () => {
  assert.equal(gambarKomoditas("BRS05"), gambarKomoditas("BRS"));
  assert.equal(gambarKomoditas("DSP02"), gambarKomoditas("DSP01"));
  assert.equal(gambarKomoditas("CRW"), gambarKomoditas("CRW01"));
  assert.equal(gambarKomoditas(undefined), umum);
});

test("SVG gambar utuh dan bersih", () => {
  for (const kode of KODE_GAMBAR) {
    const svg = gambarKomoditas(kode);
    assert.match(svg, /^<svg class="gambar-komoditas" viewBox="0 0 64 48" aria-hidden="true"/);
    assert.doesNotMatch(svg, /undefined|NaN|\$\{/, kode);
    for (const tag of ["g", "svg"]) {
      const buka = (svg.match(new RegExp(`<${tag}[ >]`, "g")) || []).length;
      const tutup = (svg.match(new RegExp(`</${tag}>`, "g")) || []).length;
      assert.equal(buka, tutup, `${kode}: <${tag}> tidak seimbang`);
    }
  }
});

const cabai = {
  kode: "CRW02", harga_terakhir: 65250, perubahan: { bulanan: 44.2, mingguan: 42.62 },
  harga_acuan: { bulanan: { harga: 45250, tanggal: "2026-09-01" }, mingguan: { harga: 45750, tanggal: "2026-09-24" }, tahunan: null },
};

test("selisih harga dihitung dari harga pembanding", () => {
  assert.deepEqual(selisihHarga(cabai), { kini: 65250, lalu: 45250, tanggal: "2026-09-01", selisih: 20000, persen: 44.2 });
  assert.equal(selisihHarga(cabai, "mingguan").selisih, 19500);
  assert.equal(selisihHarga(cabai, "tahunan"), null);
  assert.equal(selisihHarga({ harga_terakhir: null, harga_acuan: cabai.harga_acuan }), null);
  assert.equal(selisihHarga({ harga_terakhir: 1000 }), null);
});

test("teks selisih mudah dibaca", () => {
  assert.equal(teksSelisih(20000), "Naik Rp20.000");
  assert.equal(teksSelisih(-1250), "Turun Rp1.250");
  assert.equal(teksSelisih(0), "Tetap");
  assert.equal(arahSelisih({ selisih: 0 }), "datar");
  assert.equal(arahSelisih(null), "datar");
  assert.equal(tglPendek("2026-09-01"), "1 Sep");
  assert.equal(tglPendek(null), "–");
  const html = htmlSelisih(selisihHarga(cabai));
  assert.match(html, /class="selisih naik /);
  assert.match(html, /Naik Rp20\.000 <small>\(\+44,2%\)<\/small>/);
  assert.match(htmlSelisih({ selisih: -500, persen: -1.23 }), /Turun Rp500 <small>\(-1,2%\)<\/small>/);
  assert.match(htmlSelisih({ selisih: 0, persen: 0 }), /Tetap<\/span>$/);
  assert.match(htmlSelisih(null), /Belum ada pembanding/);
});

test("ringkasan hari ini memakai rupiah, ambang 0,5%, dan kalimat biasa", () => {
  const v = (nama, kini, lalu, satuan = "kg") => ({ nama, satuan, harga_terakhir: kini,
    harga_acuan: { mingguan: { harga: lalu, tanggal: "2026-10-09" } }, perubahan: { mingguan: ((kini - lalu) / lalu) * 100 } });
  const r = ringkasHariIni([v("Cabai Rawit Hijau", 80000, 70000), v("Beras Medium", 14400, 14375), v("Daging Ayam", 35000, 40000)]);
  assert.equal(r.naik, 1);
  assert.equal(r.turun, 1);
  assert.equal(r.kalimat, "Dibanding minggu lalu, 1 harga naik dan 1 harga turun. Naik paling banyak: Cabai Rawit Hijau, Rp10.000 per kg (+14,3%).");
  assert.match(ringkasHariIni([v("Beras", 14375, 14375)]).kalimat, /stabil/);
  assert.match(ringkasHariIni([]).kalimat, /Belum ada harga minggu lalu/);
  assert.match(ringkasHariIni([v("Gula", 18000, 20000)]).kalimat, /tidak ada harga yang naik dan 1 harga turun\.$/);
});

test("perkiraan yang praktis sama dengan harga sekarang ditulis tetap", () => {
  assert.equal(teksPerkiraan(bandingPerkiraan(35000, { prediksi: 35000, bawah: 29242, atas: 41892 })), "diperkirakan tetap");
  assert.equal(bandingPerkiraan(40000, { prediksi: 40150 }).tetap, true); // 0,375%
  assert.equal(teksPerkiraan(bandingPerkiraan(80000, { prediksi: 84000 })), "sekitar Rp84.000 (naik Rp4.000)");
  assert.equal(teksPerkiraan(bandingPerkiraan(80000, { prediksi: 76000 })), "sekitar Rp76.000 (turun Rp4.000)");
  assert.equal(bandingPerkiraan(80000, null), null);
  assert.equal(teksPerkiraan(null), "belum ada perkiraan");
});

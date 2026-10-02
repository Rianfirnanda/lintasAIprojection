// Pembaca berkas CSV harga di browser (unggahan operator lewat situs).
import { test } from "node:test";
import assert from "node:assert/strict";
import { angkaHarga, bacaCSV, petakanHarga, tanggalISO } from "../site/assets/berkas-harga.js";

test("CSV dengan kutip, koma di dalam sel, dan titik koma ala Excel Indonesia", () => {
  assert.deepEqual(bacaCSV('a,b\n"x, y","say ""hai"""\n'), [["a", "b"], ["x, y", 'say "hai"']]);
  assert.deepEqual(bacaCSV("﻿a;b\r\n1;2\r\n\r\n"), [["a", "b"], ["1", "2"]]);
});

test("tanggal dan harga mengikuti aturan pipeline", () => {
  assert.equal(tanggalISO("2026-10-01"), "2026-10-01");
  assert.equal(tanggalISO("1/10/2026"), "2026-10-01");
  assert.equal(tanggalISO("01.10.2026"), "2026-10-01");
  assert.equal(tanggalISO("31/02/2026"), null);
  assert.equal(tanggalISO("kemarin"), null);
  assert.equal(angkaHarga("Rp 45.000"), 45000);
  assert.equal(angkaHarga("12.500,50"), 12500.5);
  assert.equal(angkaHarga("45,000"), 45000);
  assert.equal(angkaHarga("4,5"), 4.5);
  assert.equal(angkaHarga("0"), null);
  assert.equal(angkaHarga("abc"), null);
});

test("kolom alias dipetakan, baris salah dilewati dengan alasannya", () => {
  const h = petakanHarga("Tgl;Pasar;Varian;Harga Rp;Petugas\n01/10/2026;psr01;cmr01;Rp 55.000;ptg01\n;PSR01;CMR01;1000;\n02/10/2026;PSR01;CMR01;nol;\n");
  assert.equal(h.galatBerkas, "");
  assert.equal(h.baris.length, 1);
  assert.deepEqual({ ...h.baris[0], id_klien: "?" }, {
    tanggal: "2026-10-01", kode_pasar: "PSR01", kode_varian: "CMR01", harga: 55000, satuan: "", kode_sumber: "",
    petugas: "PTG01", responden: "", id_klien: "?", waktu_input: "", catatan: "",
  });
  assert.deepEqual(h.galat.map((g) => g.baris), [3, 4]);
});

test("berkas yang sama diunggah dua kali menghasilkan ID yang sama (tidak ganda), baris kembar tetap terpisah", () => {
  const isi = "tanggal,kode_pasar,kode_varian,harga\n2026-10-01,PSR01,CMR01,55000\n2026-10-01,PSR01,CMR01,55000\n";
  const a = petakanHarga(isi).baris.map((b) => b.id_klien);
  const b = petakanHarga(isi).baris.map((b) => b.id_klien);
  assert.deepEqual(a, b);
  assert.notEqual(a[0], a[1]);
  assert.match(a[0], /^u[0-9a-f]{16}$/);
  assert.equal(petakanHarga("tanggal,kode_pasar,kode_varian,harga,id_klien\n2026-10-01,PSR01,CMR01,1,abc\n").baris[0].id_klien, "abc");
});

test("berkas dengan data pribadi atau tanpa kolom wajib ditolak utuh", () => {
  assert.match(petakanHarga("tanggal,kode_pasar,kode_varian,harga,No HP\n", { terlarang: ["no_hp"] }).galatBerkas, /data pribadi \(no_hp\)/);
  assert.match(petakanHarga("tanggal,pasar,harga\n2026-10-01,PSR01,1\n").galatBerkas, /kode_varian/);
  assert.match(petakanHarga("").galatBerkas, /kosong/);
});

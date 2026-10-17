// Istilah teknis tidak boleh tampil di lapis depan halaman umum (masyarakat, TPID, peringatan). Istilah itu tetap boleh
// ada di rincian (jendela, tooltip "title", bagian <details>) dan di Kamus Data, tempat artinya dijelaskan.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { ringkasHariIni } from "../site/assets/selisih.js";

export const ISTILAH_TEKNIS = /\b(s?MAPE|F1(-score)?|recall|precision|quality gate|ensemble|z-?score|baseline|drift|conformal|Ridge|Holt|SES|false alarm|uptime)\b/i;

/** Teks yang terlihat dari markup HTML statis: tanpa <script>, <style>, komentar, isi <details>, dan atribut. */
function teksTerlihat(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<details[\s\S]*?<\/details>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ");
}

for (const halaman of ["index.html", "harga.html", "sinyal.html", "laporan.html"]) {
  test(`${halaman}: teks yang terlihat tanpa istilah teknis`, () => {
    const teks = teksTerlihat(readFileSync(new URL(`../site/${halaman}`, import.meta.url), "utf-8"));
    const m = teks.match(ISTILAH_TEKNIS);
    assert.equal(m, null, m ? `"${m[0]}" di: …${teks.slice(Math.max(0, m.index - 60), m.index + 40)}…` : "");
  });
}

test("label ubin mutu dan indikator Dasbor TPID memakai kata sehari-hari", () => {
  const sumber = readFileSync(new URL("../site/assets/dashboard.js", import.meta.url), "utf-8");
  for (const [, nama] of sumber.matchAll(/nama: "([^"]+)", arti:/g)) assert.doesNotMatch(nama, ISTILAH_TEKNIS, nama);
  const index = readFileSync(new URL("../site/index.html", import.meta.url), "utf-8");
  for (const [, label, sub] of index.matchAll(/kartuKpi\("[^"]+", "[^"]+", "[^"]+", [^,]+(?:\([^)]*\))?[^,]*, "([^"]+)", ([^\n]+)\),/g)) {
    assert.doesNotMatch(`${label} ${sub}`, ISTILAH_TEKNIS, label);
  }
});

test("kalimat ringkas beranda tanpa istilah teknis", () => {
  const v = { nama: "Cabai Rawit Hijau", satuan: "kg", harga_terakhir: 80000, harga_acuan: { bulanan: { harga: 55000, tanggal: "2026-09-16" } },
    perubahan: { bulanan: 45.5 } };
  assert.doesNotMatch(ringkasHariIni([v], "bulanan").kalimat, ISTILAH_TEKNIS);
});

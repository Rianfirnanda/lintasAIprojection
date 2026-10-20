// Pencatat galat di perangkat pengguna: ringkas, saring galat yang bukan dari situs, dan kelompokkan untuk Administrator.
import assert from "node:assert/strict";
import test from "node:test";
import { abaikan, kelompokkanGalat, namaPeramban, ringkasGalat, sidikGalat } from "../site/assets/galat-klien.js";

const ASAL = "https://takar.web.app";

test("galat diringkas tanpa alamat situs dan dibatasi panjangnya", () => {
  const err = new TypeError("x is not a function");
  err.stack = `TypeError: x is not a function\n    at gambar (${ASAL}/assets/app.js:10:5)`;
  const g = ringkasGalat({ type: "error", error: err, filename: `${ASAL}/assets/app.js`, lineno: 10, colno: 5 }, ASAL);
  assert.deepEqual(g, { pesan: "x is not a function", sumber: "/assets/app.js:10:5",
    tumpukan: "TypeError: x is not a function\n    at gambar (/assets/app.js:10:5)", jenis: "galat" });
  const j = ringkasGalat({ type: "unhandledrejection", reason: "a".repeat(500) }, ASAL);
  assert.equal(j.jenis, "janji");
  assert.equal(j.pesan.length, 300);
  assert.equal(sidikGalat(g), "x is not a function|/assets/app.js:10:5");
});

test("galat dari ekstensi, skrip luar, dan gangguan jaringan tidak dicatat", () => {
  const g = (pesan, sumber = "", tumpukan = "") => ({ pesan, sumber, tumpukan });
  assert.equal(abaikan(g("Script error.")), true);
  assert.equal(abaikan(g("ResizeObserver loop completed with undelivered notifications.")), true);
  assert.equal(abaikan(g("boom", "chrome-extension://abc/x.js:1:1")), true);
  assert.equal(abaikan(g("Failed to fetch")), true);
  assert.equal(abaikan(g("")), true);
  assert.equal(abaikan(g("Cannot read properties of undefined (reading 'harga')", "/harga.html:120:9")), false);
});

test("nama peramban mudah dibaca dan galat yang sama dikelompokkan", () => {
  const android = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36";
  const iphone = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1";
  assert.equal(namaPeramban(android), "Chrome, Android");
  assert.equal(namaPeramban(iphone), "Safari, iOS");
  assert.equal(namaPeramban("Mozilla/5.0 (Linux; Android 13) SamsungBrowser/25.0 Chrome/121.0"), "Samsung Internet, Android");
  const c = (id, uid, waktu, ekstra = {}) => ({ id, uid, peran: "masyarakat", halaman: "harga.html", pesan: "a", sumber: "/x.js:1:1",
    tumpukan: "", peramban: android, waktu: new Date(waktu), ...ekstra });
  const grup = kelompokkanGalat([c("1", "u1", "2026-10-20T01:00:00Z"), c("2", "u2", "2026-10-20T03:00:00Z", { peramban: iphone }),
    c("3", "u1", "2026-10-20T02:00:00Z", { pesan: "b" })]);
  assert.equal(grup.length, 2);
  assert.equal(grup[0].pesan, "a");
  assert.equal(grup[0].jumlah, 2);
  assert.equal(grup[0].pengguna.size, 2);
  assert.deepEqual([...grup[0].peramban], ["Chrome, Android", "Safari, iOS"]);
  assert.deepEqual(grup[0].id, ["1", "2"]);
});

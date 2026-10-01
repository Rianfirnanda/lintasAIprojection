// Uji enkripsi sealed box. Vektor di bawah dibuat dengan libsodium (crypto_box_seal dan primitifnya),
// jadi lulus di sini berarti hasil kita bisa dibuka GitHub dan sebaliknya.
import assert from "node:assert/strict";
import test from "node:test";
import { segel, bukaSegel, buatPasangan } from "../site/vendor/sealedbox/sealedbox.js";

const heks = (h) => Uint8Array.from(h.match(/../g).map((x) => parseInt(x, 16)));
const ke = (u) => Buffer.from(u).toString("hex");
const KAT = {
  "kunciPublikPenerima": "761d88ec830413919dfe9d4d1d56f17e653c8c994082df5b137b90a0ae6edf74",
  "kunciRahasiaPenerima": "2fad39fefd7fa3e200a9c626eef599e61a2d055c48a8288a4e7e4c4bca3928f8",
  "kunciRahasiaSementara": "3e8fe3ab30c0aabf54acd276f3d8bbbc2b7ca4a9495d204f255bacf578c74c86",
  "pesan": "kunci-rahasia-contoh-123",
  "paketDeterministik": "ede2393fe2defd0ff703799841c699b03fd634a9b9c411ed760df7bce5d5c26717fb2c9b01253ead7f241a24b0d47da43a5fd564ede2196a9f05048034add15b688ef98ba608edfc",
  "paketAsliLibsodium": "7b9caa236ede82b7adf9ce5fb01a2a986cc147998041412be9f6ec7eb6032830375a8d522768d271d341c6926648ce2d53003436a28f10cc5086466ae3834566218be0d77a4de1a0"
};

test("segel dengan kunci sementara tetap menghasilkan paket yang sama dengan libsodium", () => {
  const paket = segel(new TextEncoder().encode(KAT.pesan), heks(KAT.kunciPublikPenerima), heks(KAT.kunciRahasiaSementara));
  assert.equal(ke(paket), KAT.paketDeterministik);
});

test("paket asli dari crypto_box_seal libsodium bisa dibuka", () => {
  const buka = bukaSegel(heks(KAT.paketAsliLibsodium), heks(KAT.kunciPublikPenerima), heks(KAT.kunciRahasiaPenerima));
  assert.equal(new TextDecoder().decode(buka), KAT.pesan);
});

test("segel acak: bisa dibuka pemilik kunci, panjang sesuai, dan tiap segel berbeda", () => {
  const pasangan = buatPasangan();
  const pesan = new TextEncoder().encode("AIzaSyContohKunciGemini_1234567890");
  const a = segel(pesan, pasangan.publicKey);
  const b = segel(pesan, pasangan.publicKey);
  assert.equal(a.length, pesan.length + 48);
  assert.notEqual(ke(a), ke(b));
  assert.deepEqual(bukaSegel(a, pasangan.publicKey, pasangan.secretKey), pesan);
});

test("kunci yang salah atau paket yang diubah tidak bisa dibuka", () => {
  const pemilik = buatPasangan();
  const lain = buatPasangan();
  const paket = segel(new TextEncoder().encode("rahasia"), pemilik.publicKey);
  assert.equal(bukaSegel(paket, lain.publicKey, lain.secretKey), null);
  const rusak = paket.slice();
  rusak[40] ^= 1;
  assert.equal(bukaSegel(rusak, pemilik.publicKey, pemilik.secretKey), null);
});

test("kunci publik penerima harus 32 byte", () => {
  assert.throws(() => segel(new Uint8Array([1]), new Uint8Array(5)), /32 byte/);
});

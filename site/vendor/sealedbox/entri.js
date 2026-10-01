// Titik masuk untuk membuat sealedbox.js (lihat README.md di folder ini).
// Sama dengan crypto_box_seal milik libsodium, yang dipakai GitHub untuk mengenkripsi nilai GitHub Secrets:
//   nonce = BLAKE2b-24(kunciPublikSementara || kunciPublikPenerima)
//   hasil = kunciPublikSementara || crypto_box(pesan, nonce, kunciPublikPenerima, kunciRahasiaSementara)
import nacl from "tweetnacl";
import { blake2b } from "blakejs";

const gabung = (a, b) => {
  const hasil = new Uint8Array(a.length + b.length);
  hasil.set(a, 0);
  hasil.set(b, a.length);
  return hasil;
};

/** Mengunci `pesan` (Uint8Array) agar hanya pemilik kunci rahasia penerima yang bisa membukanya. */
export function segel(pesan, kunciPublikPenerima, kunciRahasiaSementara = globalThis.crypto.getRandomValues(new Uint8Array(32))) {
  if (kunciPublikPenerima.length !== nacl.box.publicKeyLength) throw new Error("Kunci publik penerima harus 32 byte");
  const sementara = nacl.box.keyPair.fromSecretKey(kunciRahasiaSementara);
  const nonce = blake2b(gabung(sementara.publicKey, kunciPublikPenerima), null, nacl.box.nonceLength);
  const tertutup = nacl.box(pesan, nonce, kunciPublikPenerima, sementara.secretKey);
  return gabung(sementara.publicKey, tertutup);
}

/** Kebalikan segel(); dipakai untuk pengujian. Mengembalikan null bila gagal dibuka. */
export function bukaSegel(paket, kunciPublikPenerima, kunciRahasiaPenerima) {
  const publikSementara = paket.slice(0, nacl.box.publicKeyLength);
  const nonce = blake2b(gabung(publikSementara, kunciPublikPenerima), null, nacl.box.nonceLength);
  return nacl.box.open(paket.slice(nacl.box.publicKeyLength), nonce, publikSementara, kunciRahasiaPenerima);
}

/** Pasangan kunci baru (untuk pengujian). Memakai crypto.getRandomValues, sama seperti segel(). */
export const buatPasangan = () => nacl.box.keyPair.fromSecretKey(globalThis.crypto.getRandomValues(new Uint8Array(32)));

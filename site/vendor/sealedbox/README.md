# sealedbox

Enkripsi "sealed box" (sama dengan `crypto_box_seal` milik libsodium) yang dipakai GitHub untuk nilai GitHub Secrets.
Dipakai oleh panel admin (`site/pengaturan.html`) supaya kunci API dienkripsi di browser sebelum dikirim ke GitHub,
tanpa memuat skrip dari CDN.

Isi folder:

- `entri.js`: kode sumber (dua fungsi kecil, `segel` dan `bukaSegel`).
- `sealedbox.js`: hasil bundel yang dimuat halaman. Memuat `tweetnacl` 1.0.3 dan `blakejs` 1.2.1.
- `crypto-kosong.js`: pengganti modul `crypto` milik Node saat membundel (pustaka tidak memakainya di browser).
- `LICENSE.md`: lisensi kedua pustaka.

Membuat ulang `sealedbox.js` (butuh Node):

```bash
mkdir /tmp/bundel && cd /tmp/bundel
npm init -y && npm install tweetnacl@1.0.3 blakejs@1.2.1 esbuild
cp <repo>/site/vendor/sealedbox/{entri.js,crypto-kosong.js} .
npx esbuild entri.js --bundle --format=esm --minify --legal-comments=inline \
  --alias:crypto=./crypto-kosong.js --outfile=sealedbox.js
```

Hasil bundel sudah diuji silang dengan libsodium di dua arah (segel kita dibuka libsodium, segel libsodium dibuka kita):
lihat `tests_js/sealedbox.test.mjs`.

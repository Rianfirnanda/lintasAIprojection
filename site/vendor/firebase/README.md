# Firebase JS SDK (bundel)

Bundel ESM dari paket npm `firebase` versi 11.10.0 (Apache License 2.0, lisensi tercantum di akhir tiap berkas). Disimpan
di repositori supaya situs tidak bergantung pada CDN. Hanya fungsi yang diekspor berkas entri yang ikut.

| Berkas | Entri | Isi | Dimuat |
| --- | --- | --- | --- |
| `firebase.js` | `entri.js` | login, Firestore | setiap halaman bila login Firebase |
| `firebase-ai.js` | `entri-ai.js` | AI Logic (Gemini) dan App Check | hanya saat Tanya Takar memakai AI |
| `firebase-bersama.js` | (otomatis) | inti Firebase yang dipakai keduanya | otomatis oleh kedua berkas di atas |

Keduanya harus dibangun bersama dengan `--splitting`, supaya inti Firebase hanya ada satu salinan. Kalau dibangun
terpisah, AI tidak mengenali aplikasi yang dibuat `firebase.js`.

Bangun ulang:

```bash
npm install firebase@11.10.0 esbuild
npx esbuild firebase=site/vendor/firebase/entri.js firebase-ai=site/vendor/firebase/entri-ai.js --bundle --splitting \
  --format=esm --minify --target=es2020 --legal-comments=eof --chunk-names=firebase-bersama \
  --outdir=site/vendor/firebase
```

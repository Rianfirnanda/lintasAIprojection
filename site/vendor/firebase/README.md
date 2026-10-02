# Firebase JS SDK (bundel)

`firebase.js` adalah bundel ESM dari paket npm `firebase` versi 11.10.0 (Apache License 2.0, lisensi tercantum di
akhir berkas), berisi hanya fungsi yang diekspor `entri.js`. Disimpan di repositori supaya situs tidak bergantung
pada CDN.

Bangun ulang:

```bash
npm install firebase@11.10.0 esbuild
npx esbuild site/vendor/firebase/entri.js --bundle --format=esm --minify --target=es2020 \
  --legal-comments=eof --outfile=site/vendor/firebase/firebase.js
```

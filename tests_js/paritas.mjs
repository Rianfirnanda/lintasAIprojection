// Dipanggil oleh tests/test_pengaturan_js.py: membaca { skema, dasar, kasus } dari berkas JSON (argumen pertama)
// dan mencetak, untuk tiap kasus, daftar jalur yang ditandai salah oleh validator JavaScript.
import { readFileSync } from "node:fs";
import { atur, periksa, salin } from "../site/assets/pengaturan-inti.js";

const { skema, dasar, kasus } = JSON.parse(readFileSync(process.argv[2], "utf-8"));
const hasil = kasus.map((ubah) => {
  const p = salin(dasar);
  for (const [jalur, nilai] of Object.entries(ubah)) atur(p, jalur, nilai);
  return [...new Set(periksa(p, skema).map((m) => m.jalur))].sort();
});
console.log(JSON.stringify(hasil));

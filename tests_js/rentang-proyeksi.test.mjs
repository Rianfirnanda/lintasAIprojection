import test from 'node:test';
import assert from 'node:assert/strict';
import { selRentang, hargaHariIni } from '../site/assets/rentang-proyeksi.js';
test('setiap horizon menampilkan prediksi dan kedua batas, termasuk rentang nol', () => {
  for (const p of [{prediksi:12000,bawah:11000,atas:14000},{prediksi:12000,bawah:12000,atas:12000}]) {
    assert.match(selRentang(p), /12\.000/);
    assert.match(selRentang(p), /sampai/);
  }
  assert.match(selRentang(null), /Belum tersedia/);
  assert.match(selRentang({prediksi:NaN,bawah:0,atas:1}), /Belum tersedia/);
});
test('hari ini memakai tanggal kalender dan tidak menyebut observasi sebagai prediksi', () => {
  const v = {tanggal_aktual:'2026-11-11',harga_aktual:12000};
  assert.equal(hargaHariIni(v,'2026-11-11','2026-11-11',()=>null).tercatat,true);
  const p = {prediksi:12500,bawah:11000,atas:14000};
  assert.deepEqual(hargaHariIni(v,'2026-11-12','2026-11-11',(_,h)=> h===1?p:null),p);
  assert.equal(hargaHariIni(v,'2026-12-31','2026-11-11',()=>null),null);
});

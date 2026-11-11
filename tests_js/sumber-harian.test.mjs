import test from 'node:test';
import assert from 'node:assert/strict';
import { pilihTanggal } from '../site/assets/sumber-harian-data.js';

const riwayat = [
  { sumber: 'SP2KP', tanggal: '2026-11-11', harga: 15000, status: 'Lolos pemeriksaan', riwayat: [
    ['2026-11-09', 12000, 'Ada data tidak dipakai'], ['2026-11-11', 15000, 'Lolos pemeriksaan']] },
  { sumber: 'PIHPS', riwayat: [['2026-11-09', 13000, 'Data konteks pembanding']] },
];
test('tanggal pilihan memakai harga dan status historis kedua sumber', () => {
  const baris = pilihTanggal(riwayat, '2026-11-09');
  assert.deepEqual(baris.map(b => [b.sumber, b.tanggal, b.harga, b.status]), [
    ['SP2KP', '2026-11-09', 12000, 'Ada data tidak dipakai'],
    ['PIHPS', '2026-11-09', 13000, 'Data konteks pembanding'],
  ]);
  assert.equal(riwayat[0].harga, 15000);
});
test('tanggal tanpa laporan tidak diisi dengan harga hari lain', () => {
  assert.deepEqual(pilihTanggal(riwayat, '2026-11-10'), []);
  assert.deepEqual(pilihTanggal(riwayat, '2026-11-11').map(b => b.sumber), ['SP2KP']);
  assert.deepEqual(pilihTanggal([], '2026-11-11'), []);
});

test('pilihan tanggal memuat riwayat sekali dan tombol terbaru memulihkan tabel', async () => {
  globalThis.addEventListener = () => {};
  globalThis.window = { addEventListener() {} };
  globalThis.document = { documentElement: { dataset: {}, classList: { add() {} } }, addEventListener() {} };
  globalThis.matchMedia = () => ({ addEventListener() {} });
  const { tampilkanSumberHarian } = await import('../site/assets/sumber-harian.js');
  const elemen = Object.fromEntries(['[data-tanggal]', '[data-status]', '[data-tabel]', '[data-terbaru]'].map(k =>
    [k, { value: '', innerHTML: '', textContent: '', handlers: {}, addEventListener(e, cb) { this.handlers[e] = cb; } }]));
  const target = { querySelector: k => elemen[k] };
  let muat = 0;
  tampilkanSumberHarian(target, [{ sumber: 'SP2KP', tanggal: '2026-11-11', harga: 15000 }], async () => { muat++; return riwayat; });
  const input = elemen['[data-tanggal]'], tabel = elemen['[data-tabel]'];
  input.value = '2026-11-09'; await input.handlers.change();
  assert.match(tabel.innerHTML, /PIHPS/);
  assert.match(tabel.innerHTML, /12[.,]000/);
  input.value = '2026-11-10'; await input.handlers.change();
  assert.match(tabel.innerHTML, /Tidak ada laporan harga/);
  assert.equal(muat, 1);
  elemen['[data-terbaru]'].handlers.click();
  assert.equal(input.value, '');
  assert.match(tabel.innerHTML, /terakhir yang tersedia/);
});

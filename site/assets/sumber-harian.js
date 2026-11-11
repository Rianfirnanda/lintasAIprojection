import { pilihTanggal } from "./sumber-harian-data.js";
import { esc, rp, tgl, angka, muatJSON } from './app.js';

function isiTabel(target, baris = [], tanggal = "") {
  target.innerHTML = `<p class="meta-kecil">${angka(baris.length)} deret harga ${tanggal ? `pada ${esc(tgl(tanggal))}` : "terakhir yang tersedia"} per sumber, pasar atau wilayah, dan varian. ${tanggal ? "Hanya data tepat pada tanggal pilihan yang ditampilkan; tanggal tanpa laporan tidak diisi dengan harga hari lain." : "Tanggal data dapat berbeda antar sumber."} Harga ditampilkan sesuai laporan sumber; data yang tidak lolos pemeriksaan tidak digunakan dalam analisis.</p>
    <div class="gulir-tabel" style="max-height:420px"><table><thead><tr>
    <th>Sumber</th><th>Pasar / wilayah</th><th>Varian</th><th>Tanggal data</th><th class="angka">Harga harian</th><th>Peran data</th><th>Pemeriksaan</th>
    </tr></thead><tbody>${baris.map(b => `<tr>
    <td>${/^https:\/\//.test(b.url) ? `<a href="${esc(b.url)}" target="_blank" rel="noopener noreferrer">${esc(b.sumber)}</a>` : esc(b.sumber)}</td>
    <td>${esc(b.pasar)}</td><td>${esc(b.varian)}</td><td>${esc(tgl(b.tanggal))}</td>
    <td class="angka">${rp(b.harga)}<div class="meta-kecil">per ${esc(b.satuan)}</div></td>
    <td>${esc(b.peran)}</td><td>${esc(b.status)}</td></tr>`).join('') || '<tr><td colspan="7" class="kosong">Tidak ada laporan harga untuk pilihan ini. Pilih tanggal lain atau tampilkan data terbaru.</td></tr>'}</tbody></table></div>`;
}



export function tampilkanSumberHarian(target, baris = [], muat = muatJSON) {
  target.innerHTML = `<div class="baris-kontrol" style="margin-bottom:12px">
    <label>Pilih tanggal <input type="date" data-tanggal aria-label="Tanggal data harga harian"></label>
    <button type="button" class="tombol kecil" data-terbaru>Data terbaru</button>
    </div><p class="meta-kecil" role="status" aria-live="polite" data-status></p><div data-tabel></div>`;
  const input = target.querySelector('[data-tanggal]');
  const status = target.querySelector('[data-status]');
  const tabel = target.querySelector('[data-tabel]');
  let riwayat, versi = 0;
  isiTabel(tabel, baris);
  async function perbarui() {
    const tanggal = input.value;
    const kini = ++versi;
    status.textContent = '';
    if (!tanggal) { isiTabel(tabel, baris); return; }
    tabel.innerHTML = '';
    status.textContent = 'Memuat data tanggal pilihan…';
    try {
      riwayat ||= await muat('sumber_harian_riwayat.json');
      if (kini !== versi) return;
      isiTabel(tabel, pilihTanggal(riwayat, tanggal), tanggal);
      status.textContent = '';
    } catch {
      if (kini === versi) status.textContent = 'Riwayat harga belum dapat dimuat. Silakan pilih tanggal lagi atau tampilkan data terbaru.';
    }
  }
  input.addEventListener('change', perbarui);
  target.querySelector('[data-terbaru]').addEventListener('click', () => { input.value = ''; perbarui(); });
}

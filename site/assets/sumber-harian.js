import { esc, rp, tgl, angka } from './app.js';

export function tampilkanSumberHarian(target, baris = []) {
  target.innerHTML = `<p class="meta-kecil">${angka(baris.length)} deret harga terakhir yang tersedia per sumber, pasar atau wilayah, dan varian. Tanggal data dapat berbeda antar sumber. Harga ditampilkan sesuai laporan sumber; data yang tidak lolos pemeriksaan tidak digunakan dalam analisis.</p>
    <div class="gulir-tabel" style="max-height:420px"><table><thead><tr>
    <th>Sumber</th><th>Pasar / wilayah</th><th>Varian</th><th>Tanggal data</th><th class="angka">Harga harian</th><th>Peran data</th><th>Pemeriksaan</th>
    </tr></thead><tbody>${baris.map(b => `<tr>
    <td>${/^https:\/\//.test(b.url) ? `<a href="${esc(b.url)}" target="_blank" rel="noopener noreferrer">${esc(b.sumber)}</a>` : esc(b.sumber)}</td>
    <td>${esc(b.pasar)}</td><td>${esc(b.varian)}</td><td>${esc(tgl(b.tanggal))}</td>
    <td class="angka">${rp(b.harga)}<div class="meta-kecil">per ${esc(b.satuan)}</div></td>
    <td>${esc(b.peran)}</td><td>${esc(b.status)}</td></tr>`).join('') || '<tr><td colspan="7" class="kosong">Data harian SP2KP dan PIHPS belum tersedia pada hasil pengolahan ini.</td></tr>'}</tbody></table></div>`;
}

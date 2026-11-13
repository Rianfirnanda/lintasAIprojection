const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
export const NAMA_TRUST_CABAI = { belum_cukup_bukti: 'Belum cukup bukti', rendah: 'Rendah', sedang: 'Sedang', tinggi: 'Tinggi' };
const warna = { belum_cukup_bukti: 'polos', rendah: 'sedang', sedang: 'info', tinggi: 'baik' };
const nama = level => NAMA_TRUST_CABAI[level] || NAMA_TRUST_CABAI.belum_cukup_bukti;
const lencana = level => `<span class="lencana ${warna[level] || 'polos'}">${nama(level)}</span>`;
const nilai = value => value == null ? 'Belum dinilai' : typeof value === 'number'
  ? value.toLocaleString('id-ID', { maximumFractionDigits: 2 })
  : escapeHtml(typeof value === 'object' ? JSON.stringify(value) : value);

export function selTrustCabai(trust) {
  if (!trust?.per_horizon) return '<span class="meta-kecil">-</span>';
  return `<div class="dsb-trust" title="Trust harga dan rentang setelah tanggal data. Level bukan probabilitas prediksi benar.">${[1,7,30].map(h => {
    const item = trust.per_horizon[String(h)];
    const alasan = [...(item?.gagal || []), ...(item?.belum_dinilai || [])].join('; ');
    return `<span class="dsb-trust-baris" title="${escapeHtml(alasan || 'Lihat rincian pengujian')}"><span>H+${h}</span>${lencana(item?.level)}</span>`;
  }).join('')}</div>`;
}

function syarat(list) {
  return (list || []).map(s => `<tr><td>${escapeHtml(s.syarat)}</td><td>${nilai(s.nilai)}</td><td>${nilai(s.target)}</td><td>${s.lolos === true ? 'Lolos' : s.lolos === false ? 'Gagal' : 'Belum cukup bukti'}</td></tr>`).join('');
}

export function rincianTrustCabai(trust) {
  if (!trust?.per_horizon) return '';
  const scope = trust.sumber;
  return `<details class="dsb-trust-rincian"><summary>Trust khusus cabai per horizon</summary>
    <p>Harga dan rentang dinilai terpisah dari arah. Kriteria ini berjalan berdampingan dengan uji umum; level bukan probabilitas.</p>
    ${trust.ambang_belum_tervalidasi ? '<p class="meta-kecil">Kriteria awal sedang dievaluasi. Level ini belum menjadi standar akurasi yang tervalidasi pada data baru.</p>' : ''}
    <p class="meta-kecil">Versi ${escapeHtml(trust.versi)}. Dinilai ${escapeHtml(trust.tanggal_penilaian)}${scope?.kode_wilayah ? `; wilayah ${escapeHtml(scope.kode_wilayah)}, sumber ${escapeHtml(scope.kode_sumber || 'belum layak')}` : ''}.
    Level tinggi memerlukan bukti ramalan terbit yang sudah mempunyai harga aktual.</p>
    <div class="gulir-tabel"><table class="tabel-kecil"><thead><tr><th>Horizon</th><th>Harga dan rentang</th><th>Arah</th><th>sMAPE (%)</th><th>Bias (%)</th><th>Origin tidak bertumpang tindih</th></tr></thead>
    <tbody>${[1,7,30].map(h => { const x = trust.per_horizon[String(h)], m = x?.metrik?.[x?.level === 'tinggi' ? 'tinggi' : 'sedang'];
      return `<tr><td>${h} hari</td><td>${lencana(x?.level)}</td><td>${lencana(x?.arah?.level)}</td><td>${nilai(m?.smape)}</td><td>${nilai(m?.bias)}</td><td>${nilai(m?.n)}</td></tr>`;
    }).join('')}</tbody></table></div>
    ${[1,7,30].map(h => { const x = trust.per_horizon[String(h)];
      return `<details><summary>Alasan penilaian ${h} hari</summary>${['sedang','tinggi'].map(level => `<h4>Gerbang ${nama(level)}</h4>
      <div class="gulir-tabel"><table class="tabel-kecil"><thead><tr><th>Syarat harga dan rentang</th><th>Hasil</th><th>Target</th><th>Status</th></tr></thead><tbody>${syarat(x?.syarat?.[level])}</tbody></table></div>
      <p class="meta-kecil">Dasar arah: ${x?.arah?.basis?.[level] === 'ramalan_terbit_prospektif' ? 'arsip ramalan yang benar-benar diterbitkan' : 'uji historis'}.</p>
      <div class="gulir-tabel"><table class="tabel-kecil"><thead><tr><th>Syarat arah</th><th>Hasil</th><th>Target</th><th>Status</th></tr></thead><tbody>${syarat(x?.arah?.syarat?.[level])}</tbody></table></div>`).join('')}</details>`;
    }).join('')}</details>`;
}

export function kolomTrustCabai(trust) {
  const result = { versi_trust_cabai: trust?.versi || '' };
  for (const h of [1,7,30]) {
    result[`trust_cabai_${h}`] = trust?.per_horizon?.[String(h)]?.level || '';
    result[`trust_arah_cabai_${h}`] = trust?.per_horizon?.[String(h)]?.arah?.level || '';
  }
  return result;
}

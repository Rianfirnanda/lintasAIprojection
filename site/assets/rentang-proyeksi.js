const angka = x => Math.round(x).toLocaleString('id-ID');
export function selRentang(p) {
  if (!p || ![p.prediksi, p.bawah, p.atas].every(Number.isFinite)) return '<span class="menunggu">Belum tersedia</span>';
  return `<strong>${angka(p.prediksi)}</strong><div class="dsb-interval">${angka(p.bawah)} sampai ${angka(p.atas)}</div>`;
}

export function hargaHariIni(v, tanggal, asal, proyeksi) {
  if (v.tanggal_aktual === tanggal && Number.isFinite(v.harga_aktual))
    return { prediksi: v.harga_aktual, bawah: v.harga_aktual, atas: v.harga_aktual, tercatat: true };
  const h = Math.round((Date.parse(tanggal + 'T00:00:00Z') - Date.parse(asal + 'T00:00:00Z')) / 86400000);
  return h > 0 ? proyeksi(v, h) : null;
}

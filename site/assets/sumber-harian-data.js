export function pilihTanggal(riwayat, tanggal) {
  return riwayat.flatMap(({ riwayat: nilai = [], ...baris }) => {
    const data = nilai.find(([t]) => t === tanggal);
    return data ? [{ ...baris, tanggal: data[0], harga: data[1], status: data[2] }] : [];
  });
}

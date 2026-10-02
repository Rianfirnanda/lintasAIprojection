// Membaca berkas CSV harga di browser (untuk unggahan operator lewat situs). Aturannya mengikuti pipeline/masukan.py:
// nama kolom boleh beragam (alias), tanggal boleh 2026-10-01 atau 01/10/2026, harga boleh "Rp 45.000".
// Pemeriksaan lengkap tetap dilakukan mesin pengolah; di sini hanya yang perlu supaya kiriman bisa disimpan.
// Murni tanpa DOM, supaya bisa diuji dengan Node.

export const ALIAS_HARGA = {
  tanggal: ["tanggal", "tgl", "date", "tanggal_pencatatan"],
  kode_pasar: ["kode_pasar", "pasar", "market"],
  kode_varian: ["kode_varian", "varian", "kode_komoditas_varian", "kode_barang"],
  harga: ["harga", "harga_rp", "price", "harga_eceran"],
  satuan: ["satuan", "unit"],
  kode_sumber: ["kode_sumber", "sumber"],
  petugas: ["petugas", "kode_petugas", "pencacah"],
  responden: ["responden", "kode_responden"],
  catatan: ["catatan", "keterangan", "notes"],
  id_klien: ["id_klien", "uuid", "client_id"],
  waktu_input: ["waktu_input", "waktu_isi", "timestamp"],
};
const WAJIB = ["tanggal", "kode_pasar", "kode_varian", "harga"];
export const MAKS_BARIS = 3000;

export const normalisasiKolom = (nama) => String(nama ?? "").trim().toLowerCase().replace(/^﻿/, "").replace(/[\s\-.]+/g, "_");

/** CSV menjadi larik baris (larik teks). Mendukung tanda kutip, koma atau titik koma (Excel Indonesia). */
export function bacaCSV(teks) {
  const t = String(teks).replace(/^﻿/, "");
  const barisPertama = t.split(/\r?\n/, 1)[0] || "";
  const pemisah = (barisPertama.match(/;/g) || []).length > (barisPertama.match(/,/g) || []).length ? ";" : ",";
  const hasil = [];
  let baris = [], sel = "", kutip = false;
  for (let i = 0; i < t.length; i++) {
    const c = t[i];
    if (kutip) {
      if (c === '"' && t[i + 1] === '"') { sel += '"'; i++; } else if (c === '"') kutip = false; else sel += c;
    } else if (c === '"') kutip = true;
    else if (c === pemisah) { baris.push(sel); sel = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && t[i + 1] === "\n") i++;
      baris.push(sel); hasil.push(baris); baris = []; sel = "";
    } else sel += c;
  }
  if (sel !== "" || baris.length) { baris.push(sel); hasil.push(baris); }
  return hasil.filter((b) => b.some((x) => x.trim() !== ""));
}

/** Sidik pendek dan tetap dari teks (dua FNV-1a 32 bit). Baris yang sama selalu mendapat ID yang sama. */
export function sidik(teks) {
  let a = 0x811c9dc5, b = 0x01000193 ^ 0x5bd1e995;
  for (let i = 0; i < teks.length; i++) {
    const c = teks.charCodeAt(i);
    a = Math.imul(a ^ c, 0x01000193) >>> 0;
    b = Math.imul(b ^ c, 0x01000193 + 2) >>> 0;
  }
  return a.toString(16).padStart(8, "0") + b.toString(16).padStart(8, "0");
}

const dua = (n) => String(n).padStart(2, "0");

/** "2026-10-01", "01/10/2026", "1-10-2026", "01.10.2026", "2026/10/01" menjadi "2026-10-01"; null bila tidak dikenali. */
export function tanggalISO(teks) {
  const s = String(teks ?? "").trim();
  let m = s.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/);
  let y, bln, h;
  if (m) [, y, bln, h] = m;
  else if ((m = s.match(/^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$/))) [, h, bln, y] = m;
  else return null;
  const d = new Date(Date.UTC(+y, +bln - 1, +h));
  if (d.getUTCFullYear() !== +y || d.getUTCMonth() !== +bln - 1 || d.getUTCDate() !== +h) return null;
  return `${y}-${dua(bln)}-${dua(h)}`;
}

/** "Rp 45.000", "45.000", "12.500,50", "45000" menjadi angka; null bila tidak sah. Sama dengan parse_harga di Python. */
export function angkaHarga(nilai) {
  let t = String(nilai ?? "").trim().toLowerCase().replace(/rp/g, "").replace(/\s/g, "");
  if (!t) return null;
  if (t.includes(".") && t.includes(",")) t = t.replace(/\./g, "").replace(",", ".");
  else if (/^\d{1,3}(\.\d{3})+$/.test(t)) t = t.replace(/\./g, "");
  else if (/^\d{1,3}(,\d{3})+$/.test(t)) t = t.replace(/,/g, "");
  else if (t.includes(",")) t = t.replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(t)) return null;
  const n = Number(t);
  return n > 0 && n < 1e8 ? n : null;
}

/**
 * Isi berkas CSV harga menjadi baris siap kirim.
 * Hasil: { baris: [...], galat: [{ baris, alasan }], galatBerkas: "" }. `baris` memakai nama kolom templat.
 * Baris tanpa id_klien mendapat ID dari isinya sendiri, jadi berkas yang sama aman diunggah dua kali: tidak menjadi ganda.
 */
export function petakanHarga(teks, { terlarang = [] } = {}) {
  const tabel = bacaCSV(teks);
  if (!tabel.length) return { baris: [], galat: [], galatBerkas: "Berkas kosong." };
  const kepala = tabel[0].map(normalisasiKolom);
  const kena = kepala.filter((k) => terlarang.includes(k));
  if (kena.length) {
    return { baris: [], galat: [], galatBerkas: `Berkas memuat kolom data pribadi (${[...new Set(kena)].join(", ")}). Hapus kolom itu dulu; pakai kode pedagang anonim.` };
  }
  const indeks = {};
  for (const [kunci, alias] of Object.entries(ALIAS_HARGA)) {
    const i = kepala.findIndex((k) => alias.includes(k));
    if (i >= 0) indeks[kunci] = i;
  }
  const kurang = WAJIB.filter((k) => !(k in indeks));
  if (kurang.length) return { baris: [], galat: [], galatBerkas: `Kolom wajib tidak ditemukan: ${kurang.join(", ")}.` };
  if (tabel.length - 1 > MAKS_BARIS) {
    return { baris: [], galat: [], galatBerkas: `Berkas berisi ${tabel.length - 1} baris. Paling banyak ${MAKS_BARIS} baris sekali unggah; bagi dulu menjadi beberapa berkas.` };
  }
  const ambil = (b, k) => (k in indeks ? String(b[indeks[k]] ?? "").trim() : "");
  const baris = [];
  const galat = [];
  const idDipakai = new Set();
  tabel.slice(1).forEach((b, i) => {
    const nomor = i + 2;
    const tanggal = tanggalISO(ambil(b, "tanggal"));
    const harga = angkaHarga(ambil(b, "harga"));
    const kodePasar = ambil(b, "kode_pasar").toUpperCase();
    const kodeVarian = ambil(b, "kode_varian").toUpperCase();
    const alasan = !tanggal ? "tanggal kosong atau formatnya tidak dikenali"
      : !kodePasar ? "kode pasar kosong" : !kodeVarian ? "kode varian kosong"
        : harga === null ? "harga kosong atau bukan angka" : "";
    if (alasan) { galat.push({ baris: nomor, alasan }); return; }
    const isi = {
      tanggal, kode_pasar: kodePasar.slice(0, 30), kode_varian: kodeVarian.slice(0, 30), harga,
      satuan: ambil(b, "satuan").toLowerCase().slice(0, 20), kode_sumber: ambil(b, "kode_sumber").toUpperCase().slice(0, 30),
      petugas: ambil(b, "petugas").toUpperCase().slice(0, 60), responden: ambil(b, "responden").toUpperCase().slice(0, 60),
      waktu_input: ambil(b, "waktu_input").slice(0, 40), catatan: ambil(b, "catatan").slice(0, 300),
    };
    let id = ambil(b, "id_klien").replace(/[^A-Za-z0-9_-]/g, "").slice(0, 80);
    if (!id) {
      // Baris kembar di berkas yang sama tetap dihitung terpisah (urutan kemunculannya ikut masuk sidik).
      const dasar = Object.values(isi).join("|");
      let ke = 0;
      do { id = `u${sidik(`${dasar}|${ke++}`)}`; } while (idDipakai.has(id));
    } else if (idDipakai.has(id)) {
      galat.push({ baris: nomor, alasan: `id_klien ${id} ganda di berkas ini` });
      return;
    }
    idDipakai.add(id);
    baris.push({ ...isi, id_klien: id });
  });
  return { baris, galat, galatBerkas: "" };
}

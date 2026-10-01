// Inti panel pengaturan: validasi, perbandingan, dan penulisan JSON. Murni logika, tanpa DOM, sehingga bisa diuji di Node.
// Aturan validasi sengaja sama dengan pipeline/pengaturan.py (ada uji yang membandingkan keduanya).

/** Nilai pada jalur bertitik, mis. "sinyal.ambang_persen.pokok" atau "sinyal.rasio_volatilitas_batas.0". */
export function ambil(data, jalur) {
  let sekarang = data;
  for (const bagian of jalur.split(".")) {
    if (Array.isArray(sekarang) && /^\d+$/.test(bagian) && Number(bagian) < sekarang.length) sekarang = sekarang[Number(bagian)];
    else if (sekarang !== null && typeof sekarang === "object" && !Array.isArray(sekarang) && Object.hasOwn(sekarang, bagian)) sekarang = sekarang[bagian];
    else return { ada: false, nilai: undefined };
  }
  return { ada: true, nilai: sekarang };
}

/** Mengisi nilai pada jalur (objek diubah langsung). Bagian yang belum ada dibuat sebagai objek. */
export function atur(data, jalur, nilai) {
  const bagian = jalur.split(".");
  let sekarang = data;
  for (const b of bagian.slice(0, -1)) {
    if (Array.isArray(sekarang)) sekarang = sekarang[Number(b)];
    else {
      if (sekarang[b] === null || typeof sekarang[b] !== "object") sekarang[b] = {};
      sekarang = sekarang[b];
    }
  }
  const akhir = bagian[bagian.length - 1];
  if (Array.isArray(sekarang)) sekarang[Number(akhir)] = nilai;
  else sekarang[akhir] = nilai;
  return data;
}

export const salin = (x) => JSON.parse(JSON.stringify(x));
export const sama = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const adalahAngka = (x) => typeof x === "number" && Number.isFinite(x);
const nilaiPilihan = (kolom) => (kolom.pilihan || []).map((p) => p.nilai);

function regexPenuh(pola) {
  return new RegExp(`^(?:${pola})$`);
}

/** Pesan masalah untuk satu isian, atau null bila sah. */
export function periksaKolom(kolom, nilai) {
  switch (kolom.tipe) {
    case "bulat":
    case "desimal":
      if (!adalahAngka(nilai)) return "harus berupa angka";
      if (kolom.tipe === "bulat" && !Number.isInteger(nilai)) return "harus berupa bilangan bulat";
      if (nilai < kolom.min || nilai > kolom.maks) return `harus antara ${kolom.min} dan ${kolom.maks}`;
      return null;
    case "saklar":
      return typeof nilai === "boolean" ? null : "harus berupa ya atau tidak";
    case "pilihan":
      return nilaiPilihan(kolom).some((x) => x === nilai) ? null : "bukan salah satu pilihan yang tersedia";
    case "banyak_pilihan": {
      const boleh = nilaiPilihan(kolom);
      if (!Array.isArray(nilai) || nilai.some((x) => !boleh.includes(x))) return "berisi pilihan yang tidak dikenal";
      if (new Set(nilai).size !== nilai.length) return "berisi pilihan yang ganda";
      if (nilai.length < (kolom.minimal || 0)) return `pilih minimal ${kolom.minimal || 0}`;
      return null;
    }
    case "urutan": {
      const boleh = new Set((kolom.pilihan || []).flatMap((p) => p.nilai));
      if (!Array.isArray(nilai) || nilai.length === 0 || nilai.some((x) => typeof x !== "string" || !boleh.has(x))) return "harus berisi nama AI yang dikenal";
      if (new Set(nilai).size !== nilai.length) return "berisi AI yang ganda";
      return null;
    }
    case "teks":
      if (typeof nilai !== "string") return "harus berupa teks";
      if (nilai.length > (kolom.maks_panjang || 200)) return "terlalu panjang";
      if (kolom.pola && !regexPenuh(kolom.pola).test(nilai)) return kolom.pesan_pola || "bentuknya tidak sesuai";
      return null;
    case "url":
      if (typeof nilai !== "string") return "harus berupa teks";
      if (nilai === "") return kolom.boleh_kosong ? null : "tidak boleh kosong";
      if (nilai.length > 300 || !/^https?:\/\/[^\s/$.?#][^\s]*$/.test(nilai)) return "harus berupa alamat web yang diawali https://";
      return null;
    default:
      return `jenis isian tidak dikenal: ${kolom.tipe}`;
  }
}

/** Semua isian yang salah sebagai [{ jalur, pesan }]. Kosong berarti pengaturan sah. */
export function periksa(pengaturan, skema) {
  const masalah = [];
  for (const kolom of skema.kolom) {
    const { ada, nilai } = ambil(pengaturan, kolom.jalur);
    if (!ada) {
      masalah.push({ jalur: kolom.jalur, pesan: `${kolom.label}: belum diisi` });
      continue;
    }
    const pesan = periksaKolom(kolom, nilai);
    if (pesan) masalah.push({ jalur: kolom.jalur, pesan: `${kolom.label}: ${pesan}` });
  }
  for (const aturan of skema.aturan_silang || []) {
    const [a, b] = aturan.jalur.map((j) => ambil(pengaturan, j));
    if (!(a.ada && b.ada && adalahAngka(a.nilai) && adalahAngka(b.nilai))) continue;
    const benar = aturan.jenis === "kurang_dari" ? a.nilai < b.nilai : a.nilai <= b.nilai;
    if (!benar) masalah.push({ jalur: aturan.jalur[1], pesan: aturan.pesan });
  }
  return masalah;
}

/** Pesan masalah untuk nilai kunci rahasia yang diketik, atau null bila bentuknya wajar. */
export function periksaRahasia(rahasia, nilai) {
  if (!nilai) return "belum diisi";
  if (rahasia.pola && !regexPenuh(rahasia.pola).test(nilai)) return rahasia.pesan_pola || "bentuknya tidak sesuai";
  if (rahasia.nama === "SMTP_PORT" && (Number(nilai) < 1 || Number(nilai) > 65535)) return "port harus antara 1 dan 65535";
  return null;
}

/** Perbedaan dua pengaturan untuk isian yang ada di skema: [{ jalur, kolom, dari, ke }]. */
export function bedaPengaturan(awal, akhir, skema) {
  const hasil = [];
  for (const kolom of skema.kolom) {
    const a = ambil(awal, kolom.jalur).nilai;
    const b = ambil(akhir, kolom.jalur).nilai;
    if (!sama(a, b)) hasil.push({ jalur: kolom.jalur, kolom, dari: a, ke: b });
  }
  return hasil;
}

const angkaRapi = (x) => Number(x.toPrecision(12)).toString();

/** Nilai untuk ditampilkan ke manusia (label pilihan, satuan, persen). */
export function teksNilai(kolom, nilai) {
  if (nilai === undefined || nilai === null) return "kosong";
  switch (kolom.tipe) {
    case "saklar":
      return nilai ? "menyala" : "mati";
    case "pilihan":
    case "urutan":
      return (kolom.pilihan.find((p) => sama(p.nilai, nilai)) || { label: String(nilai) }).label;
    case "banyak_pilihan":
      return nilai.length ? nilai.map((x) => (kolom.pilihan.find((p) => p.nilai === x) || { label: String(x) }).label).join(", ") : "tidak ada";
    case "bulat":
    case "desimal": {
      const tampil = adalahAngka(nilai) ? angkaRapi(nilai * (kolom.skala || 1)) : String(nilai);
      return kolom.satuan ? `${tampil} ${kolom.satuan}` : tampil;
    }
    case "url":
    case "teks":
      return nilai === "" ? "kosong" : String(nilai);
    default:
      return String(nilai);
  }
}

/** Mengubah isian angka di formulir (mis. "90" untuk persen) menjadi nilai tersimpan (0.9). Kosong atau salah menjadi null. */
export function dariTampilan(kolom, teks) {
  const bersih = String(teks).trim().replace(",", ".");
  if (bersih === "") return null;
  const angka = Number(bersih);
  if (!Number.isFinite(angka)) return null;
  const nilai = angka / (kolom.skala || 1);
  return Number(nilai.toPrecision(12));
}

/** Nilai tersimpan menjadi teks untuk kotak isian angka. */
export function keTampilan(kolom, nilai) {
  return adalahAngka(nilai) ? angkaRapi(nilai * (kolom.skala || 1)) : "";
}

const skalar = (x) => x === null || typeof x !== "object";

/**
 * JSON rapi untuk config/pengaturan.json: indentasi 2 spasi, larik sederhana satu baris, dan objek kecil
 * (tanpa objek di dalamnya, muat dalam 80 karakter) satu baris. Hasilnya stabil, jadi perbedaan di git tetap kecil.
 */
export function rapikan(nilai, tingkat = 0) {
  const tab = "  ";
  if (Array.isArray(nilai)) {
    if (nilai.every(skalar)) return `[${nilai.map((x) => JSON.stringify(x)).join(", ")}]`;
    return `[\n${nilai.map((x) => tab.repeat(tingkat + 1) + rapikan(x, tingkat + 1)).join(",\n")}\n${tab.repeat(tingkat)}]`;
  }
  if (nilai !== null && typeof nilai === "object") {
    const pasangan = Object.entries(nilai);
    if (!pasangan.length) return "{}";
    const tanpaBersarang = pasangan.every(([, v]) => skalar(v) || (Array.isArray(v) && v.every(skalar)));
    if (tingkat > 0 && tanpaBersarang) {
      const satuBaris = `{${pasangan.map(([k, v]) => `${JSON.stringify(k)}: ${rapikan(v, tingkat + 1)}`).join(", ")}}`;
      if (satuBaris.length <= 80) return satuBaris;
    }
    return `{\n${pasangan.map(([k, v]) => `${tab.repeat(tingkat + 1)}${JSON.stringify(k)}: ${rapikan(v, tingkat + 1)}`).join(",\n")}\n${tab.repeat(tingkat)}}`;
  }
  return JSON.stringify(nilai);
}

/** Isi berkas pengaturan siap simpan (diakhiri baris baru). */
export const tulisPengaturan = (pengaturan) => `${rapikan(pengaturan)}\n`;

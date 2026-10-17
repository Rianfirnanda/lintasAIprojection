// Mesin jawab Tanya Takar: menjawab pertanyaan sehari-hari tentang harga dari data situs (tanpa AI, tanpa kunci).
// Murni logika tanpa DOM, jadi bisa diuji di Node. Bila pertanyaannya tidak bisa dijawab dari data, hasilnya
// { perluAi: true } dan tampilan (tanya.js) memutuskan apakah AI boleh dipakai.
//
// Hasil: { baris: [teks], tautan: [{ href, label }], saran: [pertanyaan lanjutan], perluAi, niat }
import { selisihHarga, ringkasHariIni } from "./selisih.js";

const rp = (x) => `Rp${Math.round(x).toLocaleString("id-ID")}`;
const persen = (x, d = 1) => `${x > 0 ? "+" : ""}${Number(x).toLocaleString("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d })}%`;
const BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
const tgl = (iso) => { if (!iso) return "–"; const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number); return `${d} ${BULAN[m - 1]} ${y}`; };

export const normal = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();

// Kata yang tidak membantu mengenali barang.
const KATA_UMUM = new Set(("harga berapa apakah apa yang di ke dari dan atau untuk hari ini sekarang kemarin minggu bulan tahun depan lalu " +
  "naik turun mahal murah stabil berubah perkiraan prakiraan prediksi ramalan akan nanti besok berapakah gimana bagaimana kenapa mengapa " +
  "sebab penyebab kg liter per rupiah rp pasar bengkulu tengah kabupaten kota tolong mohon dong ya kah lagi masih sudah belum cek lihat " +
  "info informasi tentang soal mengenai jika kalau bisa tahu ingin mau saya kami kita paling tertinggi terendah terbesar banyak sedikit " +
  "7 14 30 hari2 seminggu sebulan dua tiga ada adakah").split(" "));

// Tanda bahwa pertanyaan memang soal harga. Tanpa tanda ini dan dengan banyak kata lain (mis. "cara menyimpan cabai
// supaya awet"), pertanyaan menyebut barang tetapi bukan soal harga, jadi tidak dijawab dengan daftar harga.
const TANDA_HARGA = /(harga|berapa|naik|turun|mahal|murah|rp|rupiah|sekarang|hari ini|kemarin|minggu|bulan|stabil|berubah|kg|liter)/;

/** Kata di pertanyaan yang bukan kata umum dan bukan bagian nama barang yang dikenali. */
function kataLain(teks, barang) {
  const nama = new Set(barang.flatMap((v) => normal(`${v.nama} ${v.komoditas || ""}`).split(" ")));
  return teks.split(" ").filter((k) => k.length > 1 && !KATA_UMUM.has(k) && !nama.has(k) && ![...nama].some((n) => k.length >= 4 && n.startsWith(k)));
}

/** Barang yang disebut di pertanyaan: daftar varian dengan skor tertinggi (bisa lebih dari satu, mis. "cabai"). */
export function kenaliBarang(pertanyaan, varian) {
  const kata = normal(pertanyaan).split(" ").filter((k) => k.length > 1 && !KATA_UMUM.has(k));
  if (!kata.length) return [];
  const skor = varian.map((v) => {
    const nama = normal(`${v.nama} ${v.komoditas || ""}`).split(" ");
    let s = 0;
    for (const k of kata) if (nama.some((n) => n === k || (k.length >= 4 && n.startsWith(k)))) s += 1;
    return { v, s };
  });
  const maks = Math.max(0, ...skor.map((x) => x.s));
  return maks ? skor.filter((x) => x.s === maks).map((x) => x.v) : [];
}

const ada = (x) => x !== null && x !== undefined;
const arahKata = (x) => (!ada(x) ? "belum bisa dibandingkan" : x > 0.5 ? "naik" : x < -0.5 ? "turun" : "hampir tetap");

function horizonDari(teks) {
  if (/(30 hari|sebulan|bulan depan|satu bulan)/.test(teks)) return 30;
  if (/(14 hari|dua minggu|2 minggu)/.test(teks)) return 14;
  return 7;
}

function kalimatHarga(v) {
  const m = selisihHarga(v, "mingguan"), b = selisihHarga(v, "bulanan");
  const bagian = [`${v.nama} sekarang ${rp(v.harga_terakhir)} per ${v.satuan} (data ${tgl(v.tanggal_terakhir)}).`];
  if (m) bagian.push(`Dibanding minggu lalu ${arahKata(m.persen)}${m.selisih ? ` ${rp(Math.abs(m.selisih))} (${persen(m.persen)})` : ""}.`);
  if (b) bagian.push(`Dibanding sebulan lalu ${arahKata(b.persen)}${b.selisih ? ` ${rp(Math.abs(b.selisih))} (${persen(b.persen)})` : ""}.`);
  if (v.sinyal) bagian.push("Harganya sedang jauh dari biasanya, jadi perlu diwaspadai.");
  return bagian.join(" ");
}

/**
 * Menjawab satu pertanyaan. `data`: { ringkasan, sinyal, meta }. `muatSeri(kode)` (opsional, async) dipakai untuk perkiraan
 * 14 dan 30 hari. Tautan selalu ke halaman situs; tampilan menyaring tautan yang tidak boleh dibuka peran.
 */
export async function jawab(pertanyaan, data, muatSeri = null) {
  const teks = normal(pertanyaan);
  const v = data.ringkasan?.varian || [];
  const sinyalAktif = (data.sinyal?.sinyal || []).filter((s) => s.aktif);
  const barang = kenaliBarang(pertanyaan, v);
  const hasil = (niat, baris, tautan = [], saran = []) => ({ niat, baris, tautan, saran, perluAi: false });
  const tautanBarang = (x) => ({ href: `harga.html#barang=${encodeURIComponent(x.kode)}`, label: `Grafik ${x.nama}` });

  if (!teks) return hasil("kosong", ["Silakan ketik pertanyaan, misalnya \"harga cabai hari ini\"."]);

  // sapaan dan bantuan
  if (/^(halo|hai|hi|hello|selamat (pagi|siang|sore|malam)|assalamualaikum|permisi)\b/.test(teks) && !barang.length || /(bisa apa|bantuan|cara pakai|apa saja yang bisa|kamu siapa)/.test(teks)) {
    return hasil("bantuan", [
      "Halo, saya Tanya Takar. Saya menjawab dari data harga pangan Kabupaten Bengkulu Tengah di situs ini.",
      "Anda bisa bertanya harga barang, barang yang naik atau turun, perkiraan harga 7 sampai 30 hari, peringatan harga, hari raya berikutnya, atau kapan data terakhir diperbarui.",
    ], [], ["Harga cabai hari ini", "Apa yang naik paling tinggi?", "Perkiraan harga beras minggu depan", "Ada peringatan apa?"]);
  }

  // hari raya
  if (/(hari raya|lebaran|idul|natal|tahun baru|nataru|ramadan|ramadhan|puasa|imlek|nyepi|waisak)/.test(teks)) {
    const h = data.ringkasan?.hari_raya || {}, b = h.berikutnya;
    if (!b) return hasil("hariraya", ["Belum ada hari raya yang terjadwal di data situs."]);
    const baris = [`Hari raya berikutnya: ${b.nama}, ${tgl(b.tanggal)}${b.status !== "pasti" ? " (perkiraan)" : ""}, ${b.hari_menuju} hari lagi.`];
    if ((h.profil_top || []).length) {
      baris.push(`Pada hari raya sebelumnya, kenaikan tertinggi: ${h.profil_top.slice(0, 3).map((p) => `${p.nama} ${persen(p.kenaikan_puncak_persen, 0)}`).join(", ")}.`);
    }
    return hasil("hariraya", baris, [{ href: "index.html", label: "Situasi menjelang hari raya" }], ["Apa yang naik paling tinggi?"]);
  }

  // peringatan
  if (/(peringatan|waspada|janggal|sinyal|bahaya|perlu dicek|perlu diwaspadai)/.test(teks) && !barang.length) {
    if (!data.sinyal) return hasil("peringatan", [`Ada ${v.filter((x) => x.sinyal).length} barang yang harganya jauh dari biasanya dan perlu diwaspadai.`],
      [{ href: "harga.html", label: "Lihat semua harga" }]);
    if (!sinyalAktif.length) return hasil("peringatan", ["Tidak ada peringatan aktif. Semua harga masih dalam pola biasa."]);
    const penting = sinyalAktif.filter((s) => s.keparahan === "tinggi");
    return hasil("peringatan", [
      `Ada ${sinyalAktif.length} peringatan aktif, ${penting.length} di antaranya tingkat tinggi.`,
      ...(penting.length ? penting : sinyalAktif).slice(0, 3).map((s) => `• ${s.judul}`),
    ], [{ href: "sinyal.html", label: "Buka halaman Peringatan" }], ["Apa yang naik paling tinggi?"]);
  }

  // kesegaran data dan sumber
  if (/(data terakhir|diperbarui|update|kapan data|sumber data|dari mana data|asal data)/.test(teks) && !barang.length) {
    const m = data.meta || {};
    return hasil("data", [
      `Data harga terakhir per ${tgl(m.tanggal_data_terakhir)}.${m.dibuat ? ` Situs terakhir diperbarui ${tgl(m.dibuat)}.` : ""}`,
      "Harga berasal dari petugas pasar dan sumber resmi (SP2KP Kemendag dan PIHPS Bank Indonesia), lalu diperiksa dulu sebelum dipakai.",
    ], [{ href: "sumber.html", label: "Sumber data" }]);
  }

  // terbesar: naik atau turun paling banyak
  if (/(paling|tertinggi|terbesar|terbanyak|terendah|termurah|termahal)/.test(teks) && !barang.length) {
    const turun = /(turun|murah|terendah|termurah)/.test(teks) && !/(termahal)/.test(teks);
    const periode = /(minggu|pekan)/.test(teks) ? "mingguan" : "bulanan";
    const urut = v.filter((x) => ada(x.perubahan?.[periode])).sort((a, b) => (turun ? a.perubahan[periode] - b.perubahan[periode] : b.perubahan[periode] - a.perubahan[periode]))
      .filter((x) => (turun ? x.perubahan[periode] < -0.5 : x.perubahan[periode] > 0.5)).slice(0, 3);
    const lalu = periode === "mingguan" ? "minggu lalu" : "sebulan lalu";
    if (!urut.length) return hasil("terbesar", [`Dibanding ${lalu}, tidak ada harga yang ${turun ? "turun" : "naik"} lebih dari 0,5%.`]);
    return hasil("terbesar", [
      `${turun ? "Turun" : "Naik"} paling banyak dibanding ${lalu}:`,
      ...urut.map((x, i) => { const s = selisihHarga(x, periode); return `${i + 1}. ${x.nama}: ${rp(x.harga_terakhir)}/${x.satuan}${s ? `, ${turun ? "turun" : "naik"} ${rp(Math.abs(s.selisih))} (${persen(s.persen)})` : ""}`; }),
    ], urut.slice(0, 2).map(tautanBarang), [`Perkiraan harga ${urut[0].nama} minggu depan`]);
  }

  // perkiraan
  if (/\b(perkiraan|prakiraan|prediksi|ramalan|minggu depan|bulan depan|besok|ke depan|akan|nanti)\b/.test(teks)) {
    if (!barang.length) return hasil("perkiraan", ["Barang apa yang ingin diperkirakan harganya? Misalnya: \"perkiraan harga cabai rawit minggu depan\"."], [],
      ["Perkiraan harga beras minggu depan", "Perkiraan harga cabai merah 30 hari"]);
    const hari = horizonDari(teks);
    const baris = [];
    for (const x of barang.slice(0, 3)) {
      let p = null;
      if (hari === 7 && x.proyeksi_h7) p = x.proyeksi_h7;
      else if (muatSeri) {
        const seri = await muatSeri(x.kode).catch(() => null);
        p = seri?.proyeksi?.[hari - 1] || seri?.proyeksi?.[seri.proyeksi.length - 1] || null;
      }
      if (!p) { baris.push(`${x.nama}: perkiraan ${hari} hari belum tersedia.`); continue; }
      const beda = p.prediksi - x.harga_terakhir;
      baris.push(`${x.nama}: sekitar ${rp(p.prediksi)} per ${x.satuan} dalam ${hari} hari (sekarang ${rp(x.harga_terakhir)}${beda ? `, ${beda > 0 ? "naik" : "turun"} ${rp(Math.abs(beda))}` : ", tetap"}).` +
        ` Kisarannya ${rp(p.bawah)} sampai ${rp(p.atas)}.`);
    }
    baris.push("Perkiraan bukan angka resmi; harga sebenarnya biasanya jatuh di dalam kisaran itu.");
    return hasil("perkiraan", baris, barang.slice(0, 2).map(tautanBarang), hari === 7 ? [`Perkiraan harga ${barang[0].nama} 30 hari`] : []);
  }

  // kenapa / penyebab
  if (/(kenapa|mengapa|penyebab|sebab|alasan)/.test(teks) && barang.length) {
    const x = barang[0];
    const terkait = sinyalAktif.filter((s) => s.kode_varian === x.kode || normal(s.varian) === normal(x.nama));
    const baris = [kalimatHarga(x)];
    if (terkait.length && terkait[0].narasi) baris.push(`Catatan sistem: ${terkait[0].narasi}`);
    baris.push("Data harga tidak bisa memastikan penyebabnya. Biasanya dipengaruhi pasokan, cuaca, dan permintaan; petugas di pasar bisa memastikannya.");
    return { ...hasil("kenapa", baris, [tautanBarang(x), { href: "berita.html", label: "Berita lokal" }]), perluAi: true };
  }

  // menyebut barang tetapi bukan soal harga (mis. cara menyimpan, resep, cara menanam)
  if (barang.length && !TANDA_HARGA.test(teks) && kataLain(teks, barang).length >= 2) {
    const x = barang[0];
    const lain = new Set(kataLain(teks, barang));
    const disebut = barang.length === 1 ? x.nama : teks.split(" ").filter((k) => k.length > 1 && !KATA_UMUM.has(k) && !lain.has(k)).join(" ");
    return { niat: "lain", baris: ["Data situs ini hanya berisi harga, jadi pertanyaan itu belum bisa saya jawab dari data. " +
      (barang.length === 1 ? `Yang tersedia: harga ${x.nama} sekarang ${rp(x.harga_terakhir)} per ${x.satuan}.` : `Yang tersedia: harga ${barang.length} jenis ${disebut}.`)],
      tautan: barang.length === 1 ? [tautanBarang(x)] : [{ href: "harga.html", label: "Semua harga" }],
      saran: [`Harga ${disebut} hari ini`, `Perkiraan harga ${x.nama} minggu depan`], perluAi: true };
  }

  // harga barang (bawaan bila barang disebut)
  if (barang.length) {
    if (barang.length > 3) {
      const lain = new Set(kataLain(teks, barang));
      const disebut = teks.split(" ").filter((k) => k.length > 1 && !KATA_UMUM.has(k) && !lain.has(k)).join(" ") || "barang";
      return hasil("harga", [`Ada ${barang.length} jenis ${disebut}:`,
        ...barang.map((x) => `• ${x.nama}: ${rp(x.harga_terakhir)}/${x.satuan}${ada(x.perubahan?.mingguan) ? ` (${persen(x.perubahan.mingguan)} seminggu)` : ""}`)],
      [{ href: "harga.html", label: "Semua harga" }], [`Perkiraan harga ${barang[0].nama} minggu depan`]);
    }
    return hasil("harga", barang.map(kalimatHarga), barang.slice(0, 2).map(tautanBarang),
      [`Perkiraan harga ${barang[0].nama} minggu depan`, `Kenapa harga ${barang[0].nama} berubah?`]);
  }

  // ringkasan umum
  if (/(hari ini|ringkasan|kondisi|situasi|keadaan|gimana harga|bagaimana harga|harga pangan)/.test(teks)) {
    return hasil("ringkasan", [ringkasHariIni(v, "mingguan").kalimat], [{ href: "harga.html", label: "Semua harga" }], ["Apa yang naik paling tinggi?", "Ada peringatan apa?"]);
  }

  return { niat: "tidak_dikenal", baris: ["Maaf, saya belum menemukan jawabannya di data situs."], tautan: [],
    saran: ["Harga cabai hari ini", "Apa yang naik paling tinggi?", "Ada peringatan apa?"], perluAi: true };
}

/** Ringkasan data yang dikirim ke AI sebagai satu-satunya bahan jawaban (dibatasi supaya pendek). */
export function konteksAi(data) {
  const v = data.ringkasan?.varian || [];
  const baris = v.map((x) => `${x.nama}: ${rp(x.harga_terakhir)}/${x.satuan}, mingguan ${ada(x.perubahan?.mingguan) ? persen(x.perubahan.mingguan) : "-"}, ` +
    `bulanan ${ada(x.perubahan?.bulanan) ? persen(x.perubahan.bulanan) : "-"}${x.proyeksi_h7 ? `, perkiraan 7 hari ${rp(x.proyeksi_h7.prediksi)}` : ""}${x.sinyal ? ", perlu diwaspadai" : ""}`);
  const sinyal = (data.sinyal?.sinyal || []).filter((s) => s.aktif).slice(0, 8).map((s) => `- ${s.judul}${s.narasi ? `. ${s.narasi}` : ""}`);
  const hr = data.ringkasan?.hari_raya?.berikutnya;
  return [`Tanggal data terakhir: ${tgl(data.meta?.tanggal_data_terakhir)}. Wilayah: Kabupaten Bengkulu Tengah, Provinsi Bengkulu.`,
    "Harga terakhir per barang:", ...baris,
    sinyal.length ? "Peringatan aktif:" : "Tidak ada peringatan aktif.", ...sinyal,
    hr ? `Hari raya berikutnya: ${hr.nama}, ${tgl(hr.tanggal)} (${hr.hari_menuju} hari lagi).` : "",
    data.berita ? `Kesimpulan berita lokal hari ini: ${data.berita}` : ""].filter(Boolean).join("\n").slice(0, 9000);
}

export const SISTEM_AI = "Anda adalah Tanya Takar, asisten data harga pangan BPS Kabupaten Bengkulu Tengah. Jawab dalam bahasa Indonesia " +
  "sehari-hari yang mudah dipahami semua kalangan, paling banyak 5 kalimat, tanpa istilah teknis. Pakai HANYA angka dan fakta dari DATA " +
  "yang diberikan; jangan mengarang angka, tanggal, atau penyebab. Bila jawabannya tidak ada di DATA, katakan terus terang bahwa datanya " +
  "tidak tersedia. Jangan memberi saran kebijakan; cukup sebutkan apa yang perlu dipantau atau dicek. Tulis rupiah seperti Rp12.500 dan " +
  "persen dengan koma, mis. 5,3%.";

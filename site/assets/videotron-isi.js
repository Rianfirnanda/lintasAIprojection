// Isi Mode Videotron (layar rapat, TV, atau videotron): menyusun tampilan dari data situs. Murni tanpa DOM supaya bisa
// diuji di Node; rapat.js yang menampilkan dan memutarnya. Semua angka dari ringkasan.json, sinyal.json, dan seri/*.json.
import { gambarKomoditas } from "./gambar-komoditas.js";
import { selisihHarga, ringkasHariIni } from "./selisih.js";

export const rp = (x) => `Rp${Math.round(Number(x)).toLocaleString("id-ID")}`;
export const persen = (x, d = 1) => `${x > 0 ? "+" : ""}${Number(x).toLocaleString("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d })}%`;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const ada = (x) => x !== null && x !== undefined && Number.isFinite(Number(x));
const BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
export const tglPanjang = (iso) => { if (!iso) return "–"; const [y, m, d] = String(iso).slice(0, 10).split("-").map(Number); return `${d} ${BULAN[m - 1]} ${y}`; };

/** naik, turun, atau datar (perubahan di bawah 0,5% dianggap tetap). */
export const arah = (x) => (!ada(x) ? "datar" : x > 0.5 ? "naik" : x < -0.5 ? "turun" : "datar");
const TANDA = { naik: "▲", turun: "▼", datar: "▬" };
const JENIS_HARGA = ["anomali_harga", "proyeksi_naik", "risiko_hari_raya"];

/** Kalimat perubahan singkat: "▲ Rp1.500 (+3,2%)" atau "▬ Tetap". */
export function teksUbah(v, periode = "mingguan") {
  const s = selisihHarga(v, periode);
  if (!s) return { arah: "datar", teks: "Belum ada pembanding" };
  if (!s.selisih) return { arah: "datar", teks: `${TANDA.datar} Tetap` };
  const a = arah(s.persen ?? (s.selisih ? Math.sign(s.selisih) : 0));
  if (a === "datar") return { arah: a, teks: `${TANDA.datar} Tetap` };
  return { arah: a, teks: `${TANDA[a]} ${rp(Math.abs(s.selisih))}${ada(s.persen) ? ` (${persen(s.persen)})` : ""}` };
}

/** Garis harga kecil (SVG) dari deret aktual; null dan celah dilewati. */
export function garisSvg(nilai, { lebar = 240, tinggi = 72 } = {}) {
  const titik = nilai.map((y, i) => [i, y]).filter(([, y]) => ada(y));
  if (titik.length < 2) return "";
  const ys = titik.map(([, y]) => y), min = Math.min(...ys), maks = Math.max(...ys), rentang = maks - min || 1;
  const n = nilai.length - 1 || 1;
  const xy = titik.map(([i, y]) => [(i / n) * lebar, tinggi - 6 - ((y - min) / rentang) * (tinggi - 12)]);
  const garis = xy.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const bidang = `${garis} L${xy[xy.length - 1][0].toFixed(1)} ${tinggi} L${xy[0][0].toFixed(1)} ${tinggi} Z`;
  const [ax, ay] = xy[xy.length - 1];
  return `<svg class="vt-garis" viewBox="0 0 ${lebar} ${tinggi}" preserveAspectRatio="none" aria-hidden="true">
    <path class="vt-bidang" d="${bidang}"/><path class="vt-jalur" d="${garis}"/><circle cx="${ax.toFixed(1)}" cy="${ay.toFixed(1)}" r="4"/></svg>`;
}

/** Satu varian wakil tiap komoditas (yang paling banyak bergerak sebulan terakhir), urut menurut daftar. */
export function wakilKomoditas(varian) {
  const per = new Map();
  for (const v of varian) {
    const k = v.kode_komoditas || v.komoditas;
    const lama = per.get(k);
    if (!lama || Math.abs(v.perubahan?.bulanan ?? 0) > Math.abs(lama.perubahan?.bulanan ?? 0)) per.set(k, v);
  }
  return [...per.values()];
}

export function kartuHarga(v) {
  const u = teksUbah(v, "mingguan"), b = selisihHarga(v, "bulanan");
  return `<article class="vt-harga ${u.arah}${v.sinyal ? " waspada" : ""}">
    <div class="vt-harga-kepala">${gambarKomoditas(v.kode)}<h3>${esc(v.nama)}</h3></div>
    <p class="vt-harga-angka"><b>${rp(v.harga_terakhir)}</b><span>/${esc(v.satuan || "kg")}</span></p>
    <p class="vt-ubah ${u.arah}"><small>Seminggu</small> ${esc(u.teks)}</p>
    <p class="vt-lalu">${b ? `Sebulan lalu ${rp(b.lalu)}` : "&nbsp;"}${v.sinyal ? `<span class="vt-lencana">Waspada</span>` : ""}</p>
  </article>`;
}

function daftarBatang(isi, periode, kelas) {
  if (!isi.length) return `<p class="vt-kosong">Tidak ada yang ${kelas === "naik" ? "naik" : "turun"} lebih dari 0,5%.</p>`;
  const maks = Math.max(...isi.map((v) => Math.abs(v.perubahan[periode])));
  return `<ol class="vt-batang ${kelas}">${isi.map((v) => {
    const s = selisihHarga(v, periode);
    return `<li>${gambarKomoditas(v.kode)}<span class="vt-batang-nama">${esc(v.nama)}<small>${rp(v.harga_terakhir)}/${esc(v.satuan || "kg")}</small></span>
      <span class="vt-batang-isi"><i style="--lebar:${(Math.abs(v.perubahan[periode]) / maks) * 100}%"></i></span>
      <b>${s ? `${s.selisih > 0 ? "+" : "−"}${rp(Math.abs(s.selisih))}` : ""}<small>${persen(v.perubahan[periode])}</small></b></li>`;
  }).join("")}</ol>`;
}

function angkaSinyal(s, satuan) {
  const per = satuan ? `/${satuan}` : "";
  if (ada(s.nilai_aktual) && ada(s.baseline)) return `Sekarang <b>${rp(s.nilai_aktual)}${per}</b>, biasanya ${rp(s.baseline)}${per}`;
  if (ada(s.nilai_aktual) && s.proyeksi_h7?.prediksi) return `Sekarang <b>${rp(s.nilai_aktual)}${per}</b>, 7 hari lagi sekitar ${rp(s.proyeksi_h7.prediksi)}${per}`;
  if (ada(s.nilai_aktual)) return `Sekarang <b>${rp(s.nilai_aktual)}${per}</b>`;
  return esc(s.narasi || "");
}

/**
 * Daftar tampilan yang diputar bergantian: [{ kunci, judul, sub, isi (HTML), lama (detik) }].
 * `data`: { ringkasan, sinyal, seri: { kode: seri } }. `opsi.perHalaman`: kartu harga per layar (menyesuaikan ukuran layar).
 * `opsi.ikon(nama, ukuran)`: ikon garis (opsional).
 */
export function susunTampilan(data, opsi = {}) {
  const { ringkasan, sinyal, seri = {} } = data;
  const ikon = opsi.ikon || (() => "");
  const perHalaman = Math.max(4, opsi.perHalaman || 12);
  const v = (ringkasan?.varian || []).filter((x) => ada(x.harga_terakhir));
  const daftar = [];
  if (!v.length) return [{ kunci: "kosong", judul: "Belum ada data harga", sub: "", isi: `<p class="vt-kalimat">Data harga belum tersedia.</p>`, lama: 20 }];

  // 1. Ringkasan hari ini
  const m = (x) => x.perubahan?.mingguan;
  const naik = v.filter((x) => arah(m(x)) === "naik"), turun = v.filter((x) => arah(m(x)) === "turun");
  const waspada = v.filter((x) => x.sinyal).length;
  const urutNaik = [...naik].sort((a, b) => m(b) - m(a)).slice(0, 3), urutTurun = [...turun].sort((a, b) => m(a) - m(b)).slice(0, 3);
  const baris3 = (isi, kelas) => isi.length ? isi.map((x) => { const u = teksUbah(x); return `<li>${gambarKomoditas(x.kode)}<span>${esc(x.nama)}</span><b class="${kelas}">${esc(u.teks)}</b></li>`; }).join("")
    : `<li class="vt-kosong">Tidak ada</li>`;
  daftar.push({ kunci: "ringkasan", judul: "Ringkasan harga hari ini", sub: "Dibanding minggu lalu", lama: 18, isi: `
    <p class="vt-kalimat">${esc(ringkasHariIni(v, "mingguan").kalimat)}</p>
    <div class="vt-kpi">
      <div class="naik">${ikon("tren", 34)}<b>${naik.length}</b><span>harga naik</span></div>
      <div class="turun">${ikon("trenTurun", 34)}<b>${turun.length}</b><span>harga turun</span></div>
      <div class="datar">${ikon("kubus", 34)}<b>${v.length - naik.length - turun.length}</b><span>harga stabil</span></div>
      <div class="waspada">${ikon("peringatan", 34)}<b>${waspada}</b><span>perlu diwaspadai</span></div>
    </div>
    <div class="vt-dua">
      <section><h3>Naik paling banyak</h3><ul class="vt-tiga">${baris3(urutNaik, "naik")}</ul></section>
      <section><h3>Turun paling banyak</h3><ul class="vt-tiga">${baris3(urutTurun, "turun")}</ul></section>
    </div>` });

  // 2. Harga semua bahan pokok, dibagi per layar
  const halaman = Math.ceil(v.length / perHalaman);
  // bagi rata supaya layar terakhir tidak hampir kosong (mis. 21 barang di 2 layar: 11 dan 10)
  const dasar = Math.floor(v.length / halaman), lebih = v.length % halaman;
  let awal = 0;
  for (let i = 0; i < halaman; i++) {
    const isi = v.slice(awal, awal + dasar + (i < lebih ? 1 : 0));
    awal += isi.length;
    daftar.push({ kunci: `harga-${i + 1}`, judul: "Harga bahan pokok hari ini", sub: `${halaman > 1 ? `Bagian ${i + 1} dari ${halaman} · ` : ""}${v.length} barang dipantau`,
      lama: Math.max(15, Math.min(30, isi.length * 1.6)), isi: `<div class="vt-grid-harga" style="--kolom:${opsi.kolom || 4}">${isi.map(kartuHarga).join("")}</div>` });
  }

  // 3. Naik dan turun terbesar sebulan
  const b = (x) => x.perubahan?.bulanan;
  const naikB = v.filter((x) => arah(b(x)) === "naik").sort((x, y) => b(y) - b(x)).slice(0, 5);
  const turunB = v.filter((x) => arah(b(x)) === "turun").sort((x, y) => b(x) - b(y)).slice(0, 5);
  daftar.push({ kunci: "gerak", judul: "Pergerakan harga sebulan terakhir", sub: "Dibanding harga sebulan lalu", lama: 18, isi: `
    <div class="vt-dua lebar"><section><h3 class="naik">${ikon("tren", 26)} Naik paling tinggi</h3>${daftarBatang(naikB, "bulanan", "naik")}</section>
      <section><h3 class="turun">${ikon("trenTurun", 26)} Turun paling banyak</h3>${daftarBatang(turunB, "bulanan", "turun")}</section></div>` });

  // 4. Tren 30 hari (dari seri harian)
  const tren = wakilKomoditas(v).filter((x) => seri[x.kode]?.aktual?.length).slice(0, opsi.jumlahTren || 8);
  if (tren.length >= 2) {
    daftar.push({ kunci: "tren", judul: "Tren harga 30 hari terakhir", sub: "Satu barang wakil tiap komoditas", lama: 20, isi: `
      <div class="vt-grid-tren">${tren.map((x) => {
        const s = seri[x.kode], ak = s.aktual.slice(-30), angka = ak.filter(ada);
        const awal = angka[0], akhir = angka[angka.length - 1], ubah = awal ? ((akhir - awal) / awal) * 100 : null;
        const a = arah(ubah);
        return `<article class="vt-tren ${a}"><header>${gambarKomoditas(x.kode)}<h3>${esc(x.nama)}</h3></header>
          <p><b>${rp(x.harga_terakhir)}</b><span>/${esc(x.satuan || "kg")}</span><em class="${a}">${ada(ubah) ? `${TANDA[a]} ${persen(ubah)}` : ""}</em></p>
          ${garisSvg(ak)}
          <footer><span>Terendah ${rp(Math.min(...angka))}</span><span>Tertinggi ${rp(Math.max(...angka))}</span></footer></article>`;
      }).join("")}</div>` });
  }

  // 5. Peringatan harga (bukan catatan kelengkapan data)
  const satuan = Object.fromEntries(v.map((x) => [x.kode, x.satuan]));
  const penting = (sinyal?.sinyal || []).filter((s) => s.aktif && JENIS_HARGA.includes(s.jenis) && s.keparahan !== "rendah")
    .sort((a, c) => (a.keparahan === "tinggi" ? 0 : 1) - (c.keparahan === "tinggi" ? 0 : 1)).slice(0, 6);
  daftar.push({ kunci: "peringatan", judul: "Harga yang perlu diwaspadai", sub: "Bergerak jauh dari kebiasaan, perlu dicek ke pasar", lama: 18,
    isi: penting.length ? `<div class="vt-peringatan">${penting.map((s) => `
      <article class="${s.keparahan}">${gambarKomoditas(s.kode_varian)}<div><span class="vt-tingkat">${s.keparahan === "tinggi" ? "Perlu segera dicek" : "Perlu dipantau"}</span>
        <h3>${esc(s.judul)}</h3><p>${angkaSinyal(s, satuan[s.kode_varian])}</p></div></article>`).join("")}</div>`
      : `<div class="vt-aman">${ikon("centang", 64)}<p class="vt-kalimat">Tidak ada harga yang bergerak jauh dari kebiasaan. Semua masih dalam pola biasa.</p></div>` });

  // 6. Perkiraan 7 hari
  const kira = v.filter((x) => x.proyeksi_h7?.prediksi).map((x) => ({ x, beda: (x.proyeksi_h7.prediksi - x.harga_terakhir) / x.harga_terakhir * 100 }))
    .sort((a, c) => Math.abs(c.beda) - Math.abs(a.beda)).slice(0, opsi.barisKira || 8);
  if (kira.length) {
    daftar.push({ kunci: "perkiraan", judul: "Perkiraan harga 7 hari ke depan", sub: "Barang yang diperkirakan paling banyak berubah", lama: 20, isi: `
      <table class="vt-tabel"><thead><tr><th>Barang</th><th>Sekarang</th><th>7 hari lagi</th><th class="vt-sembunyi-sempit">Kisaran</th></tr></thead>
      <tbody>${kira.map(({ x, beda }) => { const a = arah(beda), h = x.proyeksi_h7; return `<tr><td>${gambarKomoditas(x.kode)}<span>${esc(x.nama)}</span></td>
        <td>${rp(x.harga_terakhir)}</td><td class="${a}"><b>${rp(h.prediksi)}</b> ${TANDA[a]}</td>
        <td class="vt-redup vt-sembunyi-sempit">${ada(h.bawah) && ada(h.atas) ? `${rp(h.bawah)} – ${rp(h.atas)}` : "–"}</td></tr>`; }).join("")}</tbody></table>
      <p class="vt-catatan">Perkiraan bukan angka resmi. Harga sebenarnya biasanya jatuh di dalam kisaran.</p>` });
  }

  // 7. Menjelang hari raya
  const hr = ringkasan.hari_raya || {}, br = hr.berikutnya;
  if (br) {
    daftar.push({ kunci: "hariraya", judul: "Menjelang hari raya", sub: `${esc(br.nama)}${br.status !== "pasti" ? " (tanggal perkiraan)" : ""}`, lama: 16, isi: `
      <div class="vt-hariraya"><div class="vt-hitung"><b>${br.hari_menuju}</b><span>hari lagi</span><small>${esc(tglPanjang(br.tanggal))}</small></div>
        <div>${(hr.profil_top || []).length ? `<h3>Yang biasanya naik menjelang hari raya</h3><ol class="vt-batang naik">${hr.profil_top.slice(0, 5).map((p) =>
          `<li>${gambarKomoditas(p.kode)}<span class="vt-batang-nama">${esc(p.nama)}</span><span class="vt-batang-isi"><i style="--lebar:${Math.min(100, (p.kenaikan_puncak_persen / Math.max(...hr.profil_top.slice(0, 5).map((q) => q.kenaikan_puncak_persen), 1)) * 100)}%"></i></span><b>${persen(p.kenaikan_puncak_persen, 0)}</b></li>`).join("")}</ol>
          <p class="vt-catatan">Kenaikan tertinggi pada hari raya tahun-tahun sebelumnya.</p>` : `<p class="vt-kalimat">Pantau harga bahan pokok menjelang hari raya.</p>`}</div></div>` });
  }
  return daftar;
}

/** Teks berjalan di bawah layar: semua harga dengan perubahan dari minggu lalu. */
export function teksBerjalan(varian) {
  return (varian || []).filter((x) => ada(x.harga_terakhir)).map((x) => {
    const u = teksUbah(x, "mingguan");
    return `<span class="vt-jalan-isi"><b>${esc(x.nama)}</b> ${rp(x.harga_terakhir)}/${esc(x.satuan || "kg")} <em class="${u.arah}">${esc(u.teks)}</em></span>`;
  }).join("");
}

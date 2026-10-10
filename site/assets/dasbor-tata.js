// Panel mutu data dan peringatan dini di Dashboard Internal: 10 pencari data (AI Data Finder), 8 tahap pembersihan,
// kecocokan antar-sumber, peringatan dini lonjakan harga (EWS), perbandingan antarwilayah, dan rantai harga.
// Semua angka dibaca dari analitik.json; bila data belum ada, panel menulis alasannya, bukan angka karangan.
import { esc, angka, tgl } from "./app.js";

const STATUS = {
  lulus: ['baik', "Berjalan baik"],
  perlu_perhatian: ['sedang', "Perlu perhatian"],
  menunggu: ['polos', "Menunggu"],
  tinjau: ['sedang', "Perlu ditinjau"],
  gagal: ['tinggi', "Belum lolos"],
};
// Target rancangan (Laporan Progres, bagian peringatan dini).
const TARGET_EWS = { recall: 0.88, f1: 0.88, fpr: 0.10 };

const lencana = (s) => { const [k, t] = STATUS[s] || STATUS.menunggu; return `<span class="lencana ${k}">${t}</span>`; };
const tanda = (ok) => ok === null || ok === undefined ? '<span class="tanda tunggu" title="Belum bisa dinilai">–</span>'
  : ok ? '<span class="tanda ok" title="Lolos">✓</span>' : '<span class="tanda gagal" title="Belum lolos">✕</span>';
const persen0 = (x, d = 0) => (x === null || x === undefined ? "–" : `${angka(x * 100, d)}%`);
const daftarGerbang = (g) => g.length
  ? `<ul class="dsb-gerbang">${g.map((x) => `<li>${tanda(x.lolos)} ${esc(x.gerbang)}: <b>${esc(String(x.nilai ?? "–"))}</b> <span class="meta-kecil">(target ${esc(x.target)})</span></li>`).join("")}</ul>`
  : "";

export const KERANGKA_TATA = `
<h2 class="dsb-bagian">Mutu data, peringatan dini, dan perbandingan wilayah</h2>
<div class="dsb-tata">
  <section class="dsb-kartu"><div class="dsb-kartu-kepala gelap"><h2>Pencari data otomatis (10 AI Data Finder)</h2></div><div class="dsb-isi" id="dsb-finder"></div></section>
  <section class="dsb-kartu"><div class="dsb-kartu-kepala gelap"><h2>Pemeriksaan dan pembersihan data (8 tahap)</h2></div><div class="dsb-isi" id="dsb-bersih"></div></section>
  <section class="dsb-kartu"><div class="dsb-kartu-kepala gelap"><h2>Peringatan dini lonjakan harga (EWS)</h2></div><div class="dsb-isi" id="dsb-ews"></div></section>
  <section class="dsb-kartu"><div class="dsb-kartu-kepala gelap"><h2 id="dsb-judul-wil">Perbandingan dengan wilayah lain</h2></div><div class="dsb-isi" id="dsb-wil"></div></section>
  <section class="dsb-kartu"><div class="dsb-kartu-kepala gelap"><h2>Kecocokan antar-sumber</h2></div><div class="dsb-isi" id="dsb-konsensus"></div></section>
  <section class="dsb-kartu"><div class="dsb-kartu-kepala gelap"><h2>Rantai harga Kota Bengkulu</h2></div><div class="dsb-isi" id="dsb-rantai"></div></section>
</div>`;

export function gambarFinder(el, A) {
  const f = A.finder || [];
  if (!f.length) { el.innerHTML = '<p class="meta-kecil">Status pencari data belum tersedia.</p>'; return; }
  const r = A.finder_ringkas || {};
  el.innerHTML = `<p class="dsb-sub">Sepuluh pencari data mengumpulkan bahan dari sumber yang berbeda. Statusnya dihitung dari data yang benar-benar masuk hari ini.
    ${r.aktif !== undefined ? `<b>${angka(r.aktif)}</b> dari ${f.length} sudah mengirim data.` : ""}</p>
    <div class="gulir-tabel"><table class="tabel-kecil dsb-tabel-tata"><thead><tr><th>Pencari data</th><th>Status</th><th>Data terakhir</th></tr></thead><tbody>
    ${f.map((x) => `<tr><td><details><summary><b>${esc(x.nama)}</b><span class="meta-kecil"> · ${esc(x.objek)}</span></summary>
      ${x.alasan ? `<p class="meta-kecil">${esc(x.alasan)}</p>` : ""}${daftarGerbang(x.gerbang || [])}
      <p class="meta-kecil">Bila gagal: ${esc(x.tindakan_gagal || "-")}</p></details></td>
      <td>${lencana(x.status)}</td><td class="meta-kecil">${x.data_terakhir ? esc(tgl(x.data_terakhir)) : "–"}</td></tr>`).join("")}
    </tbody></table></div>`;
}

export function gambarPembersihan(el, A) {
  const t = A.pembersihan || [];
  if (!t.length) { el.innerHTML = '<p class="meta-kecil">Hasil pembersihan belum tersedia.</p>'; return; }
  const lulus = t.filter((x) => x.status === "lulus").length;
  el.innerHTML = `<p class="dsb-sub">Setiap data melewati delapan pemeriksaan sebelum dipakai. <b>${lulus}</b> dari ${t.length} tahap lolos semua syaratnya.</p>
    <ol class="dsb-tahap">${t.map((x) => `<li><details><summary><b>${esc(x.nama)}</b> ${lencana(x.status)}</summary>
      <p class="meta-kecil">${esc(x.proses)}</p>${daftarGerbang(x.gerbang || [])}${x.catatan ? `<p class="meta-kecil">${esc(x.catatan)}</p>` : ""}</details></li>`).join("")}</ol>`;
}

export function gambarEws(el, A) {
  const e = A.ews;
  if (!e || e.recall === null || e.recall === undefined) {
    el.innerHTML = '<p class="meta-kecil">Peringatan dini belum bisa diuji: riwayat harga belum cukup panjang.</p>';
    return;
  }
  const p = e.parameter || {};
  const baris = [
    ["Lonjakan yang tertangkap", "recall", persen0(e.recall), `${angka(e.episode_tertangkap)} dari ${angka(e.episode_uji)} lonjakan`, e.recall >= TARGET_EWS.recall, "≥ 88%"],
    ["Peringatan yang tepat", "precision", persen0(e.precision), `dari ${angka(e.alarm_uji)} peringatan`, null, "-"],
    ["Nilai gabungan", "F1", persen0(e.f1), "keseimbangan dua angka di atas", e.f1 >= TARGET_EWS.f1, "≥ 88%"],
    ["Peringatan keliru di hari biasa", "false positive rate", persen0(e.false_positive_rate, 1), "makin kecil makin baik", e.false_positive_rate <= TARGET_EWS.fpr, "≤ 10%"],
  ];
  el.innerHTML = `<p class="dsb-sub">Sistem memberi peringatan bila kenaikan harian tidak biasa. Cara ini diuji pada riwayat harga
    ${e.periode_uji ? `${esc(tgl(e.periode_uji[0]))} sampai ${esc(tgl(e.periode_uji[1]))}` : ""}, masa yang tidak dipakai untuk menyetel ambangnya.</p>
    <table class="tabel-kecil"><thead><tr><th>Ukuran</th><th class="angka">Hasil</th><th>Target</th><th></th></tr></thead><tbody>
    ${baris.map(([n, istilah, nilai, sub, ok, tgt]) => `<tr><td>${esc(n)} <span class="meta-kecil">(${esc(istilah)})</span><div class="meta-kecil">${esc(sub)}</div></td>
      <td class="angka"><b>${nilai}</b></td><td class="meta-kecil">${esc(tgt)}</td><td>${tanda(ok)}</td></tr>`).join("")}</tbody></table>
    <p class="meta-kecil">Lonjakan dihitung bila harga naik melewati batas kelompoknya (5%, 10%, atau 15% di atas harga normal 28 hari).
    Pengaturan terpilih: ambang z ${esc(String(p.z_ambang ?? "-"))}, toleransi ${esc(String(p.toleransi_hari ?? "-"))} hari kerja.
    ${e.f1 !== null && e.f1 < TARGET_EWS.f1 ? "Peringatan masih cukup sering muncul tanpa lonjakan sungguhan, jadi setiap peringatan perlu dicek ke pasar sebelum ditindaklanjuti." : ""}</p>`;
}

const SATU = (nama) => String(nama || "").replace("Kabupaten ", "").replace("Provinsi ", "");

export function gambarBandingWilayah(el, judulEl, A, v) {
  if (!v) return;
  judulEl.textContent = `Perbandingan wilayah · ${v.nama}`;
  judulEl.title = judulEl.textContent;
  const per = (A.banding_wilayah || {})[v.kode];
  if (v.sumber?.pengganti) {
    el.innerHTML = `<p class="meta-kecil">${esc(v.sumber.catatan || "Varian ini memakai harga wilayah lain.")} Perbandingan dengan wilayah lain tidak dihitung supaya tidak menyesatkan.</p>`;
    return;
  }
  if (!per || !Object.keys(per).length) {
    el.innerHTML = '<p class="meta-kecil">Belum ada harga wilayah pembanding yang cukup panjang (minimal 30 hari yang sama).</p>';
    return;
  }
  const kol = Object.entries(per);
  const sel = (fn) => kol.map(([, b]) => `<td>${b.identik ? "sama persis" : fn(b)}</td>`).join("");
  const arah = (s) => !s ? "–" : s.searah ? "searah" : "berbeda arah";
  const lead = (b) => {
    const l = b.lead_lag;
    if (!l) return "–";
    if (l.lag_hari === 0) return "bergerak bersamaan";
    return l.lag_hari > 0 ? `${esc(SATU(b.nama))} lebih dulu ${l.lag_hari} hari` : `Bengkulu Tengah lebih dulu ${-l.lag_hari} hari`;
  };
  const selisih = (b) => b.spread_rp === undefined ? "–"
    : `Rp${angka(Math.abs(b.spread_rp))} (${angka(Math.abs(b.spread_persen), 1)}%) ${b.spread_rp > 0 ? "lebih mahal" : b.spread_rp < 0 ? "lebih murah" : "sama"} di Bengkulu Tengah`;
  el.innerHTML = `<p class="dsb-sub">Harga Bengkulu Tengah dibandingkan dengan wilayah tetangga dari sumber yang sama (${esc(kol.map(([, b]) => b.sumber).filter(Boolean)[0] || "-")}).</p>
    <div class="gulir-tabel"><table class="tabel-kecil dsb-tabel-tata"><thead><tr><th>Ukuran</th>${kol.map(([, b]) => `<th>${esc(SATU(b.nama))}</th>`).join("")}</tr></thead><tbody>
      <tr><td>Selisih harga terakhir <span class="meta-kecil">(spread)</span></td>${sel(selisih)}</tr>
      <tr><td>Arah harga 30 hari <span class="meta-kecil">(slope)</span></td>${sel((b) => arah(b.slope_30))}</tr>
      <tr><td>Arah harga 90 hari <span class="meta-kecil">(slope)</span></td>${sel((b) => arah(b.slope_90))}</tr>
      <tr><td>Kekompakan naik-turun 90 hari <span class="meta-kecil">(korelasi Spearman)</span></td>${sel((b) => b.spearman_90 === null || b.spearman_90 === undefined ? "–" : `${angka(b.spearman_90, 2)} (${esc(b.kekuatan)})`)}</tr>
      <tr><td>Siapa bergerak lebih dulu <span class="meta-kecil">(lead-lag ±14 hari)</span></td>${sel(lead)}</tr>
      <tr><td>Gejolak harga <span class="meta-kecil">(rasio volatilitas)</span></td>${sel((b) => b.rasio_volatilitas === undefined ? "–" : `${angka(b.rasio_volatilitas, 2)}, ${esc(String(b.volatilitas).replace("target", "Bengkulu Tengah"))}`)}</tr>
      <tr><td>Kemiripan pola mingguan</td>${sel((b) => b.kemiripan_mingguan === null || b.kemiripan_mingguan === undefined ? "–" : angka(b.kemiripan_mingguan, 2))}</tr>
      <tr><td>Kemiripan bentuk grafik 90 hari <span class="meta-kecil">(DTW, makin kecil makin mirip)</span></td>${sel((b) => b.dtw_90 === null || b.dtw_90 === undefined ? "–" : angka(b.dtw_90, 3))}</tr>
      <tr><td>Selisih tidak biasa? <span class="meta-kecil">(z-score disparitas)</span></td>${sel((b) => b.z_disparitas === undefined ? "–" : `${angka(b.z_disparitas, 1)}${b.perlu_tinjau ? " · perlu ditinjau" : " · wajar"}`)}</tr>
    </tbody></table></div>`;
}

export function gambarKonsensus(el, A) {
  const k = A.konsensus;
  if (!k || k.skor === null || k.skor === undefined) {
    el.innerHTML = `<p class="meta-kecil">${esc(k?.alasan || "Belum ada dua sumber harga untuk wilayah dan tanggal yang sama.")}</p>`;
    return;
  }
  const nama = Object.fromEntries((A.varian || []).map((v) => [v.kode, v.nama]));
  const per = Object.entries(k.per_varian || {});
  el.innerHTML = `<p class="dsb-sub">${esc(k.keterangan || "")}</p>
    <div class="dsb-konsensus-skor"><strong>${angka(k.skor, 2)}</strong> ${lencana(k.status)}<span class="meta-kecil">target ≥ 0,80 · ${angka(k.pasangan)} pasangan harga, ${angka(k.periode_hari)} hari terakhir</span></div>
    <p class="meta-kecil">Selisih tengah antara dua sumber: <b>${angka(k.median_selisih_persen, 1)}%</b>. Dianggap sepakat bila selisihnya paling banyak ${angka(k.ambang_selisih_persen)}%.
      Komponen: kesepakatan ${persen0(k.komponen?.kesepakatan)}, kesegaran ${persen0(k.komponen?.kesegaran)}, cakupan varian ${persen0(k.komponen?.cakupan_varian)}.</p>
    ${per.length ? `<details><summary class="meta-kecil">Rincian per varian (${per.length})</summary><div class="gulir-tabel"><table class="tabel-kecil"><thead><tr><th>Varian</th><th class="angka">Pasangan</th><th class="angka">Selisih tengah</th><th class="angka">Sepakat</th></tr></thead><tbody>
      ${per.map(([kode, x]) => `<tr><td>${esc(nama[kode] || kode)}</td><td class="angka">${angka(x.pasangan)}</td><td class="angka">${angka(x.median_selisih_persen, 1)}%</td><td class="angka">${angka(x.sepakat_persen, 0)}%</td></tr>`).join("")}
    </tbody></table></div></details>` : ""}`;
}

export function gambarRantai(el, A) {
  const r = A.rantai_harga || [];
  if (!r.length) { el.innerHTML = '<p class="meta-kecil">Harga produsen dan pedagang besar belum tersedia.</p>'; return; }
  const nama = Object.fromEntries((A.varian || []).map((v) => [v.kode, v.nama]));
  const jenis = ["Produsen", "Pedagang besar", "Pasar tradisional", "Pasar modern"];
  const nilai = (x, j) => x.harga[j] ? `Rp${angka(x.harga[j].harga)}` : "–";
  el.innerHTML = `<p class="dsb-sub">Harga terakhir di tiap mata rantai dari PIHPS Bank Indonesia. Marjin menunjukkan berapa persen harga bertambah dari produsen sampai pembeli di pasar.</p>
    <div class="gulir-tabel"><table class="tabel-kecil dsb-tabel-tata"><thead><tr><th>Varian</th>${jenis.map((j) => `<th class="angka">${j}</th>`).join("")}<th class="angka">Marjin total</th></tr></thead><tbody>
    ${r.map((x) => `<tr><td>${esc(nama[x.kode] || x.kode)}</td>${jenis.map((j) => `<td class="angka">${nilai(x, j)}</td>`).join("")}<td class="angka">${x.marjin_total_persen === undefined ? "–" : `${angka(x.marjin_total_persen, 1)}%`}</td></tr>`).join("")}
    </tbody></table></div>`;
}

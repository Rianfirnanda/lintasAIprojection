// Panel mutu data dan peringatan dini di Dashboard Internal (dalam tab): 10 pencari data (AI Data Finder), 8 tahap
// pembersihan, peringatan dini lonjakan harga (EWS), perbandingan antarwilayah, kecocokan antar-sumber, dan rantai harga.
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

const tab = (id, label, aktif = false) => `<button type="button" role="tab" id="dsb-t-${id}" aria-controls="dsb-p-${id}" aria-selected="${aktif}" tabindex="${aktif ? 0 : -1}">${label}<span class="dsb-tab-lencana" id="dsb-b-${id}"></span></button>`;
const panel = (id, isi, aktif = false) => `<div class="dsb-panel" role="tabpanel" id="dsb-p-${id}" aria-labelledby="dsb-t-${id}"${aktif ? "" : " hidden"}>${isi}</div>`;

export const KERANGKA_TATA = `
<section class="dsb-kartu dsb-tab" data-tab>
  <div class="dsb-tab-kepala"><h2>Mutu data dan peringatan dini</h2>
    <div class="dsb-tab-daftar" role="tablist" aria-label="Mutu data dan peringatan dini">
      ${tab("finder", "Pencari data", true)}${tab("bersih", "Pembersihan")}${tab("ews", "Peringatan dini")}${tab("wil", "Antarwilayah")}${tab("konsensus", "Kecocokan sumber")}${tab("rantai", "Rantai harga")}
    </div></div>
  ${panel("finder", '<div id="dsb-finder"></div>', true)}
  ${panel("bersih", '<div id="dsb-bersih"></div>')}
  ${panel("ews", '<div id="dsb-ews"></div>')}
  ${panel("wil", '<h3 class="sub-judul" id="dsb-judul-wil">Perbandingan dengan wilayah lain</h3><div id="dsb-wil"></div>')}
  ${panel("konsensus", '<div id="dsb-konsensus"></div>')}
  ${panel("rantai", '<div id="dsb-rantai"></div>')}
</section>`;

/** Tab yang bisa dipakai dengan tetikus dan papan ketik (panah kiri/kanan, Home, End). Grafik di panel yang baru tampil
 * diukur ulang supaya ukurannya pas. Tab terakhir yang dibuka diingat di peramban ini saja. */
export function pasangTab(akar) {
  akar.querySelectorAll("[data-tab]").forEach((bagian, i) => {
    const tombol = [...bagian.querySelectorAll('[role="tab"]')];
    const kunci = `lintas-tab-${i}`;
    const buka = (t, fokus = false) => {
      tombol.forEach((x) => {
        const aktif = x === t;
        x.setAttribute("aria-selected", String(aktif));
        x.tabIndex = aktif ? 0 : -1;
        const p = bagian.querySelector(`#${x.getAttribute("aria-controls")}`);
        if (p) p.hidden = !aktif;
      });
      if (fokus) t.focus();
      const p = bagian.querySelector(`#${t.getAttribute("aria-controls")}`);
      p?.querySelectorAll("canvas").forEach((c) => window.Chart?.getChart(c)?.resize());
      try { localStorage.setItem(kunci, t.id); } catch { /* penyimpanan peramban tidak tersedia */ }
    };
    bagian.addEventListener("click", (e) => { const t = e.target.closest('[role="tab"]'); if (t && tombol.includes(t)) buka(t); });
    bagian.querySelector('[role="tablist"]').addEventListener("keydown", (e) => {
      const i0 = tombol.indexOf(document.activeElement);
      if (i0 < 0) return;
      const ke = { ArrowRight: i0 + 1, ArrowLeft: i0 - 1, Home: 0, End: tombol.length - 1 }[e.key];
      if (ke === undefined) return;
      e.preventDefault();
      buka(tombol[(ke + tombol.length) % tombol.length], true);
    });
    let simpan = null;
    try { simpan = localStorage.getItem(kunci); } catch { simpan = null; }
    const awal = tombol.find((t) => t.id === simpan);
    if (awal) buka(awal);
  });
}

export function gambarFinder(el, A) {
  const f = A.finder || [];
  if (!f.length) { el.innerHTML = '<p class="meta-kecil">Status pencari data belum tersedia.</p>'; return; }
  const hitung = (st) => f.filter((x) => x.status === st).length;
  // Pencari data yang berjalan tampil sebagai ubin. Yang belum tersambung (butuh kunci, data instansi lain, atau isian petugas)
  // dikumpulkan dalam satu baris yang bisa dibuka, lengkap dengan apa yang dibutuhkan, supaya tidak tampak seperti fitur mati.
  const jalan = f.filter((x) => x.status !== "menunggu");
  const belum = f.filter((x) => x.status === "menunggu");
  const ubin = (x) => {
    const [kelas, teks] = STATUS[x.status] || STATUS.menunggu;
    return `<details class="dsb-finder ${kelas}"><summary><i class="dsb-titik-status ${kelas}"></i><b>${esc(x.nama)}</b>
        <span class="meta-kecil">${esc(x.objek)}</span><span class="dsb-finder-kaki"><span class="lencana ${kelas}">${teks}</span><span class="meta-kecil">${x.data_terakhir ? esc(tgl(x.data_terakhir)) : "belum ada data"}</span></span></summary>
        ${x.alasan ? `<p class="meta-kecil">${esc(x.alasan)}</p>` : ""}${daftarGerbang(x.gerbang || [])}<p class="meta-kecil">Bila gagal: ${esc(x.tindakan_gagal || "-")}</p></details>`;
  };
  el.innerHTML = `<div class="dsb-ringkas-baris">
      <span class="dsb-angka-besar">${angka(jalan.length)}</span><span class="dsb-sub">pencari data berjalan dan mengirim data</span>
      <span class="dsb-titik-ket"><i class="baik"></i>${hitung("lulus")} berjalan baik</span><span class="dsb-titik-ket"><i class="sedang"></i>${hitung("perlu_perhatian") + hitung("tinjau")} perlu perhatian</span>
      ${hitung("gagal") ? `<span class="dsb-titik-ket"><i class="tinggi"></i>${hitung("gagal")} belum lolos</span>` : ""}</div>
    <div class="dsb-ubin-finder">${jalan.map(ubin).join("")}</div>
    ${belum.length ? `<details class="dsb-finder-belum"><summary>${belum.length} pencari data dari rancangan belum tersambung karena butuh data atau izin dari luar sistem</summary>
      <ul>${belum.map((x) => `<li><b>${esc(x.nama)}</b>: ${esc(x.alasan || x.objek)}</li>`).join("")}</ul></details>` : ""}`;
}

export function gambarPembersihan(el, A) {
  const t = A.pembersihan || [];
  if (!t.length) { el.innerHTML = '<p class="meta-kecil">Hasil pembersihan belum tersedia.</p>'; return; }
  const lulus = t.filter((x) => x.status === "lulus").length;
  el.innerHTML = `<div class="dsb-ringkas-baris"><span class="dsb-angka-besar">${lulus}<small>/${t.length}</small></span><span class="dsb-sub">tahap pemeriksaan lolos semua syaratnya. Klik tahap untuk melihat syaratnya.</span></div>
    <ol class="dsb-tahap">${t.map((x, i) => { const [kelas] = STATUS[x.status] || STATUS.menunggu; return `<li class="${kelas}"><details><summary><span class="dsb-tahap-no">${i + 1}</span><b>${esc(x.nama)}</b> ${lencana(x.status)}</summary>
      <p class="meta-kecil">${esc(x.proses)}</p>${daftarGerbang(x.gerbang || [])}${x.catatan ? `<p class="meta-kecil">${esc(x.catatan)}</p>` : ""}</details></li>`; }).join("")}</ol>`;
}

export function gambarEws(el, A) {
  const e = A.ews;
  if (!e || e.recall === null || e.recall === undefined) {
    el.innerHTML = '<p class="meta-kecil">Peringatan dini belum bisa diuji: riwayat harga belum cukup panjang.</p>';
    return;
  }
  const p = e.parameter || {};
  const ubin = [
    ["Lonjakan tertangkap", e.recall, `${angka(e.episode_tertangkap)} dari ${angka(e.episode_uji)}`, e.recall >= TARGET_EWS.recall, "target ≥ 88%", TARGET_EWS.recall],
    ["Peringatan tepat", e.precision, `dari ${angka(e.alarm_uji)} peringatan`, null, "", null],
    ["Nilai gabungan (F1)", e.f1, "keseimbangan keduanya", e.f1 >= TARGET_EWS.f1, "target ≥ 88%", TARGET_EWS.f1],
    ["Keliru di hari biasa", e.false_positive_rate, "makin kecil makin baik", e.false_positive_rate <= TARGET_EWS.fpr, "target ≤ 10%", TARGET_EWS.fpr],
  ];
  el.innerHTML = `<p class="dsb-sub">Diuji pada ${e.periode_uji ? `${esc(tgl(e.periode_uji[0]))} sampai ${esc(tgl(e.periode_uji[1]))}` : "masa uji"}, masa yang tidak dipakai untuk menyetel ambang.</p>
    <div class="dsb-ubin-ews">${ubin.map(([n, x, sub, ok, tgt, garis]) => `<div class="dsb-ews ${ok === false ? "kuning" : ok ? "hijau" : ""}">
      <span class="dsb-label">${esc(n)}</span><strong>${persen0(x, x !== null && x < 0.1 ? 1 : 0)}</strong>
      <div class="dsb-meter ${ok === false ? "kuning" : ok ? "hijau" : "biru"}"><span style="width:${Math.min(100, (x ?? 0) * 100).toFixed(1)}%"></span>${garis === null ? "" : `<i style="left:${garis * 100}%"></i>`}</div>
      <span class="meta-kecil">${esc(sub)}${tgt ? ` · ${esc(tgt)}` : ""}</span>${ok === null ? "" : tanda(ok)}</div>`).join("")}</div>
    ${waktuPeringatan(e.waktu_peringatan)}
    <details><summary class="meta-kecil">Cara kerja dan pengaturan per kelompok gejolak</summary>
    <p class="meta-kecil">Lonjakan dihitung bila harga naik melewati batas kelompoknya (5%, 10%, atau 15% di atas harga normal 28 hari).
    ${p.per_kelas ? "" : `Pengaturan terpilih: ambang z ${esc(String(p.z_ambang ?? "-"))}, toleransi ${esc(String(p.toleransi_hari ?? "-"))} hari kerja.`}</p>
    ${p.per_kelas ? `<div class="gulir-tabel"><table class="tabel-kecil">
      <thead><tr><th>Kelompok</th><th class="angka">Ambang z</th><th class="angka">Sudah naik</th><th class="angka">Toleransi</th><th class="angka">Nilai gabungan uji</th></tr></thead><tbody>
      ${Object.entries(p.per_kelas).map(([k, x]) => `<tr><td>${esc(NAMA_KELAS[k] || k)}</td><td class="angka">${angka(x.z_ambang, 1)}</td>
        <td class="angka">${angka(x.porsi_level * 100, 0)}% dari batas</td><td class="angka">${angka(x.toleransi_hari)} hari</td>
        <td class="angka">${e.per_kelas?.[k]?.f1 == null ? "–" : persen0(e.per_kelas[k].f1)}</td></tr>`).join("")}</tbody></table></div>` : ""}</details>`;
}

const NAMA_KELAS = { rendah: "Gejolak rendah (beras, gula, minyak)", sedang: "Gejolak sedang (daging, telur, bawang putih)", tinggi: "Gejolak tinggi (cabai, bawang merah)" };

function waktuPeringatan(w) {
  if (!w) return "";
  const total = (w.sebelum || 0) + (w.tepat || 0) + (w.sesudah || 0);
  if (!total) return "";
  const bag = (x) => (x / total * 100).toFixed(1);
  return `<div class="dsb-waktu-peringatan"><span class="dsb-label">Kapan peringatan muncul (${angka(total)} lonjakan tertangkap)</span>
    <div class="dsb-arah-batang"><span class="turun" style="flex:${bag(w.sebelum || 0)}" title="Sebelum harga melonjak"></span><span class="tepat" style="flex:${bag(w.tepat || 0)}" title="Hari pertama lonjakan"></span><span class="naik" style="flex:${bag(w.sesudah || 0)}" title="Sesudahnya"></span></div>
    <div class="dsb-legenda-mini"><span><i class="turun"></i>Sebelum: ${angka(w.sebelum)}</span><span><i class="tepat"></i>Hari pertama: ${angka(w.tepat)}</span><span><i class="naik"></i>Sesudahnya: ${angka(w.sesudah)}</span></div></div>`;
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

// Dasbor Analitik: tabel proyeksi 21 varian, grafik, diagnostik, kinerja model, hari raya, proyeksi periodik, dan jejak data.
// Semua angka dibaca dari analitik.json, proyeksi_acara.json, proyeksi_periodik.json, dan seri/<varian>.json.
import { ind } from "./peran.js";
import { pasangKerangka, muatJSON, esc, persen, angka, rp, tgl, kelasPerubahan, tampilkanGalat, keCSV, unduhTeks, warna, saatTemaBerubah } from "./app.js";
import { gambarGrafikHarga, legendaDashboard, potongSeri } from "./grafik.js";

const $ = (id) => document.getElementById(id);
const meta = await pasangKerangka("dasbor.html");

let A, ACARA, PERIODIK;
try {
  [A, ACARA, PERIODIK] = await Promise.all([muatJSON("analitik.json"), muatJSON("proyeksi_acara.json"), muatJSON("proyeksi_periodik.json")]);
} catch (e) {
  tampilkanGalat(document.querySelector("main"), e);
  throw e;
}

const NAMA_KELOMPOK = { pokok: "Pokok", protein: "Protein", volatil: "Volatil", pabrikan: "Pabrikan" };
const NAMA_PERCAYA = { tinggi: "Tinggi", sedang: "Sedang", rendah: "Rendah" };
const URUT_PERCAYA = { tinggi: 3, sedang: 2, rendah: 1 };
const S = { kode: null, h: 30, hari: 180, urut: { kunci: "nama", arah: 1 }, periode: "triwulanan", grafik: null, grafikUji: null, grafikPeriodik: null, seri: {} };
const tingkat = A.tingkat_interval ?? 0.8;
const pesentingkat = Math.round(tingkat * 100);

const NAMA_PENDEK = { naif: "Harga terakhir", rata7: "Rata-rata 7 hari", holt_redam: "Tren melandai (Holt)", ses: "Penghalusan eksponensial",
  hari_raya: "Pola hari raya", ml_challenger: "Machine learning", ensemble: "Gabungan (ensemble)" };
const lencanaStatus = (s) => s === "valid" ? '<span class="lencana baik">Valid</span>' : '<span class="lencana sedang">Eksperimen</span>';
const lencanaPercaya = (p) => `<span class="lencana ${p === "tinggi" ? "baik" : p === "sedang" ? "rendah" : "sedang"}">${NAMA_PERCAYA[p] || "–"}</span>`;
const tanda = (ok) => ok === null || ok === undefined ? '<span class="tanda tunggu" title="Belum bisa dinilai">–</span>'
  : ok ? '<span class="tanda ok" title="Lolos">✓</span>' : '<span class="tanda gagal" title="Belum lolos">✕</span>';
const nilaiAtau = (x, f = (v) => v) => x === null || x === undefined ? '<span class="menunggu">menunggu data</span>' : f(x);
const pendek = (h) => (h ? String(h).slice(0, 8) : "–");

/* ---------- kepala dan indikator */
function kepala() {
  const w = A.wilayah;
  const sementara = meta?.data_sementara;
  $("wilayah").innerHTML = sementara
    ? `${esc(w.nama)} <span>Data asli sementara. Harga Bengkulu Tengah, Kepahiang, dan Kota Bengkulu terisi setelah datanya masuk.</span>`
    : `${esc(w.nama)} <span>Pembanding: Kepahiang dan Kota Bengkulu</span>`;
  $("cap").innerHTML = A.mode_demo
    ? '<span class="lencana sedang">Data contoh</span>'
    : `<span class="lencana baik">Data asli</span> <span class="meta-kecil">sampai ${esc(tgl(A.dibuat_untuk, true))}</span>`;
  const k = A.kpi;
  $("kpi").innerHTML = [
    ind({ i: "database", label: "Sumber data aktif", nilai: `${k.sumber_aktif}/${k.sumber_terdaftar}`, sub: "yang sudah mengirim harga" }),
    ind({ i: "cari", warna: "oranye", label: "Skor kesepakatan sumber", nilai: k.skor_konsensus === null ? '<span style="font-size:1.05rem">Menunggu data</span>' : angka(k.skor_konsensus, 1), sub: esc(k.keterangan_konsensus || "Kecocokan harga antar sumber") }),
    ind({ i: "jam", warna: k.kesegaran === "segar" ? "hijau" : "oranye", label: "Kesegaran data", nilai: k.hari_tertinggal === null ? "–" : `${k.hari_tertinggal}`, kecil: " hari", sub: `Data terakhir ${esc(tgl(A.dibuat_untuk))}` }),
    ind({ i: "kubus", warna: "hijau", label: "Kelengkapan data", nilai: `${k.varian_berdata}/${k.varian_aktif}`, sub: `${angka(k.kelengkapan_persen, 1)}% harga terisi`, meter: k.varian_aktif ? k.varian_berdata / k.varian_aktif * 100 : null, meterWarna: "hijau" }),
    ind({ i: "perisai", warna: k.varian_eksperimen ? "oranye" : "hijau", label: "Status audit model", nilai: `${k.varian_valid}/${k.varian_berdata}`, kecil: " Valid", sub: `${k.varian_eksperimen} Eksperimen · ${angka(k.perlu_validasi)} data menunggu validasi` }),
    ind({ i: "target", warna: "hijau", label: "Rata-rata meleset (uji akhir)", nilai: k.smape_median_holdout === null ? "–" : `${angka(k.smape_median_holdout, 2)}%`, sub: "median 21 varian, 90 hari terakhir" }),
  ].join("");
}

/* ---------- pilihan */
function isiPilihan() {
  $("origin").innerHTML = `<option>${esc(tgl(A.dibuat_untuk, true))} (data terakhir)</option>`;
  $("varian").innerHTML = A.varian.map((v) => `<option value="${esc(v.kode)}">${esc(v.nama)}</option>`).join("");
}

/* ---------- tabel */
const proy = (v, h) => v.proyeksi?.[String(h)] || null;
const nilaiUrut = {
  nama: (v) => v.nama, harga: (v) => v.harga_aktual ?? -1, h7: (v) => proy(v, 7)?.prediksi ?? -1, h14: (v) => proy(v, 14)?.prediksi ?? -1,
  h30: (v) => proy(v, 30)?.prediksi ?? -1, rentang: (v) => { const p = proy(v, S.h); return p ? p.atas - p.bawah : -1; },
  ubah: (v) => proy(v, S.h)?.perubahan_persen ?? -999, model: (v) => v.nama_model, status: (v) => v.status, percaya: (v) => URUT_PERCAYA[v.kepercayaan] || 0,
};

function daftarTampil() {
  const kel = $("kelompok").value, st = $("status").value;
  const u = nilaiUrut[S.urut.kunci];
  return A.varian.filter((v) => (!kel || v.kelompok === kel) && (!st || v.status === st))
    .sort((a, b) => { const x = u(a), y = u(b); return (x < y ? -1 : x > y ? 1 : 0) * S.urut.arah; });
}

function gambarTabel() {
  const baris = daftarTampil();
  const sel = (v, h) => {
    const p = proy(v, h);
    return p ? `<td class="angka">${rp(p.prediksi)}</td>` : '<td class="angka menunggu">–</td>';
  };
  document.querySelector("#tabel tbody").innerHTML = baris.map((v) => {
    const p = proy(v, S.h);
    return `<tr data-kode="${esc(v.kode)}" class="${v.kode === S.kode ? "terpilih" : ""}" tabindex="0">
      <td><strong>${esc(v.nama)}</strong><br><span class="meta-kecil">${esc(NAMA_KELOMPOK[v.kelompok] || v.kelompok)} · per ${esc(v.satuan)}</span></td>
      <td class="angka">${rp(v.harga_aktual)}</td>${sel(v, 7)}${sel(v, 14)}${sel(v, 30)}
      <td class="angka">${p ? `${rp(p.bawah)} – ${rp(p.atas)}` : "–"}</td>
      <td class="angka ${kelasPerubahan(p?.perubahan_persen ?? null, 3)}">${persen(p?.perubahan_persen, 1, true)}</td>
      <td class="meta-kecil" title="${esc(v.nama_model)}">${esc(NAMA_PENDEK[v.model] || v.nama_model)}</td>
      <td>${lencanaStatus(v.status)}</td><td>${lencanaPercaya(v.kepercayaan)}</td></tr>`;
  }).join("") || `<tr><td colspan="10" class="kosong">Tidak ada varian yang cocok dengan pilihan.</td></tr>`;
  document.querySelector('#tabel th[data-urut="rentang"]').textContent = `Rentang ${pesentingkat}% (${S.h} hari)`;
  document.querySelector('#tabel th[data-urut="ubah"]').textContent = `Perubahan ${S.h} hari`;
  document.querySelectorAll("#tabel th[data-urut]").forEach((th) => {
    th.setAttribute("aria-sort", th.dataset.urut === S.urut.kunci ? (S.urut.arah > 0 ? "ascending" : "descending") : "none");
  });
  const valid = A.varian.filter((v) => v.status === "valid").length;
  $("catatan-status").innerHTML = `<b>${valid}</b> dari ${A.varian.length} varian berstatus <b>Valid</b>. <b>Eksperimen</b> berarti ada syarat uji yang belum lolos, jadi angkanya bahan pertimbangan, bukan angka resmi. Tingkat keyakinan: Tinggi bila semua syarat lolos, Sedang bila hanya satu syarat gagal, Rendah bila lebih.`;
}

function ekspor() {
  const kolom = ["kode", "varian", "kelompok", "satuan", "tanggal_harga", "harga_aktual", "prediksi_7", "bawah_7", "atas_7", "prediksi_14", "bawah_14", "atas_14",
    "prediksi_30", "bawah_30", "atas_30", "perubahan_30_persen", "cara_prakiraan", "status_validasi", "tingkat_keyakinan", "smape_uji_akhir", "cakupan_uji_akhir"];
  const baris = daftarTampil().map((v) => {
    const o = { kode: v.kode, varian: v.nama, kelompok: v.kelompok, satuan: v.satuan, tanggal_harga: v.tanggal_aktual, harga_aktual: v.harga_aktual,
      perubahan_30_persen: proy(v, 30)?.perubahan_persen, cara_prakiraan: v.nama_model, status_validasi: v.status, tingkat_keyakinan: v.kepercayaan,
      smape_uji_akhir: v.holdout?.smape, cakupan_uji_akhir: v.holdout?.cakupan_persen };
    for (const h of [7, 14, 30]) { const p = proy(v, h); o[`prediksi_${h}`] = p?.prediksi; o[`bawah_${h}`] = p?.bawah; o[`atas_${h}`] = p?.atas; }
    return o;
  });
  unduhTeks(`proyeksi_harga_${A.dibuat_untuk}.csv`, keCSV(kolom, baris));
}

/* ---------- varian terpilih */
async function pilih(kode, gulir = false) {
  S.kode = kode;
  $("varian").value = kode;
  gambarTabel();
  const v = A.varian.find((x) => x.kode === kode);
  if (!S.seri[kode]) {
    try { S.seri[kode] = await muatJSON(`seri/${kode}.json`); } catch { S.seri[kode] = null; }
  }
  gambarTren(v);
  ringkasVarian(v);
  wilayah(v);
  diagnostik(v);
  kinerja(v);
  gambarUji(v);
  pendorong(v);
  acaraVarian(v);
  periodik(v);
  rekomendasi(v);
  if (gulir) $("judul-tren").scrollIntoView({ behavior: "smooth", block: "start" });
}

function gambarTren(v) {
  $("judul-tren").textContent = `Tren dan proyeksi · ${v.nama}`;
  $("sub-tren").textContent = `Proyeksi ${S.h} hari dengan rentang ${pesentingkat}%. ${v.status === "valid" ? "Model lolos protokol validasi." : "Model berstatus Eksperimen."}`;
  $("legenda").innerHTML = legendaDashboard();
  if (S.grafik) { S.grafik.destroy(); S.grafik = null; }
  const seri = S.seri[v.kode];
  if (!seri || !window.Chart) { $("grafik-tren").replaceWith(Object.assign(document.createElement("canvas"), { id: "grafik-tren" })); return; }
  S.grafik = gambarGrafikHarga($("grafik-tren"), potongSeri(seri, S.hari), { gaya: "dashboard", horizon: S.h, tingkat });
}

function ringkasVarian(v) {
  $("sub-ringkas").textContent = `${v.kode} · ${NAMA_KELOMPOK[v.kelompok] || v.kelompok} · per ${v.satuan}`;
  const baris = [7, 14, 30].map((h) => {
    const p = proy(v, h);
    return p ? `<tr class="${h === S.h ? "terpilih" : ""}"><td>${h} hari<br><span class="meta-kecil">${esc(tgl(p.tanggal))}</span></td><td class="angka"><strong>${rp(p.prediksi)}</strong></td>
      <td class="angka">${rp(p.bawah)} – ${rp(p.atas)}</td><td class="angka ${kelasPerubahan(p.perubahan_persen, 3)}">${persen(p.perubahan_persen, 1, true)}</td></tr>` : "";
  }).join("");
  $("ringkas").innerHTML = `
    <dl class="dl"><dt>Harga aktual</dt><dd><strong>${rp(v.harga_aktual)}</strong> <span class="meta-kecil">${esc(tgl(v.tanggal_aktual))}</span></dd>
    <dt>Cara prakiraan</dt><dd>${esc(v.nama_model)}</dd><dt>Status</dt><dd>${lencanaStatus(v.status)} ${lencanaPercaya(v.kepercayaan)}</dd>
    <dt>Riwayat</dt><dd>${angka(v.jumlah_obs)} hari harga sejak ${esc(tgl(v.tanggal_awal))}</dd></dl>
    <div class="gulir-tabel"><table class="tabel-kecil"><thead><tr><th>Horizon</th><th class="angka">Prediksi</th><th class="angka">Rentang ${pesentingkat}%</th><th class="angka">Perubahan</th></tr></thead><tbody>${baris}</tbody></table></div>
    ${v.catatan?.length ? `<details><summary class="meta-kecil">Catatan mesin (${v.catatan.length})</summary><ul class="meta-kecil">${v.catatan.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></details>` : ""}
    ${kartuModel(v)}`;
}

function kartuModel(v) {
  const k = v.kartu_model;
  if (!k) return "";
  return `<details style="margin-top:8px"><summary class="meta-kecil"><b>Kartu model</b></summary>
    <dl class="dl" style="margin-top:8px"><dt>Tujuan</dt><dd>${esc(k.tujuan)}</dd>
    <dt>Data</dt><dd>${esc(k.data.wilayah)}, ${esc(k.data.sumber)}; ${esc(tgl(k.data.dari))} sampai ${esc(tgl(k.data.sampai))}; ${angka(k.data.jumlah_hari_berharga)} hari berharga</dd>
    <dt>Cara prakiraan</dt><dd>${esc(k.model.nama)}</dd>
    <dt>Cara memilih</dt><dd class="meta-kecil">${esc(k.model.cara_memilih)}</dd>
    <dt>Yang dicoba</dt><dd class="meta-kecil">${k.model.kandidat.map(esc).join("; ")}</dd></dl>
    <p class="meta-kecil" style="margin:8px 0 2px"><b>Keterbatasan</b></p><ul class="meta-kecil">${k.keterbatasan.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></details>`;
}

/* ---------- perbandingan wilayah */
function wilayah(v) {
  const seri = S.seri[v.kode];
  // Saat harga utama sementara adalah PIHPS Provinsi, garis pembanding PIHPS sama dengan target, jadi tidak ditampilkan dua kali.
  const pembanding = Object.entries(seri?.pembanding || {}).filter(([k]) => !(meta?.data_sementara && k === "PIHPS")).map(([, p]) => p);
  const terakhir = (arr) => { for (let i = arr.length - 1; i >= 0; i--) if (arr[i] !== null && arr[i] !== undefined) return arr[i]; return null; };
  const target = { nama: A.wilayah.nama, nilai: v.harga_aktual };
  const lain = pembanding.map((p) => ({ nama: p.nama, nilai: terakhir(p.nilai) })).filter((p) => p.nilai !== null);
  const kosong = ["Kepahiang", "Kota Bengkulu"].filter((n) => !lain.some((p) => p.nama.toLowerCase().includes(n.toLowerCase())));
  const semua = [target, ...lain];
  const maks = Math.max(...semua.map((x) => x.nilai || 0), 1);
  const batang = semua.map((x) => `<div class="bar-baris"><span class="bar-nama">${esc(x.nama)}</span><div class="bar"><span style="width:${(x.nilai / maks * 100).toFixed(1)}%"></span></div><span class="bar-nilai">${rp(x.nilai)}</span></div>`).join("");
  const menunggu = kosong.map((n) => `<div class="bar-baris menunggu-baris"><span class="bar-nama">${esc(n)}</span><div class="bar kosong-bar"></div><span class="bar-nilai menunggu">menunggu data</span></div>`).join("");
  $("wilayah-banding").innerHTML = batang + menunggu + (kosong.length ? `<p class="meta-kecil" style="margin-top:8px">${esc(A.pembanding_wilayah.keterangan || "Wilayah ini belum punya harga yang masuk ke sistem.")}</p>` : "");
  $("disparitas").innerHTML = lain.length
    ? `<table class="tabel-kecil"><thead><tr><th>Wilayah</th><th class="angka">Harga</th><th class="angka">Selisih</th></tr></thead><tbody>${lain.map((p) => {
      const d = v.harga_aktual ? (p.nilai / v.harga_aktual - 1) * 100 : null;
      return `<tr><td>${esc(p.nama)}</td><td class="angka">${rp(p.nilai)}</td><td class="angka ${kelasPerubahan(d, 3)}">${persen(d, 1, true)}</td></tr>`;
    }).join("")}</tbody></table>`
    : `<p class="menunggu-blok">Menunggu data. Selisih antar wilayah dihitung begitu harga wilayah pembanding masuk.</p>`;
}

/* ---------- diagnostik */
function diagnostik(v) {
  const d = v.diagnostik || {};
  const musiman = d.kekuatan_musiman;
  const kelasMusiman = musiman === null || musiman === undefined ? null : musiman < 0.3 ? "lemah" : musiman < 0.6 ? "sedang" : "kuat";
  const baris = [
    ["Uji ADF (akar unit)", nilaiAtau(d.adf_p, (x) => `p = ${angka(x, 3)}`), d.adf_p === null || d.adf_p === undefined ? null : d.adf_p < 0.05, "Stasioner bila p < 0,05"],
    ["Uji KPSS", nilaiAtau(d.kpss_p, (x) => (x <= 0.0101 ? "p ≤ 0,01" : x >= 0.0999 ? "p ≥ 0,10" : `p = ${angka(x, 3)}`)), d.kpss_p === null || d.kpss_p === undefined ? null : d.kpss_p > 0.05, "Stasioner bila p > 0,05"],
    ["Kesimpulan stasioneritas", nilaiAtau(d.stasioner, (x) => (x ? "Stasioner" : "Belum stasioner")), d.stasioner ?? null, "Harga cenderung bergerak mengikuti tren bila belum stasioner"],
    ["Pola mingguan", nilaiAtau(musiman, (x) => `${angka(x, 2)} (${kelasMusiman})`), null, "Kekuatan musiman 7 hari (STL), 0 sampai 1"],
    ["Rezim naik-turun harga", nilaiAtau(d.rezim_volatilitas, (x) => esc(x)), d.rezim_volatilitas ? d.rezim_volatilitas !== "tinggi" : null, "30 hari terakhir dibanding seluruh riwayat"],
    ["Pergeseran pola harga (PSI)", nilaiAtau(d.psi, (x) => angka(x, 3)), d.patahan_struktural === null || d.patahan_struktural === undefined ? null : !d.patahan_struktural, "PSI > 0,25 dianggap ada patahan struktural"],
    ["Kelengkapan data", nilaiAtau(v.kelengkapan_persen, (x) => persen(x, 1)), v.kelengkapan_persen === null || v.kelengkapan_persen === undefined ? null : v.kelengkapan_persen >= A.protokol.kelengkapan_min_persen, `Syarat minimal ${A.protokol.kelengkapan_min_persen}% (1 tahun terakhir)`],
  ];
  $("diagnostik").innerHTML = `<table class="tabel-kecil"><tbody>${baris.map(([a, b, ok, ket]) => `<tr><td>${a}<br><span class="meta-kecil">${esc(ket)}</span></td><td class="angka">${b}</td><td>${typeof ok === "boolean" || ok === null ? tanda(ok) : ""}</td></tr>`).join("")}</tbody></table>`;
}

/* ---------- kinerja model */
function kinerja(v) {
  const ho = v.holdout, va = v.validasi || {};
  $("sub-kinerja").textContent = ho
    ? `${ho.hari} hari terakhir disisihkan dan tidak dipakai memilih cara prakiraan. ${ho.jumlah_origin} titik awal, ${angka(ho.n)} pasangan prakiraan dan kenyataan.`
    : "Belum ada masa uji akhir untuk varian ini.";
  const syarat = (va.syarat || []).map((s) => `<tr><td>${esc(s.syarat)}</td><td class="angka">${s.nilai === null || s.nilai === undefined ? "–" : esc(typeof s.nilai === "number" ? angka(s.nilai, Number.isInteger(s.nilai) ? 0 : 2) : s.nilai)}</td><td class="angka meta-kecil">${esc(s.target)}</td><td>${tanda(s.lolos)}</td></tr>`).join("");
  let isi = `<div class="gulir-tabel"><table class="tabel-kecil"><thead><tr><th>Syarat</th><th class="angka">Hasil</th><th class="angka">Target</th><th></th></tr></thead><tbody>${syarat || '<tr><td colspan="4" class="kosong">Tidak ada syarat yang dinilai.</td></tr>'}</tbody></table></div>`;
  if (ho) {
    const dm = ho.uji_dm;
    const ph = ho.per_horizon || {};
    isi += `<dl class="dl" style="margin-top:10px">
      <dt>Lebih baik dari harga terakhir</dt><dd>${nilaiAtau(ho.perbaikan_vs_naif_persen, (x) => persen(x, 1, true))} <span class="meta-kecil">(menang di ${ho.menang_origin_vs_naif} dari ${ho.jumlah_origin} titik awal)</span></dd>
      <dt>Uji Diebold-Mariano</dt><dd>${dm && dm.p !== null ? `p = ${angka(dm.p, 3)} (n = ${dm.n})` : '<span class="menunggu">tidak berlaku untuk cara pembanding</span>'}</dd>
      ${["7", "14", "30"].filter((h) => ph[h]).map((h) => `<dt>Meleset ${h} hari</dt><dd>${persen(ph[h].smape, 2)} <span class="meta-kecil">(bias ${persen(ph[h].bias_persen, 2, true)}, n = ${ph[h].n})</span></dd>`).join("")}
    </dl>`;
  }
  if (va.gagal?.length) isi += `<p class="pesan peringatan" style="margin-top:10px">Belum lolos: ${va.gagal.map(esc).join(", ")}.</p>`;
  $("kinerja").innerHTML = isi;
}

function gambarUji(v) {
  if (S.grafikUji) { S.grafikUji.destroy(); S.grafikUji = null; }
  const wadah = $("grafik-uji")?.parentElement || document.querySelector("#grafik-uji-wadah");
  const t = v.holdout?.titik_h7 || [];
  if (!t.length || !window.Chart) {
    wadah.innerHTML = '<p class="menunggu-blok">Menunggu data. Masa uji akhir belum tersedia untuk varian ini.</p>';
    return;
  }
  wadah.innerHTML = '<canvas id="grafik-uji" role="img" aria-label="Prakiraan lawan kenyataan pada masa uji"></canvas>';
  const c = { a: warna("series-1"), p: warna("series-2"), grid: warna("grid"), muted: warna("muted") };
  S.grafikUji = new window.Chart($("grafik-uji"), {
    type: "line",
    data: { labels: t.map((x) => x.tanggal), datasets: [
      { label: "Kenyataan", data: t.map((x) => x.aktual), borderColor: c.a, backgroundColor: c.a, borderWidth: 2, pointRadius: 0, tension: 0 },
      { label: "Prakiraan 7 hari", data: t.map((x) => x.prediksi), borderColor: c.p, backgroundColor: c.p, borderWidth: 2, borderDash: [5, 4], pointRadius: 0, tension: 0 },
    ] },
    options: { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: true, labels: { boxWidth: 12, color: c.muted } }, tooltip: { callbacks: { title: (i) => tgl(i[0].label), label: (i) => `${rp(i.raw)}  ${i.dataset.label}` } } },
      scales: { x: { grid: { display: false }, ticks: { color: c.muted, maxRotation: 0, autoSkipPadding: 24, callback(val) { return tgl(this.getLabelForValue(val)); } } },
        y: { grid: { color: c.grid }, border: { display: false }, ticks: { color: c.muted, callback: (val) => new Intl.NumberFormat("id-ID").format(val) } } } },
  });
}

/* ---------- faktor terukur */
function pendorong(v) {
  const p = v.pendorong || [];
  $("pendorong").innerHTML = p.length
    ? `<ul class="daftar-pendorong">${p.map((x) => {
      const panah = x.arah === "naik" ? "▲" : x.arah === "turun" ? "▼" : x.arah === "bergeser" ? "◆" : "•";
      const kelas = x.arah === "naik" ? "naik" : x.arah === "turun" ? "turun" : "";
      const nilai = typeof x.nilai === "number" ? `${angka(x.nilai, x.satuan === "hari" ? 0 : 2)}${x.satuan ? (x.satuan === "%" ? "%" : ` ${x.satuan}`) : ""}` : esc(x.nilai);
      return `<li><span class="panah ${kelas}">${panah}</span><span class="pendorong-nama">${esc(x.nama)}</span><strong>${nilai}</strong></li>`;
    }).join("")}</ul>`
    : '<p class="menunggu-blok">Menunggu data. Belum ada faktor yang dapat diukur.</p>';
}

/* ---------- hari raya */
function acaraVarian(v) {
  const aktif = ACARA.acara.filter((a) => a.fase !== "belum_dimulai" && a.fase !== "selesai");
  const berikut = ACARA.acara.find((a) => a.fase === "belum_dimulai");
  $("sub-acara").textContent = `Menuju Hari H: dari H-7 dan H-3. Sesudah Hari H: H+3, H+7, H+14. Diuji dengan menyisihkan satu hari raya bergiliran (butuh minimal ${ACARA.aturan.minimal_acara} hari raya sejenis).`;
  let isi = "";
  if (berikut) {
    isi += `<div class="pesan" style="margin-bottom:12px"><b>${esc(berikut.nama)}</b>, ${esc(tgl(berikut.tanggal, true))} (${berikut.hari_menuju} hari lagi). Proyeksi menuju Hari H otomatis muncul mulai ${esc(tgl(berikut.proyeksi_mulai, true))} (H-7), karena dihitung dari harga pada saat itu, bukan dari tebakan jauh-jauh hari.</div>`;
  }
  for (const a of aktif) {
    const ent = a.varian.find((x) => x.kode === v.kode);
    if (!ent) continue;
    isi += `<h3 class="sub-judul">${esc(a.nama)} · ${esc(tgl(a.tanggal))}</h3><div class="gulir-tabel"><table class="tabel-kecil"><thead><tr><th>Titik</th><th class="angka">Harga asal</th><th class="angka">Prediksi</th><th class="angka">Rentang ${pesentingkat}%</th><th class="angka">Selisih</th><th class="angka">Kenyataan</th><th>Status</th></tr></thead><tbody>${ent.baris.map((b) => b.prediksi === null
      ? `<tr><td>${esc(b.kode)}</td><td class="angka">${rp(b.asal)}</td><td colspan="5" class="meta-kecil">${esc(b.alasan)}</td></tr>`
      : `<tr><td>${esc(b.kode)}<br><span class="meta-kecil">${esc(tgl(b.sasaran_tanggal))}</span></td><td class="angka">${rp(b.asal)}</td><td class="angka"><strong>${rp(b.prediksi)}</strong></td><td class="angka">${rp(b.bawah)} – ${rp(b.atas)}</td><td class="angka ${kelasPerubahan(b.delta_persen, 3)}">${rp(b.delta_rp)} (${persen(b.delta_persen, 1, true)})</td><td class="angka">${b.aktual ? rp(b.aktual) : "–"}</td><td>${lencanaStatus(b.status)}</td></tr>`).join("")}</tbody></table></div>`;
  }
  const ev = ACARA.evaluasi.filter((e) => e.kode === v.kode);
  const urutOffset = ["H-7", "H-3", "H+3", "H+7", "H+14"];
  const jenis = ev.map((e) => e.jenis);
  if (ev.length) {
    isi += `<h3 class="sub-judul">Uji pada hari raya yang sudah lewat · ${esc(v.nama)}</h3><div class="gulir-tabel"><table class="tabel-kecil"><thead><tr><th>Hari raya</th><th>Titik</th><th class="angka">Jumlah</th><th class="angka">Meleset</th><th class="angka">Meleset harga terakhir</th><th class="angka">Lebih baik</th><th class="angka">Tepat dalam rentang</th><th>Status</th></tr></thead><tbody>${ev.flatMap((e) => urutOffset.filter((o) => e.offset[o]).map((o) => {
      const x = e.offset[o];
      return x.smape === undefined
        ? `<tr><td>${esc(e.jenis)}</td><td>${o}</td><td class="angka">${x.n_acara}</td><td colspan="4" class="meta-kecil">${esc((x.gagal || []).join(", "))}</td><td>${lencanaStatus(x.status)}</td></tr>`
        : `<tr><td>${esc(e.jenis)}</td><td>${o}</td><td class="angka">${x.n_acara}</td><td class="angka">${persen(x.smape, 2)}</td><td class="angka">${persen(x.smape_naif, 2)}</td><td class="angka">${persen(x.perbaikan_vs_naif_persen, 1, true)}</td><td class="angka">${persen(x.cakupan_persen, 0)}</td><td>${lencanaStatus(x.status)}</td></tr>`;
    })).join("")}</tbody></table></div>
    <details style="margin-top:8px"><summary class="meta-kecil">Rincian per hari raya (harga asal, prediksi, kenyataan)</summary><div class="gulir-tabel"><table class="tabel-kecil"><thead><tr><th>Hari raya</th><th>Titik</th><th>Tanggal Hari H</th><th class="angka">Harga asal</th><th class="angka">Prediksi</th><th class="angka">Kenyataan</th><th>Dalam rentang</th></tr></thead><tbody>${ev.flatMap((e) => urutOffset.filter((o) => e.offset[o]?.rincian).flatMap((o) => e.offset[o].rincian.map((r) => `<tr><td>${esc(e.jenis)}</td><td>${o}</td><td>${esc(tgl(r.tanggal_hr))}</td><td class="angka">${rp(r.asal)}</td><td class="angka">${rp(r.prediksi)}</td><td class="angka">${rp(r.sasaran)}</td><td>${tanda(r.dalam_interval)}</td></tr>`))).join("")}</tbody></table></div></details>
    <p class="meta-kecil" style="margin-top:8px">Cara: harga asal dikalikan median perubahan pada hari raya sejenis sebelumnya. Cakupan rentang belum bisa dinilai bila hari raya sejenis kurang dari ${ACARA.aturan.minimal_acara_cakupan}, jadi statusnya tetap Eksperimen.</p>`;
  } else void jenis;
  $("acara").innerHTML = isi || '<p class="menunggu-blok">Menunggu data. Belum ada hari raya yang cukup berdata.</p>';
}

/* ---------- periodik */
function periodik(v) {
  const info = PERIODIK.periode[S.periode];
  const wadah = $("periodik");
  if (S.grafikPeriodik) { S.grafikPeriodik.destroy(); S.grafikPeriodik = null; }
  if (!info) { wadah.innerHTML = '<p class="menunggu-blok">Menunggu data.</p>'; return; }
  if (!info.tersedia) {
    const pct = Math.min(100, info.bulan_tersedia / info.minimal_bulan * 100);
    wadah.innerHTML = `<div class="pesan peringatan"><b>Menunggu data.</b> ${esc(info.alasan)}</div>
      <div class="ind-meter" style="margin-top:10px"><span style="width:${pct.toFixed(1)}%"></span></div><p class="meta-kecil">${info.bulan_tersedia} dari ${info.minimal_bulan} bulan data tersedia.</p>`;
    return;
  }
  const p = info.varian.find((x) => x.kode === v.kode);
  if (!p || !p.dasar) { wadah.innerHTML = `<p class="menunggu-blok">Menunggu data. ${esc((p?.gagal || ["Riwayat bulanan varian ini belum cukup."]).join(" "))}</p>`; return; }
  const r = p.rata_periode;
  wadah.innerHTML = `
    <div class="skenario">
      <div class="skenario-kotak rendah"><span>Skenario rendah</span><strong>${rp(r.rendah)}</strong></div>
      <div class="skenario-kotak dasar"><span>Skenario dasar</span><strong>${rp(r.dasar)}</strong><em class="${kelasPerubahan(p.perubahan_vs_periode_lalu_persen, 3)}">${persen(p.perubahan_vs_periode_lalu_persen, 1, true)} dari periode lalu (${rp(p.rata_periode_lalu)})</em></div>
      <div class="skenario-kotak tinggi"><span>Skenario tinggi</span><strong>${rp(r.tinggi)}</strong></div>
    </div>
    <div class="kanvas-tinggi kecil"><canvas id="grafik-periodik" role="img" aria-label="Skenario harga rata-rata bulanan"></canvas></div>
    <p class="meta-kecil">${lencanaStatus(p.status)} ${p.gagal?.length ? `Belum lolos: ${p.gagal.map(esc).join(", ")}. ` : ""}Cara: ${esc(p.nama_model)}. Meleset uji ${persen(p.evaluasi.smape, 2)} (harga terakhir: ${persen(p.evaluasi.smape_naif, 2)}), tepat dalam rentang ${persen(p.evaluasi.cakupan_persen, 0)}. Rata-rata ${info.bulan_per_periode} bulan ke depan: ${info.bulan_target.map((b) => esc(b)).join(", ")}. Skenario rendah dan tinggi adalah batas bawah dan atas ${pesentingkat}%.</p>`;
  if (!window.Chart) return;
  const riw = p.riwayat_bulanan || [];
  const label = [...riw.map((x) => x.bulan), ...info.bulan_target];
  const kosong = (n) => Array(n).fill(null);
  const c = { a: warna("series-1"), p: warna("series-2"), s3: warna("series-3"), s4: warna("series-4"), grid: warna("grid"), muted: warna("muted") };
  const sambung = (arr) => [...kosong(riw.length - 1), riw.at(-1)?.rata ?? null, ...arr];
  S.grafikPeriodik = new window.Chart($("grafik-periodik"), {
    type: "line",
    data: { labels: label, datasets: [
      { label: "Rata-rata bulanan", data: [...riw.map((x) => x.rata), ...kosong(info.bulan_target.length)], borderColor: c.a, backgroundColor: c.a, borderWidth: 2, pointRadius: 2, tension: 0 },
      { label: "Tinggi", data: sambung(p.tinggi).slice(0, label.length), borderColor: c.s4, borderDash: [4, 3], borderWidth: 1.5, pointRadius: 0, tension: 0 },
      { label: "Dasar", data: sambung(p.dasar).slice(0, label.length), borderColor: c.p, backgroundColor: c.p, borderDash: [6, 4], borderWidth: 2, pointRadius: 2, tension: 0 },
      { label: "Rendah", data: sambung(p.rendah).slice(0, label.length), borderColor: c.s3, borderDash: [4, 3], borderWidth: 1.5, pointRadius: 0, tension: 0 },
    ] },
    options: { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { display: true, labels: { boxWidth: 12, color: c.muted } }, tooltip: { callbacks: { label: (i) => (i.raw === null ? "" : `${rp(i.raw)}  ${i.dataset.label}`) } } },
      scales: { x: { grid: { display: false }, ticks: { color: c.muted, maxRotation: 0, autoSkipPadding: 18 } },
        y: { grid: { color: c.grid }, border: { display: false }, ticks: { color: c.muted, callback: (val) => new Intl.NumberFormat("id-ID").format(val) } } } },
  });
}

/* ---------- rekomendasi dan jejak */
function rekomendasi(v) {
  const terbesar = [...A.varian].filter((x) => proy(x, 30)?.perubahan_persen != null)
    .sort((a, b) => Math.abs(proy(b, 30).perubahan_persen) - Math.abs(proy(a, 30).perubahan_persen)).slice(0, 5);
  $("rekomendasi").innerHTML = `<p class="rekomendasi-utama">${esc(v.rekomendasi)}</p>
    <h3 class="sub-judul">Perubahan 30 hari terbesar</h3>
    <ul class="daftar-pendorong">${terbesar.map((x) => { const p = proy(x, 30); return `<li><button type="button" class="tautan-varian" data-kode="${esc(x.kode)}">${esc(x.nama)}</button><strong class="${kelasPerubahan(p.perubahan_persen, 3)}">${persen(p.perubahan_persen, 1, true)}</strong>${x.status === "valid" ? "" : ' <span class="meta-kecil">Eksperimen</span>'}</li>`; }).join("")}</ul>`;
}

function jejak() {
  const g = A.garis_data;
  $("jejak").innerHTML = `
    <ol class="alur-data">${g.tahap.map((t) => `<li><b>${esc(t.nama)}</b><span>${esc(t.ringkas)}</span></li>`).join("")}</ol>
    <dl class="dl">
      <dt>Versi data</dt><dd><code title="${esc(g.versi_data)}">${esc(pendek(g.versi_data))}</code></dd>
      <dt>Versi konfigurasi</dt><dd><code title="${esc(g.versi_konfigurasi)}">${esc(pendek(g.versi_konfigurasi))}</code></dd>
      <dt>Versi kode</dt><dd>${g.commit ? `<code>${esc(g.commit.slice(0, 7))}</code>` : '<span class="menunggu">dijalankan di luar GitHub</span>'}</dd>
      <dt>Proses</dt><dd>${g.url_run ? `<a href="${esc(g.url_run)}" rel="noopener">buka jalannya di GitHub</a>` : "–"}</dd>
      <dt>Unsur acak</dt><dd>${esc(g.keterangan_seed)}</dd>
    </dl>
    <details><summary class="meta-kecil">Riwayat pergantian cara prakiraan (${(A.registry_riwayat || []).length})</summary>${(A.registry_riwayat || []).length
      ? `<div class="gulir-tabel"><table class="tabel-kecil"><thead><tr><th>Data hingga</th><th>Varian</th><th>Dari</th><th>Menjadi</th><th>Status</th></tr></thead><tbody>${[...A.registry_riwayat].reverse().map((r) => `<tr><td>${esc(tgl(r.tanggal_data))}</td><td>${esc(r.kode)}</td><td class="meta-kecil">${esc(NAMA_PENDEK[r.model_sebelumnya] || "–")}</td><td class="meta-kecil">${esc(NAMA_PENDEK[r.model] || r.model || "–")}</td><td>${lencanaStatus(r.status)}</td></tr>`).join("")}</tbody></table></div>`
      : '<p class="meta-kecil">Belum ada catatan. Registri terisi saat sistem berjalan dengan data asli.</p>'}</details>
    <details><summary class="meta-kecil">Berkas sumber dan sidik jari SHA-256 (${g.berkas_mentah.length})</summary><div class="gulir-tabel"><table class="tabel-kecil"><thead><tr><th>Berkas</th><th class="angka">Diterima</th><th class="angka">Ditolak</th><th>SHA-256</th></tr></thead><tbody>${g.berkas_mentah.map((b) => `<tr><td class="meta-kecil">${esc(b.berkas)}</td><td class="angka">${angka(b.diterima)}</td><td class="angka">${angka(b.ditolak)}</td><td><code title="${esc(b.sha256)}">${esc(b.sha256.slice(0, 12))}</code></td></tr>`).join("")}</tbody></table></div></details>`;
}

/* ---------- peristiwa */
function atur(grup, atribut, fn) {
  $(grup).addEventListener("click", (e) => {
    const b = e.target.closest(`button[${atribut}]`);
    if (!b) return;
    $(grup).querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    fn(b.getAttribute(atribut));
  });
}

kepala();
isiPilihan();
jejak();
atur("horizon", "data-h", (h) => { S.h = Number(h); gambarTabel(); const v = A.varian.find((x) => x.kode === S.kode); gambarTren(v); ringkasVarian(v); });
atur("rentang-waktu", "data-hari", (h) => { S.hari = Number(h); gambarTren(A.varian.find((x) => x.kode === S.kode)); });
atur("periode", "data-p", (p) => { S.periode = p; periodik(A.varian.find((x) => x.kode === S.kode)); });
$("varian").addEventListener("change", (e) => pilih(e.target.value));
for (const id of ["kelompok", "status"]) $(id).addEventListener("change", gambarTabel);
$("ekspor").addEventListener("click", ekspor);
document.querySelector("#tabel thead").addEventListener("click", (e) => {
  const th = e.target.closest("th[data-urut]");
  if (!th) return;
  S.urut = { kunci: th.dataset.urut, arah: S.urut.kunci === th.dataset.urut ? -S.urut.arah : 1 };
  gambarTabel();
});
const bukaBaris = (e) => {
  const tr = e.target.closest("tr[data-kode]");
  if (tr && (e.type === "click" || e.key === "Enter" || e.key === " ")) { e.preventDefault(); pilih(tr.dataset.kode, true); }
};
document.querySelector("#tabel tbody").addEventListener("click", bukaBaris);
document.querySelector("#tabel tbody").addEventListener("keydown", bukaBaris);
$("rekomendasi").addEventListener("click", (e) => { const b = e.target.closest("[data-kode]"); if (b) pilih(b.dataset.kode, true); });
saatTemaBerubah(() => { if (S.kode) pilih(S.kode); });

const awal = new URLSearchParams(location.search).get("varian");
await pilih(A.varian.find((v) => v.kode === awal)?.kode || A.varian[0]?.kode);

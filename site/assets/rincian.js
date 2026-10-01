// Jendela rincian untuk kotak indikator di beranda TPID. Klik "1 Sinyal prioritas" (atau kotak lain)
// dan isinya muncul di sini: apa saja yang dihitung, di mana, dan apa langkah berikutnya.
import { esc, rp, persen, angka, tgl, muatJSON, lencanaStatus, lencanaKeparahan, JENIS_SINYAL } from "./app.js";
import { ikon, gambarKomoditas, selisihHarga, htmlSelisih, tglPendek, LANGKAH_SINYAL } from "./dashboard.js";
import { bolehAkses } from "./akses.js";

let dialog = null;
let asal = null;

function siapkan() {
  if (dialog) return dialog;
  dialog = document.createElement("dialog");
  dialog.className = "rincian";
  dialog.setAttribute("aria-labelledby", "rincian-judul");
  dialog.innerHTML = `<div class="rincian-kotak">
      <div class="rincian-kepala"><span class="rincian-ikon"></span>
        <div class="rincian-teks"><h2 id="rincian-judul"></h2><p class="rincian-sub"></p></div>
        <button type="button" class="rincian-tutup" aria-label="Tutup">${ikon("silang", 18)}</button></div>
      <div class="rincian-isi"></div>
    </div>`;
  document.body.append(dialog);
  dialog.querySelector(".rincian-tutup").addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (e) => {
    // Klik di luar kotak (latar gelap) atau tautan ke bagian halaman ini (mis. grafik) menutup jendela.
    if (e.target === dialog || e.target.closest("a[href^='#']")) dialog.close();
  });
  dialog.addEventListener("close", () => {
    // Event "close" datang sedikit terlambat. Bila jendela sudah dibuka lagi, jangan ganggu fokus dan kunci gulir.
    if (dialog.open) return;
    document.documentElement.classList.remove("rincian-terbuka");
    const kembali = asal;
    asal = null;
    kembali?.focus({ preventScroll: true });
  });
  return dialog;
}

/** Membuka jendela rincian. `isi` boleh berupa teks HTML atau fungsi async yang mengembalikan teks HTML. */
export async function bukaRincian({ judul, sub = "", ikonNama = "dokumen", warna = "biru", isi }) {
  const d = siapkan();
  if (!d.open) asal = document.activeElement;
  d.querySelector("#rincian-judul").textContent = judul;
  d.querySelector(".rincian-sub").textContent = sub;
  d.querySelector(".rincian-sub").hidden = !sub;
  const lingkar = d.querySelector(".rincian-ikon");
  lingkar.className = `rincian-ikon kpi-lingkar ${warna}`;
  lingkar.innerHTML = ikon(ikonNama, 22);
  const wadah = d.querySelector(".rincian-isi");
  wadah.innerHTML = `<p class="kosong">Memuat…</p>`;
  wadah.scrollTop = 0;
  if (!d.open) d.showModal();
  document.documentElement.classList.add("rincian-terbuka");
  try {
    wadah.innerHTML = typeof isi === "function" ? await isi() : isi;
  } catch (e) {
    console.error(e);
    wadah.innerHTML = `<p class="pesan galat">Rincian belum bisa dimuat. Coba muat ulang halaman.</p>`;
  }
  d.querySelector(".rincian-tutup").focus({ preventScroll: true });
}

/* ---------- bagian kecil yang dipakai bersama */
const tautan = (peran, href, teks, utama = false) =>
  bolehAkses(peran, href.split("#")[0]) ? `<a class="tombol${utama ? " utama-aksi" : ""}" href="${esc(href)}">${teks}</a>` : "";
const aksi = (...tombol) => {
  const ada = tombol.filter(Boolean);
  return ada.length ? `<div class="rincian-aksi">${ada.join("")}</div>` : "";
};
const meter = (nilai, target, kelas = "") =>
  `<div class="rincian-meter ${kelas}" role="img" aria-label="${esc(persen(nilai, 1))} dari target ${esc(persen(target, 0))}">
    <span style="width:${Math.max(0, Math.min(100, nilai ?? 0))}%"></span>${target !== null && target !== undefined ? `<i style="left:${target}%"></i>` : ""}</div>`;
const baris = (label, nilai) => `<div><dt>${label}</dt><dd>${nilai}</dd></div>`;
const lamaHari = (mulai, akhir) => {
  const n = Math.round((Date.parse(akhir) - Date.parse(mulai)) / 864e5) + 1;
  return Number.isFinite(n) && n > 0 ? `${n} hari` : "";
};

/* ---------- 1. sinyal prioritas */
const ada = (x) => x !== null && x !== undefined;

/** Angka penting sebuah sinyal. Isinya menyesuaikan jenis sinyal (harga janggal, perkiraan naik, hari raya, data terlambat). */
function angkaSinyal(s, satuan) {
  const r = [];
  const kini = ada(s.nilai_aktual) ? baris("Harga sekarang", `<b>${rp(s.nilai_aktual)}</b>${satuan}`) : "";
  if (s.jenis === "anomali_harga" && kini && s.baseline) {
    r.push(kini, baris("Harga biasanya", `${rp(s.baseline)}${satuan}`),
      baris("Selisih", htmlSelisih({ selisih: s.nilai_aktual - s.baseline, persen: s.deviasi_persen ?? null })));
  } else if (s.jenis === "proyeksi_naik" && kini && s.proyeksi_h7) {
    r.push(kini, baris("Perkiraan 7 hari lagi", `${rp(s.proyeksi_h7.prediksi)}${satuan}`),
      baris("Perkiraan naik", htmlSelisih({ selisih: s.proyeksi_h7.prediksi - s.nilai_aktual, persen: s.deviasi_persen ?? null })));
  } else if (s.jenis === "risiko_hari_raya") {
    if (kini) r.push(kini);
    if (ada(s.deviasi_persen)) r.push(baris("Bisa naik sampai", persen(s.deviasi_persen, 0, true)));
  } else if (s.jenis === "data_terlambat") {
    const t = s.konteks?.tanggal_data_terakhir;
    r.push(baris("Data terakhir masuk", t ? esc(tglPendek(t)) : "belum pernah"));
  } else if (kini) r.push(kini);
  const lama = lamaHari(s.tanggal_mulai, s.tanggal_terakhir);
  r.push(baris(s.jenis === "data_terlambat" ? "Belum masuk sejak" : "Mulai terlihat", `${esc(tglPendek(s.tanggal_mulai))}${lama ? `, sudah ${lama}` : ""}`));
  return `<dl class="rs-angka">${r.join("")}</dl>`;
}

export function isiSinyal({ sinyal, ringkasan, pasar, peran }) {
  const aktif = sinyal.filter((s) => s.aktif);
  const prioritas = aktif.filter((s) => s.keparahan === "tinggi");
  const lain = aktif.length - prioritas.length;
  const varian = Object.fromEntries(ringkasan.varian.map((v) => [v.kode, v]));
  const namaWilayah = (s) => pasar.find((p) => p.kode === s.kode_pasar)?.nama
    || pasar.find((p) => p.kode_wilayah === s.kode_wilayah)?.wilayah || "";

  const kartu = prioritas.map((s) => {
    const v = varian[s.kode_varian];
    return `<article class="rincian-sinyal">
      <div class="rs-kepala">${s.kode_varian ? gambarKomoditas(s.kode_varian) : `<span class="kpi-lingkar merah">${ikon(s.jenis === "data_terlambat" ? "jam" : "peringatan", 22)}</span>`}
        <div><strong>${esc(s.varian || JENIS_SINYAL[s.jenis] || "Peringatan")}</strong><span>${esc(namaWilayah(s))}</span></div>
        ${lencanaStatus(s.status)}</div>
      <p class="rs-judul">${esc(s.judul)}</p>
      ${angkaSinyal(s, v ? `/${esc(v.satuan)}` : "")}
      ${s.narasi ? `<p class="rs-narasi">${esc(s.narasi)}</p>` : ""}
      <p class="rs-langkah">${ikon("lampu", 16)}<span><b>Langkah berikutnya:</b> ${esc(LANGKAH_SINYAL[s.jenis] || "Perlu dicek analis")}</span></p>
      ${aksi(v ? `<a class="tombol" href="#varian=${encodeURIComponent(s.kode_varian)}">Lihat grafik harga</a>` : "",
        tautan(peran, `sinyal.html#${s.id}`, "Buka di halaman Peringatan", true))}
    </article>`;
  }).join("");

  const kosong = `<p class="rincian-kosong">${ikon("centang", 20)}<span>Tidak ada sinyal prioritas saat ini. Harga yang dipantau masih dalam batas wajar.</span></p>`;
  const catatanLain = lain > 0
    ? `<div class="rincian-catatan"><span>Ada <b>${angka(lain)}</b> peringatan lain dengan tingkat lebih rendah.</span>${tautan(peran, "sinyal.html", "Lihat semua peringatan")}</div>`
    : "";
  return `<p class="rincian-pengantar">Sinyal prioritas adalah peringatan tingkat tinggi yang perlu segera dicek bersama,
      misalnya harga yang naik jauh di atas biasanya atau data pasar yang lama tidak masuk.</p>
    ${kartu || kosong}${catatanLain}`;
}

/* ---------- 2. komoditas dan varian */
export function isiKomoditas({ ringkasan, master }) {
  const varian = Object.fromEntries(ringkasan.varian.map((v) => [v.kode, v]));
  const grup = master.komoditas.map((k) => {
    const daftar = k.varian.map((kode) => varian[kode]).filter(Boolean);
    if (!daftar.length) return "";
    return `<section class="rk-grup">
      <h3>${gambarKomoditas(daftar[0].kode)}<span>${esc(k.nama)}</span><small>${daftar.length} varian</small></h3>
      <ul>${daftar.map((v) => {
        const s = selisihHarga(v);
        return `<li><a href="#varian=${encodeURIComponent(v.kode)}">
          <span class="rk-nama">${esc(v.nama)}${v.sinyal ? ` ${lencanaKeparahan(v.sinyal)}` : ""}</span>
          <span class="rk-harga"><b>${rp(v.harga_terakhir)}</b><i>/${esc(v.satuan)}</i></span>
          <span class="rk-ubah">${htmlSelisih(s)}${s ? `<small>dari ${rp(s.lalu)}</small>` : ""}</span></a></li>`;
      }).join("")}</ul></section>`;
  }).join("");
  return `<p class="rincian-pengantar">Harga sekarang dibanding sebulan lalu. Klik salah satu untuk melihat grafiknya.</p>${grup}`;
}

/* ---------- 3. wilayah blank spot */
export function isiBlankSpot({ pasar, peran }) {
  const TARGET = 8;
  const blank = pasar.filter((p) => p.blank_spot);
  const dipantau = pasar.filter((p) => p.peran === "target" && !p.blank_spot);
  const daftarBlank = blank.length
    ? `<ul class="rincian-daftar">${blank.map((p) => `<li>${ikon("pin", 18)}<div><b>${esc(p.nama)}</b>
        <span>${esc(p.kecamatan ? `Kecamatan ${p.kecamatan}` : p.wilayah)}${p.ketepatan ? ` · data lengkap ${persen(p.ketepatan.kelengkapan_persen, 0)}` : ""}</span></div></li>`).join("")}</ul>`
    : `<p class="rincian-kosong oranye">${ikon("pin", 20)}<span>Belum ada wilayah blank spot yang didaftarkan. Daftar 8 wilayahnya masih menunggu keputusan.</span></p>`;
  const caraTambah = peran === "admin" || peran === "operator"
    ? `<p class="meta-kecil">Cara menambah: isi <code>blank_spot</code> dengan <code>1</code> pada <code>config/pasar.csv</code> untuk pasar di wilayah tersebut.</p>`
    : "";
  return `<p class="rincian-pengantar">Blank spot adalah wilayah yang sulit sinyal. Petugas tetap bisa mencatat harga tanpa internet,
      dan data terkirim sendiri begitu ada sinyal.</p>
    <div class="rincian-angka-besar"><b>${angka(blank.length)}</b><span>dari target ${TARGET} wilayah</span></div>
    ${meter(blank.length / TARGET * 100, null, "oranye")}
    ${daftarBlank}${caraTambah}
    ${dipantau.length ? `<h3 class="rincian-subjudul">Pasar yang sudah dipantau</h3>
      <ul class="rincian-daftar">${dipantau.map((p) => `<li>${ikon("toko", 18)}<div><b>${esc(p.nama)}</b>
        <span>${esc(p.kecamatan ? `Kecamatan ${p.kecamatan}` : p.wilayah)}</span></div></li>`).join("")}</ul>` : ""}
    ${aksi(tautan(peran, "input.html", "Buka Catat Harga"))}`;
}

/* ---------- 4. ketepatan waktu pelaporan */
export async function isiKetepatan({ kpi, pasar, peran }) {
  const kualitas = await muatJSON("kualitas.json").catch(() => null);
  const kt = kualitas?.ketepatan;
  const target = kpi.target_ketepatan_persen;
  const jam = kualitas?.pengaturan?.jam_batas_tepat_waktu;
  const periode = kt?.periode ? `${tgl(kt.periode.mulai)} sampai ${tgl(kt.periode.akhir)}` : "";
  const perPasar = (kt?.per_pasar || pasar.map((p) => p.ketepatan).filter(Boolean));
  const kartu = perPasar.map((p) => {
    const kurang = p.ketepatan_persen !== null && p.ketepatan_persen < target;
    return `<li class="${kurang ? "kurang" : ""}">
      <div class="rkt-atas"><b>${esc(p.nama_pasar)}</b><span class="rkt-nilai">${persen(p.ketepatan_persen, 1)}</span></div>
      ${meter(p.ketepatan_persen, target, kurang ? "oranye" : "hijau")}
      <div class="rkt-bawah"><span>Data masuk ${angka(p.diterima)} dari ${angka(p.diharapkan)} (${persen(p.kelengkapan_persen, 0)})</span>
        <span>Terakhir lapor ${esc(tglPendek(p.tanggal_terakhir))}</span></div>
      ${kurang ? `<p class="rkt-saran">Di bawah target. Ingatkan petugas di pasar ini untuk mengirim lebih awal.</p>` : ""}
    </li>`;
  }).join("");
  return `<p class="rincian-pengantar">Persentase harga yang masuk tepat waktu${jam !== undefined ? `, yaitu paling lambat pukul ${esc(String(jam).padStart(2, "0"))}.00 pada hari yang sama` : ""}.
      Targetnya ${persen(target, 0)}.</p>
    <div class="rincian-angka-besar"><b>${persen(kpi.ketepatan_persen, 1)}</b><span>${periode ? `rata-rata ${esc(periode)}` : "rata-rata semua pasar"}</span></div>
    ${meter(kpi.ketepatan_persen, target, kpi.ketepatan_persen >= target ? "hijau" : "oranye")}
    <h3 class="rincian-subjudul">Per pasar</h3>
    ${kartu ? `<ul class="rincian-ketepatan">${kartu}</ul>` : `<p class="kosong">Belum ada data pasar.</p>`}
    ${aksi(tautan(peran, "kualitas.html", "Buka Cek Data"))}`;
}

/* ---------- 5. uptime */
export function isiUptime({ kinerja, peran }) {
  const l1 = kinerja?.indikator?.find((i) => i.kode === "L1");
  const ada = l1 && l1.nilai !== null && l1.nilai !== undefined;
  return `<p class="rincian-pengantar">Uptime menunjukkan seberapa sering dashboard bisa dibuka dalam 30 hari terakhir. Situs dicek otomatis setiap jam.</p>
    <div class="rincian-angka-besar"><b>${ada ? persen(l1.nilai, 1) : "–"}</b><span>target ${l1 ? persen(l1.target, 1) : "99,5%"}</span></div>
    ${ada ? meter(l1.nilai, l1.target, l1.nilai >= l1.target ? "hijau" : "oranye") : ""}
    <p class="rincian-kosong">${ikon("roda", 20)}<span>${esc(l1?.catatan || "Catatan pemeriksaan belum ada.")}</span></p>
    ${aksi(tautan(peran, "kinerja.html", "Lihat semua capaian"))}`;
}

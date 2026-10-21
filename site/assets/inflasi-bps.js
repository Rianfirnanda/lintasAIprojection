// Inflasi resmi BPS di Dasbor TPID dan Mode Videotron. Bengkulu Tengah belum termasuk kota penghitung IHK, jadi angka
// Provinsi Bengkulu (gabungan Kota Bengkulu dan Mukomuko) dipakai sebagai acuan. Data dari ringkasan.json bagian
// inflasi_bps, disusun pipeline (python -m pipeline ambil-bps) dari tabel BPS Web API dan Berita Resmi Statistik.
import { esc, persen, tgl, angka, warna } from "./app.js";
import { bulanTahun } from "./dashboard.js";
import { animasiGrafik } from "./grafik.js";
import { sasaran, statusSasaran, angkaUtama } from "./inflasi-inti.js";

const BULAN_SINGKAT = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
const ada = (x) => x !== null && x !== undefined && !Number.isNaN(x);
const nilai = (x) => (ada(x) ? persen(x, 2) : "–");

const setahunLalu = (p) => `${Number(p.slice(0, 4)) - 1}${p.slice(4)}`;
const bulanPendek = (p) => `${BULAN_SINGKAT[Number(p.slice(5, 7)) - 1]} ${p.slice(2, 4)}`;

function catatanSumber(ib, u) {
  const asal = u.asal === "rilis"
    ? `Angka utama dari Berita Resmi Statistik BPS${u.tanggal ? ` terbitan ${esc(tgl(u.tanggal))}` : ""}. Rincian per kelompok pengeluaran di tabel BPS Web API baru tersedia sampai ${esc(bulanTahun(ib.periode))}.`
    : `Sumber: tabel BPS Web API, data sampai ${esc(bulanTahun(ib.periode))}.`;
  return `${asal} Bengkulu Tengah belum punya angka inflasi sendiri, jadi angka Provinsi Bengkulu dipakai sebagai acuan.`;
}

/** Isi panel "Inflasi Resmi BPS" di Dasbor TPID. Grafiknya digambar sesudahnya dengan gambarTrenInflasi. */
export function panelInflasi(ib) {
  const u = angkaUtama(ib);
  const st = statusSasaran(u.yoy, u.periode), s = sasaran(u.periode);
  const tren = ib.tren || [], iUtama = tren.findIndex((t) => t.periode === u.periode);
  const lalu = iUtama > 0 ? tren[iUtama - 1] : null;
  // Garis kelompok makanan terputus bila tabel BPS kosong di tengah deret.
  const adaMakan = (i) => ada(tren[i]?.yoy_makanan);
  const putus = tren.some((t, i) => !adaMakan(i) && tren.slice(0, i).some((_, j) => adaMakan(j)) && tren.slice(i + 1).some((_, j) => adaMakan(i + 1 + j)));
  const mak = ib.makanan;
  const kota = (ib.wilayah_ihk?.daftar || []).filter((k) => !/provinsi/i.test(k.nama));
  const samping = [
    mak && ada(mak.yoy) ? `<li><span>Makanan, minuman, dan tembakau</span><b>${nilai(mak.yoy)}</b><small>setahun, ${esc(bulanTahun(ib.periode))}</small></li>` : "",
    ...kota.map((k) => `<li><span>${esc(k.nama)}</span><b>${nilai(k.yoy)}</b><small>setahun, ${esc(bulanTahun(ib.wilayah_ihk.periode))}</small></li>`),
    ib.ntp ? `<li><span>Nilai Tukar Petani</span><b>${esc(angka(ib.ntp.nilai, 2))}</b><small>${esc(bulanTahun(ib.ntp.periode))}, di atas 100 berarti petani surplus</small></li>` : "",
  ].join("");
  return `<div class="inf-grid">
      <div class="inf-utama">
        <span class="inf-label">Inflasi setahun (y-on-y)</span>
        <strong class="inf-angka">${nilai(u.yoy)}</strong>
        <span class="inf-periode">${esc(bulanTahun(u.periode))} dibanding ${esc(bulanTahun(setahunLalu(u.periode)))}</span>
        ${st ? `<span class="pil ${st[1]}">${st[0]} ${esc(s.teks)}</span>` : ""}
        <dl class="inf-kecil">
          <div><dt>Sebulan (m-to-m)</dt><dd>${nilai(u.mtm)}</dd></div>
          ${ada(u.ytd) ? `<div><dt>Sejak Januari (y-to-d)</dt><dd>${nilai(u.ytd)}</dd></div>` : ""}
          ${lalu && ada(lalu.yoy) ? `<div><dt>Setahun, ${esc(bulanTahun(lalu.periode))}</dt><dd>${nilai(lalu.yoy)}</dd></div>` : ""}
        </dl>
      </div>
      <figure class="inf-grafik">
        <div class="wadah-grafik"><canvas id="grafik-inflasi" role="img" aria-label="Grafik inflasi setahun Provinsi Bengkulu, ${esc(bulanTahun(ib.tren?.[0]?.periode))} sampai ${esc(bulanTahun(u.periode))}"></canvas></div>
        <figcaption class="legenda dash-legenda">
          <span><span class="kunci-garis" style="border-color:var(--series-1)"></span>Umum</span>
          ${mak ? `<span><span class="kunci-garis" style="border-color:var(--series-2)"></span>Makanan, minuman, dan tembakau</span>` : ""}
          ${s ? `<span><span class="kunci-pita" style="background:var(--pil-baik-bg)"></span>Sasaran ${esc(s.teks)}</span>` : ""}
        </figcaption>
      </figure>
      ${samping ? `<ul class="inf-samping">${samping}</ul>` : ""}
    </div>
    <p class="inf-catatan">${catatanSumber(ib, u)}${putus ? " Garis kelompok makanan terputus pada bulan yang tabelnya belum diisi BPS." : ""}</p>`;
}

// Pita sasaran inflasi di belakang garis grafik.
const pitaSasaran = {
  id: "pitaSasaran",
  beforeDatasetsDraw(chart, _args, opsi) {
    if (!opsi?.bawah && opsi?.bawah !== 0) return;
    const { ctx, chartArea: a, scales: { y } } = chart;
    const atas = Math.max(a.top, y.getPixelForValue(opsi.atas)), bawah = Math.min(a.bottom, y.getPixelForValue(opsi.bawah));
    if (bawah <= atas) return;
    ctx.save();
    ctx.fillStyle = opsi.warna;
    ctx.fillRect(a.left, atas, a.right - a.left, bawah - atas);
    ctx.restore();
  },
};

/** Grafik inflasi setahun (umum dan makanan) dengan pita sasaran. Titik dari Berita Resmi Statistik diberi bulatan. */
export function gambarTrenInflasi(kanvas, ib) {
  const tren = ib.tren || [];
  if (!window.Chart || tren.length < 2) return null;
  const label = tren.map((t) => t.periode);
  const daftarSasaran = label.map(sasaran);
  const s = daftarSasaran.every((x) => x && x.teks === daftarSasaran[0].teks) ? daftarSasaran[0] : null;
  const huruf = { family: warna("sans"), size: 11 };
  const titik = (ctx) => (tren[ctx.dataIndex]?.asal === "rilis" ? 3.5 : 0);
  const datasets = [{
    label: "Umum", data: tren.map((t) => t.yoy ?? null), borderColor: warna("series-1"), backgroundColor: warna("series-1"),
    borderWidth: 2.4, pointRadius: titik, pointHoverRadius: 5, tension: 0.25, spanGaps: true,
  }];
  if (tren.some((t) => ada(t.yoy_makanan))) {
    datasets.push({ label: "Makanan, minuman, dan tembakau", data: tren.map((t) => t.yoy_makanan ?? null), borderColor: warna("series-2"),
      backgroundColor: warna("series-2"), borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.25, spanGaps: false });
  }
  return new window.Chart(kanvas, {
    type: "line",
    data: { labels: label, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: animasiGrafik(label.length),
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        pitaSasaran: s ? { bawah: s.bawah, atas: s.atas, warna: warna("pil-baik-bg") } : {},
        tooltip: {
          filter: (item) => item.raw !== null,
          callbacks: {
            title: (items) => bulanTahun(items[0]?.label),
            label: (item) => `${item.dataset.label}: ${persen(item.raw, 2)}`,
            footer: (items) => (tren[items[0]?.dataIndex]?.asal === "rilis" ? "Dari Berita Resmi Statistik" : ""),
          },
        },
      },
      scales: {
        x: { grid: { display: false }, border: { color: warna("grid") },
          ticks: { color: warna("muted"), font: huruf, maxRotation: 0, autoSkipPadding: 18, callback(v) { return bulanPendek(this.getLabelForValue(v)); } } },
        y: { grid: { color: warna("grid") }, border: { display: false }, grace: "8%",
          ticks: { color: warna("muted"), font: huruf, callback: (v) => `${v.toLocaleString("id-ID")}%` } },
      },
    },
    plugins: [pitaSasaran],
  });
}

/** Isi jendela rincian: rilis resmi terbaru, angka per kelompok pengeluaran, per kota IHK, dan nilai tukar petani. */
export function isiInflasi(ib) {
  const u = angkaUtama(ib);
  const s = sasaran(u.periode);
  const rilis = (ib.rilis || []).map((r) => `<tr><td>${esc(bulanTahun(r.periode))}</td><td class="angka">${nilai(r.mtm)}</td>
      <td class="angka">${nilai(r.yoy)}</td><td>${r.tanggal ? esc(tgl(r.tanggal)) : "–"}${r.url ? ` · <a href="${esc(r.url)}" target="_blank" rel="noopener">Baca</a>` : ""}</td></tr>`).join("");
  const kelompok = (ib.kelompok || []).map((k) => `<tr${k.nama === "Umum" ? ' class="inf-umum"' : ""}><td>${esc(k.nama)}</td>
      <td class="angka">${nilai(k.mtm)}</td><td class="angka">${nilai(k.ytd)}</td><td class="angka">${nilai(k.yoy)}</td></tr>`).join("");
  const daftarKota = ib.wilayah_ihk?.daftar || [], adaSebulan = daftarKota.some((k) => ada(k.mtm));
  const kota = daftarKota.map((k) => `<tr><td>${esc(k.nama)}</td>${adaSebulan ? `<td class="angka">${nilai(k.mtm)}</td>` : ""}<td class="angka">${nilai(k.yoy)}</td></tr>`).join("");
  const n = ib.ntp;
  const riwayatNtp = (n?.riwayat || []).slice().reverse().map((x) => `<tr><td>${esc(bulanTahun(x.periode))}</td><td class="angka">${esc(angka(x.nilai, 2))}</td></tr>`).join("");
  const ntp = n ? `<h3 class="rincian-subjudul">Nilai Tukar Petani (NTP), ${esc(bulanTahun(n.periode))}</h3>
      <div class="rincian-angka-besar"><b>${esc(angka(n.nilai, 2))}</b><span>${ada(n.ubah_persen) ? `${n.ubah_persen < 0 ? "turun" : "naik"} ${persen(Math.abs(n.ubah_persen), 2)} dari bulan sebelumnya` : "Provinsi Bengkulu"}</span></div>
      <p class="rincian-pengantar">NTP membandingkan harga yang diterima petani dengan harga yang mereka bayar untuk kebutuhan rumah tangga
        dan biaya produksi. Di atas 100 berarti harga jual hasil tani naik lebih cepat daripada pengeluaran petani.${n.asal === "indeks"
          ? " Angka ini dihitung dari indeks harga yang diterima (It) dan dibayar (Ib) petani, karena rilis resminya belum terbaca." : ""}
        ${n.url ? `<a href="${esc(n.url)}" target="_blank" rel="noopener">Baca rilis BPS</a>` : ""}</p>
      ${riwayatNtp ? `<div class="gulir-tabel"><table><thead><tr><th>Bulan</th><th class="angka">NTP</th></tr></thead><tbody>${riwayatNtp}</tbody></table></div>` : ""}` : "";
  return `<p class="rincian-pengantar">Inflasi adalah kenaikan harga barang dan jasa secara umum. BPS menghitungnya dari harga di kota
      penghitung IHK di Provinsi Bengkulu, yaitu Kota Bengkulu dan Kabupaten Mukomuko. Bengkulu Tengah belum termasuk, jadi angka
      provinsi dipakai sebagai acuan TPID.</p>
    <div class="rincian-angka-besar"><b>${nilai(u.yoy)}</b><span>inflasi setahun, ${esc(bulanTahun(u.periode))}${s ? `; sasaran nasional ${esc(s.teks)}` : ""}</span></div>
    ${rilis ? `<h3 class="rincian-subjudul">Berita Resmi Statistik terbaru</h3>
      <div class="gulir-tabel"><table><thead><tr><th>Bulan</th><th class="angka">Sebulan</th><th class="angka">Setahun</th><th>Terbit</th></tr></thead><tbody>${rilis}</tbody></table></div>` : ""}
    ${kelompok ? `<h3 class="rincian-subjudul">Menurut kelompok pengeluaran, ${esc(bulanTahun(ib.periode))}</h3>
      <div class="gulir-tabel"><table><thead><tr><th>Kelompok</th><th class="angka">Sebulan</th><th class="angka">Sejak Januari</th><th class="angka">Setahun</th></tr></thead><tbody>${kelompok}</tbody></table></div>` : ""}
    ${kota ? `<h3 class="rincian-subjudul">Menurut kota penghitung IHK, ${esc(bulanTahun(ib.wilayah_ihk.periode))}</h3>
      <div class="gulir-tabel"><table><thead><tr><th>Wilayah</th>${adaSebulan ? `<th class="angka">Sebulan</th>` : ""}<th class="angka">Setahun</th></tr></thead><tbody>${kota}</tbody></table></div>` : ""}
    ${ntp}
    <p class="rincian-catatan"><span>${catatanSumber(ib, u)} Diambil dari BPS ${esc(tgl(ib.diambil))}.</span></p>`;
}

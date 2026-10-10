// Dashboard Internal BPS: tata letak padat (indikator, tabel 21 varian, grafik, diagnostik, kinerja model, lineage, rekomendasi),
// diikuti analisis lanjutan (hari raya, periodik, kartu model, jejak versi). Dipakai di dasbor.html dan beranda admin/analis.
// Semua angka dibaca dari analitik.json, proyeksi_acara.json, proyeksi_periodik.json, model.json, dan seri/<varian>.json.
import { muatJSON, esc, persen, angka, rp, tgl, tampilkanGalat, keCSV, unduhTeks, warna, saatTemaBerubah } from "./app.js";
import { ikon } from "./dashboard.js";
import { gambarGrafikHarga, legendaDashboard, potongSeri } from "./grafik.js";

const NAMA_KELOMPOK = { pokok: "Pokok", protein: "Protein", volatil: "Volatil", pabrikan: "Pabrikan" };
const NAMA_PERCAYA = { tinggi: "Tinggi", sedang: "Sedang", rendah: "Rendah" };
const URUT_PERCAYA = { tinggi: 3, sedang: 2, rendah: 1 };
const NAMA_PENDEK = { naif: "Harga terakhir", rata7: "Rata-rata 7 hari", holt_redam: "Tren melandai (Holt)", ses: "Penghalusan eksponensial",
  hari_raya: "Pola hari raya", ml_challenger: "Machine learning", ensemble: "Gabungan (ensemble)" };
const KOMODITAS_BANDING = ["BRS03", "CMR01", "DAY01", "TLR01"];
const NAMA_BANDING = { BRS03: "Beras Medium", CMR01: "Cabai Merah", DAY01: "Daging Ayam Ras", TLR01: "Telur Ayam Ras" };

const KERANGKA = `
<header class="dsb-kepala">
  <img class="dsb-logo" src="assets/logo-bps.png" alt="Badan Pusat Statistik">
  <div class="dsb-judul">
    <h1>HASIL AKHIR · DASHBOARD INTERNAL BPS</h1>
    <p class="dsb-kuning">PROYEKSI HARGA PANGAN</p>
    <p id="dsb-wilayah" class="dsb-wilayah"></p>
  </div>
  <div class="dsb-semboyan"><span>DATA UNTUK PENGAMBILAN KEPUTUSAN<br>YANG LEBIH BAIK</span><span class="dsb-sekat"></span><em>Statistik Berkualitas<br>untuk Indonesia Maju</em></div>
</header>
<div class="dsb-kpi" id="dsb-kpi"></div>
<section class="dsb-kontrol" aria-label="Pilihan tampilan">
  <label>Periode Data (Origin)<select id="dsb-origin" aria-label="Periode data (origin)"></select></label>
  <label>Pilih Varian<select id="dsb-varian" aria-label="Pilih varian"></select></label>
  <div><span class="dsb-label">Horizon Prediksi</span>
    <div class="segmen" id="dsb-horizon" role="group" aria-label="Horizon prediksi">
      <button type="button" data-h="7" aria-pressed="false">7 Hari</button><button type="button" data-h="14" aria-pressed="false">14 Hari</button><button type="button" data-h="30" aria-pressed="true">30 Hari</button>
    </div></div>
  <div class="dsb-status" id="dsb-cap"></div>
</section>
<div class="dsb-grid">
  <section class="dsb-kartu dsb-tabel">
    <div class="dsb-kartu-kepala"><h2 id="dsb-judul-tabel">Tabel Proyeksi Harga Pangan</h2>
      <div class="dsb-alat">
        <select id="dsb-kelompok" aria-label="Kelompok komoditas"><option value="">Semua kelompok</option><option value="pokok">Pokok</option><option value="protein">Protein</option><option value="volatil">Volatil</option><option value="pabrikan">Pabrikan</option></select>
        <select id="dsb-status-filter" aria-label="Status validasi"><option value="">Semua status</option><option value="valid">Valid</option><option value="eksperimen">Eksperimen</option></select>
        <button class="tombol dsb-ekspor" type="button" id="dsb-ekspor">Ekspor CSV</button>
      </div></div>
    <div class="dsb-gulir">
      <table id="dsb-tabel" class="dsb-tabel-isi">
        <thead>
          <tr><th rowspan="2" data-urut="no">No</th><th rowspan="2" data-urut="nama">Varian</th><th rowspan="2" class="angka" data-urut="harga">Harga Aktual<br>(Rp)</th>
            <th colspan="3" class="tengah">Prediksi (Rp)</th><th colspan="2" class="tengah" id="dsb-th-interval">Interval 80%</th>
            <th rowspan="2" class="angka" data-urut="ubah" id="dsb-th-ubah">Perubahan<br>30 Hari (%)</th><th rowspan="2" data-urut="model">Metode / Model<br>Champion</th>
            <th rowspan="2" data-urut="status">Status<br>Validasi</th><th rowspan="2" class="angka" data-urut="percaya" title="Persen syarat uji yang lolos">Keyakinan<br>(%)</th></tr>
          <tr><th class="angka" data-urut="h7">7 Hari</th><th class="angka" data-urut="h14">14 Hari</th><th class="angka" data-urut="h30">30 Hari</th><th class="angka">Bawah</th><th class="angka">Atas</th></tr>
        </thead><tbody></tbody>
      </table>
    </div>
    <p class="dsb-catatan" id="dsb-catatan-status"></p>
  </section>
  <section class="dsb-kartu dsb-tren">
    <div class="dsb-kartu-kepala"><h2 id="dsb-judul-tren">Tren Harga</h2>
      <div class="segmen" id="dsb-rentang" role="group" aria-label="Rentang waktu grafik">
        <button type="button" data-hari="90" aria-pressed="false">3 bln</button><button type="button" data-hari="180" aria-pressed="true">6 bln</button><button type="button" data-hari="365" aria-pressed="false">1 th</button><button type="button" data-hari="0" aria-pressed="false">Semua</button>
      </div></div>
    <div class="dsb-kanvas"><canvas id="dsb-grafik-tren" role="img" aria-label="Grafik harga aktual dan proyeksi"></canvas></div>
    <div class="legenda" id="dsb-legenda"></div>
  </section>
  <section class="dsb-kartu dsb-banding"><div class="dsb-kartu-kepala"><h2>Perbandingan Harga Terkini (Rp)</h2></div>
    <div class="dsb-kanvas pendek"><canvas id="dsb-grafik-banding" role="img" aria-label="Perbandingan harga terkini antar wilayah"></canvas></div>
    <div class="legenda" id="dsb-legenda-banding"></div></section>
  <section class="dsb-kartu dsb-dispar"><div class="dsb-kartu-kepala"><h2>Disparitas Harga antar Wilayah (Rp)</h2></div>
    <div id="dsb-dispar"></div></section>
  <section class="dsb-kartu dsb-diag"><div class="dsb-kartu-kepala"><h2 id="dsb-judul-diag">Diagnostik Time Series</h2></div><div id="dsb-diag"></div></section>
  <section class="dsb-kartu dsb-metrik"><div class="dsb-kartu-kepala"><h2 id="dsb-judul-metrik">Metrik Performa Model</h2></div><div id="dsb-metrik"></div></section>
  <section class="dsb-kartu dsb-faktor"><div class="dsb-kartu-kepala"><h2>Faktor Pendorong Harga</h2></div><div id="dsb-faktor"></div></section>
</div>
<div class="dsb-bawah">
  <section class="dsb-kartu dsb-lineage"><div class="dsb-kartu-kepala"><h2>Data Lineage · Dari Sumber Data ke Model</h2></div><div id="dsb-lineage"></div></section>
  <section class="dsb-kartu dsb-rekom"><div class="dsb-kartu-kepala"><h2>Rekomendasi (Netral)</h2></div><div id="dsb-rekom"></div></section>
</div>
<h2 class="dsb-bagian">Analisis lanjutan</h2>
<div class="dsb-lanjut">
  <section class="dsb-kartu"><div class="dsb-kartu-kepala"><h2 id="dsb-judul-ringkas">Ringkasan varian terpilih</h2></div><div id="dsb-ringkas"></div></section>
  <section class="dsb-kartu"><div class="dsb-kartu-kepala"><h2>Kinerja model pada data uji akhir</h2></div><p class="dsb-catatan" id="dsb-sub-kinerja"></p><div id="dsb-kinerja"></div></section>
  <section class="dsb-kartu"><div class="dsb-kartu-kepala"><h2>Prakiraan 7 hari lawan kenyataan</h2></div><div class="dsb-kanvas pendek" id="dsb-uji-wadah"><canvas id="dsb-grafik-uji" role="img" aria-label="Prakiraan lawan kenyataan pada masa uji"></canvas></div></section>
  <section class="dsb-kartu dsb-lebar"><div class="dsb-kartu-kepala"><h2>Proyeksi hari raya</h2></div><p class="dsb-catatan" id="dsb-sub-acara"></p><div id="dsb-acara"></div></section>
  <section class="dsb-kartu dsb-lebar"><div class="dsb-kartu-kepala"><h2>Proyeksi triwulanan, semesteran, dan tahunan</h2>
    <div class="segmen" id="dsb-periode" role="group" aria-label="Jenis periode"><button type="button" data-p="triwulanan" aria-pressed="true">Triwulanan</button><button type="button" data-p="semesteran" aria-pressed="false">Semesteran</button><button type="button" data-p="tahunan" aria-pressed="false">Tahunan</button></div></div>
    <div id="dsb-periodik"></div></section>
  <section class="dsb-kartu"><div class="dsb-kartu-kepala"><h2>Rekomendasi varian terpilih</h2></div><div id="dsb-rekom-varian"></div></section>
  <section class="dsb-kartu"><div class="dsb-kartu-kepala"><h2>Jejak data dan versi</h2></div><div id="dsb-jejak"></div></section>
</div>
<footer class="dsb-kaki"><span>Badan Pusat Statistik &nbsp;|&nbsp; Bengkulu Tengah</span><span>Statistik Berkualitas untuk Indonesia Maju</span></footer>`;

/** Memasang dashboard ke dalam `wadah`. `meta` dipakai untuk nama wilayah dan keterangan lain bila perlu. */
export async function pasangDasborInternal(wadah, meta) {
  const $ = (id) => wadah.querySelector(`#${id}`);
  wadah.innerHTML = KERANGKA;

  let A, ACARA, PERIODIK;
  try {
    [A, ACARA, PERIODIK] = await Promise.all([muatJSON("analitik.json"), muatJSON("proyeksi_acara.json"), muatJSON("proyeksi_periodik.json")]);
  } catch (e) {
    tampilkanGalat(wadah, e);
    throw e;
  }
  void meta;

  const S = { kode: null, h: 30, hari: 180, urut: { kunci: "no", arah: 1 }, periode: "triwulanan", grafik: null, grafikBanding: null, grafikDispar: null,
    grafikUji: null, grafikPeriodik: null, seri: {} };
  const tingkat = A.tingkat_interval ?? 0.8;
  const persenTingkat = Math.round(tingkat * 100);

  const lencanaStatus = (s) => s === "valid" ? '<span class="lencana baik">Valid</span>' : '<span class="lencana sedang">Eksperimen</span>';
  const tanda = (ok) => ok === null || ok === undefined ? '<span class="tanda tunggu" title="Belum bisa dinilai">–</span>'
    : ok ? '<span class="tanda ok" title="Lolos">✓</span>' : '<span class="tanda gagal" title="Belum lolos">✕</span>';
  const nilaiAtau = (x, f = (v) => v) => x === null || x === undefined ? '<span class="menunggu">menunggu data</span>' : f(x);
  const pendek = (h) => (h ? String(h).slice(0, 8) : "–");
  const kelasUbah = (x) => (x === null || x === undefined ? "" : x > 0.05 ? "naik" : x < -0.05 ? "turun" : "");
  const angkaRp = (x) => (x === null || x === undefined ? "–" : Math.round(x).toLocaleString("id-ID"));
  const proy = (v, h) => v.proyeksi?.[String(h)] || null;
  const skor = (v) => (v.syarat_total ? Math.round(v.syarat_lolos / v.syarat_total * 100) : null);
  const varianTerpilih = () => A.varian.find((x) => x.kode === S.kode);

  /* ---------- kepala, indikator, kontrol */
  function kepala() {
    const wp = A.wilayah_proyek || { sasaran: "Bengkulu Tengah", pembanding: ["Kepahiang", "Kota Bengkulu"] };
    $("dsb-wilayah").textContent = `${wp.sasaran} | Pembanding: ${wp.pembanding.join(" dan ")}`;
    $("dsb-judul-tabel").textContent = `Tabel Proyeksi Harga Pangan · ${A.wilayah.nama} (${A.varian.length} Varian)`;
    $("dsb-cap").innerHTML = A.mode_demo
      ? '<span class="dsb-cap demo">DATA CONTOH · ANGKA ILUSTRATIF</span>'
      : `<span class="dsb-cap asli">DATA ASLI · per ${esc(tgl(A.dibuat_untuk))}</span>`;
    const k = A.kpi, au = A.audit || { status: "KUNING", alasan: "" };
    const tahap = (A.garis_data?.tahap || []).length;
    const kartu = (ikonNama, warnaIkon, nilai, label, sub, chip = "") => `<div class="dsb-k">
      <span class="dsb-k-ikon ${warnaIkon}">${ikon(ikonNama, 26)}</span>
      <div class="dsb-k-isi"><div class="dsb-k-atas"><strong>${nilai}</strong>${chip}</div><div class="dsb-k-label">${label}</div><div class="dsb-k-sub">${sub}</div></div></div>`;
    $("dsb-kpi").innerHTML = [
      kartu("database", "biru", `${k.sumber_aktif}/${k.sumber_terdaftar}`, "Sumber Data Aktif", "Sumber yang mengirim data", k.sumber_aktif ? '<span class="dsb-chip hijau">AKTIF</span>' : '<span class="dsb-chip merah">KOSONG</span>'),
      kartu("roda", "biru", `${tahap}/${tahap}`, "Pemrosesan Data", "Semua tahapan pemrosesan selesai", '<span class="dsb-chip hijau">LULUS</span>'),
      kartu("centang", "biru", k.skor_konsensus === null ? '<span class="dsb-k-kecil">Menunggu data</span>' : angka(k.skor_konsensus, 2), "Skor Kesepakatan Sumber",
        k.skor_konsensus === null ? "Butuh minimal dua sumber harga" : "Kecocokan harga antar sumber"),
      kartu("kalender", "biru", k.hari_tertinggal === null ? "–" : `${k.hari_tertinggal} hari`, "Kesegaran Data", `(per ${esc(tgl(A.dibuat_untuk))})`),
      kartu("database", "biru", `${angka(k.kelengkapan_persen, 0)}%`, "Kelengkapan Data", `${k.varian_berdata}/${k.varian_aktif} varian`),
      kartu("dokumen", "biru", `<span class="dsb-audit ${au.status.toLowerCase()}">${esc(au.status)}</span>`, "Status Audit", esc(au.alasan)),
    ].join("");
    $("dsb-origin").innerHTML = `<option>${esc(tgl(A.dibuat_untuk, true))} (data terakhir)</option>`;
    $("dsb-varian").innerHTML = A.varian.map((v) => `<option value="${esc(v.kode)}">${esc(v.nama)}</option>`).join("");
  }

  /* ---------- tabel */
  const nilaiUrut = {
    no: (v) => A.varian.indexOf(v), nama: (v) => v.nama, harga: (v) => v.harga_aktual ?? -1, h7: (v) => proy(v, 7)?.prediksi ?? -1,
    h14: (v) => proy(v, 14)?.prediksi ?? -1, h30: (v) => proy(v, 30)?.prediksi ?? -1, ubah: (v) => proy(v, S.h)?.perubahan_persen ?? -999,
    model: (v) => v.nama_model, status: (v) => v.status, percaya: (v) => skor(v) ?? -1 + URUT_PERCAYA[v.kepercayaan] / 10,
  };

  function daftarTampil() {
    const kel = $("dsb-kelompok").value, st = $("dsb-status-filter").value;
    const u = nilaiUrut[S.urut.kunci] || nilaiUrut.no;
    return A.varian.filter((v) => (!kel || v.kelompok === kel) && (!st || v.status === st))
      .sort((a, b) => { const x = u(a), y = u(b); return (x < y ? -1 : x > y ? 1 : 0) * S.urut.arah; });
  }

  function gambarTabel() {
    const baris = daftarTampil();
    const sel = (v, h) => { const p = proy(v, h); return `<td class="angka">${p ? angkaRp(p.prediksi) : "–"}</td>`; };
    $("dsb-tabel").querySelector("tbody").innerHTML = baris.map((v) => {
      const p = proy(v, S.h);
      const s = skor(v);
      return `<tr data-kode="${esc(v.kode)}" class="${v.kode === S.kode ? "terpilih" : ""}" tabindex="0">
        <td class="angka">${A.varian.indexOf(v) + 1}</td><td class="dsb-nama" title="${esc(v.nama)}">${esc(v.nama.replace(" Kualitas", ""))}</td><td class="angka">${angkaRp(v.harga_aktual)}</td>${sel(v, 7)}${sel(v, 14)}${sel(v, 30)}
        <td class="angka">${p ? angkaRp(p.bawah) : "–"}</td><td class="angka">${p ? angkaRp(p.atas) : "–"}</td>
        <td class="angka dsb-ubah ${kelasUbah(p?.perubahan_persen)}">${persen(p?.perubahan_persen, 1, true)}</td>
        <td class="dsb-model" title="${esc(v.nama_model)}">${esc(NAMA_PENDEK[v.model] || v.nama_model)}</td>
        <td>${lencanaStatus(v.status)}</td><td class="angka" title="${v.syarat_lolos} dari ${v.syarat_total} syarat uji lolos (${esc(NAMA_PERCAYA[v.kepercayaan] || "")})">${s === null ? "–" : s}</td></tr>`;
    }).join("") || `<tr><td colspan="12" class="kosong">Tidak ada varian yang cocok dengan pilihan.</td></tr>`;
    $("dsb-th-interval").textContent = `Interval ${persenTingkat}% (${S.h} Hari)`;
    $("dsb-th-ubah").innerHTML = `Perubahan<br>${S.h} Hari (%)`;
    $("dsb-tabel").querySelectorAll("th[data-urut]").forEach((th) => {
      th.setAttribute("aria-sort", th.dataset.urut === S.urut.kunci ? (S.urut.arah > 0 ? "ascending" : "descending") : "none");
    });
    const valid = A.varian.filter((v) => v.status === "valid").length;
    $("dsb-catatan-status").innerHTML = `<b>${valid}</b> dari ${A.varian.length} varian <b>Valid</b>. Eksperimen = ada syarat uji yang belum lolos (angka bahan pertimbangan, bukan angka resmi). Keyakinan = persen syarat uji yang lolos.`;
  }

  function ekspor() {
    const kolom = ["kode", "varian", "kelompok", "satuan", "tanggal_harga", "harga_aktual", "prediksi_7", "bawah_7", "atas_7", "prediksi_14", "bawah_14", "atas_14",
      "prediksi_30", "bawah_30", "atas_30", "perubahan_30_persen", "cara_prakiraan", "status_validasi", "keyakinan_persen", "smape_uji_akhir", "cakupan_uji_akhir"];
    const baris = daftarTampil().map((v) => {
      const o = { kode: v.kode, varian: v.nama, kelompok: v.kelompok, satuan: v.satuan, tanggal_harga: v.tanggal_aktual, harga_aktual: v.harga_aktual,
        perubahan_30_persen: proy(v, 30)?.perubahan_persen, cara_prakiraan: v.nama_model, status_validasi: v.status, keyakinan_persen: skor(v),
        smape_uji_akhir: v.holdout?.smape, cakupan_uji_akhir: v.holdout?.cakupan_persen };
      for (const h of [7, 14, 30]) { const p = proy(v, h); o[`prediksi_${h}`] = p?.prediksi; o[`bawah_${h}`] = p?.bawah; o[`atas_${h}`] = p?.atas; }
      return o;
    });
    unduhTeks(`proyeksi_harga_${A.dibuat_untuk}.csv`, keCSV(kolom, baris));
  }

  /* ---------- varian terpilih */
  async function muatSeri(kode) {
    if (!(kode in S.seri)) { try { S.seri[kode] = await muatJSON(`seri/${kode}.json`); } catch { S.seri[kode] = null; } }
    return S.seri[kode];
  }

  async function pilih(kode, gulir = false) {
    S.kode = kode;
    $("dsb-varian").value = kode;
    gambarTabel();
    const v = varianTerpilih();
    await muatSeri(kode);
    gambarTren(v);
    ringkasVarian(v);
    diagnostik(v);
    metrik(v);
    kinerja(v);
    gambarUji(v);
    faktor(v);
    banding(v);
    disparitas(v);
    acaraVarian(v);
    periodik(v);
    rekomVarian(v);
    if (gulir) $("dsb-judul-tren").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function gambarTren(v) {
    $("dsb-judul-tren").textContent = `Tren Harga ${v.nama} (Rp/${v.satuan})`;
    $("dsb-legenda").innerHTML = legendaDashboard();
    if (S.grafik) { S.grafik.destroy(); S.grafik = null; }
    const seri = S.seri[v.kode];
    if (!seri || !window.Chart) return;
    S.grafik = gambarGrafikHarga($("dsb-grafik-tren"), potongSeri(seri, S.hari), { gaya: "dashboard", horizon: S.h, tingkat, dariNol: false });
  }

  function ringkasVarian(v) {
    $("dsb-judul-ringkas").textContent = `Ringkasan · ${v.nama}`;
    const baris = [7, 14, 30].map((h) => {
      const p = proy(v, h);
      return p ? `<tr class="${h === S.h ? "terpilih" : ""}"><td>${h} hari<br><span class="meta-kecil">${esc(tgl(p.tanggal))}</span></td><td class="angka"><strong>${rp(p.prediksi)}</strong></td>
        <td class="angka">${rp(p.bawah)} sampai ${rp(p.atas)}</td><td class="angka dsb-ubah ${kelasUbah(p.perubahan_persen)}">${persen(p.perubahan_persen, 1, true)}</td></tr>` : "";
    }).join("");
    $("dsb-ringkas").innerHTML = `
      <dl class="dl"><dt>Harga aktual</dt><dd><strong>${rp(v.harga_aktual)}</strong> <span class="meta-kecil">${esc(tgl(v.tanggal_aktual))}</span></dd>
      <dt>Cara prakiraan</dt><dd>${esc(v.nama_model)}</dd><dt>Status</dt><dd>${lencanaStatus(v.status)}</dd>
      <dt>Riwayat</dt><dd>${angka(v.jumlah_obs)} hari harga sejak ${esc(tgl(v.tanggal_awal))}</dd></dl>
      <div class="gulir-tabel"><table class="tabel-kecil"><thead><tr><th>Horizon</th><th class="angka">Prediksi</th><th class="angka">Interval ${persenTingkat}%</th><th class="angka">Perubahan</th></tr></thead><tbody>${baris}</tbody></table></div>
      ${v.catatan?.length ? `<details><summary class="meta-kecil">Catatan mesin (${v.catatan.length})</summary><ul class="meta-kecil">${v.catatan.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></details>` : ""}
      ${kartuModel(v)}`;
  }

  function kartuModel(v) {
    const k = v.kartu_model;
    if (!k) return "";
    return `<details style="margin-top:8px"><summary class="meta-kecil"><b>Kartu model</b></summary>
      <dl class="dl" style="margin-top:8px"><dt>Tujuan</dt><dd>${esc(k.tujuan)}</dd>
      <dt>Data</dt><dd>${esc(k.data.wilayah)}; ${esc(tgl(k.data.dari))} sampai ${esc(tgl(k.data.sampai))}; ${angka(k.data.jumlah_hari_berharga)} hari berharga</dd>
      <dt>Cara prakiraan</dt><dd>${esc(k.model.nama)}</dd>
      <dt>Cara memilih</dt><dd class="meta-kecil">${esc(k.model.cara_memilih)}</dd>
      <dt>Yang dicoba</dt><dd class="meta-kecil">${k.model.kandidat.map(esc).join("; ")}</dd></dl>
      <p class="meta-kecil" style="margin:8px 0 2px"><b>Keterbatasan</b></p><ul class="meta-kecil">${k.keterbatasan.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></details>`;
  }

  /* ---------- wilayah: perbandingan dan disparitas */
  const bersihNama = (n) => String(n).replace(/\s*\(PIHPS BI\)/, "");
  // Pembanding wilayah sasaran proyek: Kepahiang dan Kota Bengkulu.
  const pembandingNyata = (seri) => Object.values(seri?.pembanding || {}).filter((p) => /kepahiang|kota bengkulu/i.test(p.nama)).map((p) => ({ ...p, nama: bersihNama(p.nama) }));
  const terakhirAda = (arr) => { for (let i = arr.length - 1; i >= 0; i--) if (arr[i] != null) return arr[i]; return null; };

  async function banding() {
    if (S.grafikBanding) { S.grafikBanding.destroy(); S.grafikBanding = null; }
    const kodeAda = KOMODITAS_BANDING.filter((k) => A.varian.some((v) => v.kode === k));
    await Promise.all(kodeAda.map(muatSeri));
    const nama = ["Kepahiang", "Kota Bengkulu"];
    const c = { a: warna("series-1"), b: warna("series-2"), d: warna("series-3"), muted: warna("muted"), grid: warna("grid") };
    const dataUtama = kodeAda.map((k) => A.varian.find((v) => v.kode === k).harga_aktual);
    const set = [{ label: A.wilayah.nama, data: dataUtama, backgroundColor: c.a, borderRadius: 3 }];
    const adaNama = new Set();
    for (const n of nama) {
      const data = kodeAda.map((k) => { const p = pembandingNyata(S.seri[k]).find((x) => x.nama.toLowerCase().includes(n.toLowerCase())); return p ? terakhirAda(p.nilai) : null; });
      if (data.some((x) => x != null)) { adaNama.add(n); set.push({ label: n, data, backgroundColor: n === "Kepahiang" ? c.b : c.d, borderRadius: 3 }); }
    }
    $("dsb-legenda-banding").innerHTML = [`<span><i style="background:${c.a}" class="dsb-titik"></i>${esc(A.wilayah.nama)}</span>`,
      ...nama.map((n) => adaNama.has(n) ? `<span><i style="background:${n === "Kepahiang" ? c.b : c.d}" class="dsb-titik"></i>${n}</span>`
        : `<span class="menunggu"><i class="dsb-titik kosong"></i>${n} (menunggu data)</span>`)].join("");
    if (!window.Chart || !kodeAda.length) return;
    S.grafikBanding = new window.Chart($("dsb-grafik-banding"), {
      type: "bar",
      data: { labels: kodeAda.map((k) => NAMA_BANDING[k]), datasets: set },
      options: { responsive: true, maintainAspectRatio: false, animation: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (i) => `${i.dataset.label}: ${rp(i.raw)}` } } },
        scales: { x: { grid: { display: false }, ticks: { color: c.muted } }, y: { grid: { color: c.grid }, border: { display: false }, beginAtZero: true,
          ticks: { color: c.muted, callback: (val) => new Intl.NumberFormat("id-ID").format(val) } } } },
    });
  }

  function disparitas(v) {
    if (S.grafikDispar) { S.grafikDispar.destroy(); S.grafikDispar = null; }
    const seri = S.seri[v.kode];
    const lain = pembandingNyata(seri);
    const wadahDispar = $("dsb-dispar");
    if (!seri || !lain.length || !window.Chart) {
      wadahDispar.innerHTML = '<p class="menunggu-blok">Menunggu data. Selisih harga antar wilayah dihitung begitu harga wilayah pembanding masuk.</p>';
      return;
    }
    wadahDispar.innerHTML = '<div class="dsb-kanvas pendek"><canvas id="dsb-grafik-dispar" role="img" aria-label="Disparitas harga antar wilayah"></canvas></div>';
    const n = Math.min(seri.tanggal.length, 365);
    const mulai = seri.tanggal.length - n;
    const c = { m: warna("muted"), g: warna("grid"), w: [warna("series-2"), warna("series-3"), warna("series-4")] };
    S.grafikDispar = new window.Chart(wadahDispar.querySelector("canvas"), {
      type: "line",
      data: { labels: seri.tanggal.slice(mulai), datasets: lain.map((p, i) => ({ label: `${A.wilayah.nama} dikurangi ${p.nama}`, borderColor: c.w[i % 3], borderWidth: 1.6, pointRadius: 0, spanGaps: true,
        data: seri.aktual.slice(mulai).map((a, j) => (a != null && p.nilai[mulai + j] != null ? a - p.nilai[mulai + j] : null)) })) },
      options: { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: "index", intersect: false },
        plugins: { legend: { display: true, labels: { boxWidth: 10, color: c.m } }, tooltip: { callbacks: { title: (i) => tgl(i[0].label), label: (i) => `${rp(i.raw)}  ${i.dataset.label}` } } },
        scales: { x: { grid: { display: false }, ticks: { color: c.m, maxRotation: 0, autoSkipPadding: 28, callback(val) { return tgl(this.getLabelForValue(val)); } } },
          y: { grid: { color: c.g }, border: { display: false }, ticks: { color: c.m } } } },
    });
  }

  /* ---------- diagnostik, metrik, faktor */
  function diagnostik(v) {
    $("dsb-judul-diag").textContent = `Diagnostik Time Series (${v.nama})`;
    const d = v.diagnostik || {};
    const musiman = d.kekuatan_musiman;
    const kelasMusiman = musiman == null ? null : musiman < 0.3 ? "lemah" : musiman < 0.6 ? "moderat" : "kuat";
    const p = (x) => (x == null ? "–" : angka(x, 3));
    const pKpss = (x) => (x == null ? "–" : x <= 0.0101 ? "≤ 0,01" : x >= 0.0999 ? "≥ 0,10" : angka(x, 3));  // pustaka KPSS membulatkan ke 0,01 sampai 0,10
    const ubin = (judul, isi, ket, kelas = "") => `<div class="dsb-ubin ${kelas}"><span class="dsb-ubin-j">${judul}</span><div class="dsb-ubin-n${String(isi).length > 9 && !String(isi).includes("<") ? " kecil" : ""}">${isi}</div><span class="dsb-ubin-k">${ket}</span></div>`;
    $("dsb-diag").innerHTML = `<div class="dsb-ubin-baris">
      ${ubin("Stasioneritas (p-value)", `<span class="dsb-dua"><b>ADF</b> ${p(d.adf_p)}</span><span class="dsb-dua"><b>KPSS</b> ${pKpss(d.kpss_p)}</span>`,
        d.stasioner == null ? "menunggu data" : d.stasioner ? "(stasioner)" : "(belum stasioner)", d.stasioner === false ? "kuning" : "")}
      ${ubin("Seasonal Strength", musiman == null ? "–" : angka(musiman, 2), kelasMusiman ? `(${kelasMusiman})` : "menunggu data")}
      ${ubin("Volatility Regime", d.rezim_volatilitas ? esc(d.rezim_volatilitas.charAt(0).toUpperCase() + d.rezim_volatilitas.slice(1)) : "–",
        d.rezim_volatilitas ? (d.rezim_volatilitas === "tinggi" ? "(bergejolak)" : "(stabil)") : "menunggu data", d.rezim_volatilitas === "tinggi" ? "kuning" : "")}
      ${ubin("Structural Break", d.patahan_struktural == null ? "–" : d.patahan_struktural ? "Terdeteksi" : "Tidak terdeteksi", d.psi != null ? `PSI ${angka(d.psi, 3)}` : "menunggu data", d.patahan_struktural ? "kuning" : "")}
    </div>`;
  }

  function metrik(v) {
    $("dsb-judul-metrik").textContent = `Metrik Performa Model (${v.nama})`;
    const ho = v.holdout;
    if (!ho) { $("dsb-metrik").innerHTML = '<p class="menunggu-blok">Menunggu data. Belum ada masa uji akhir untuk varian ini.</p>'; return; }
    const ambang = v.validasi?.ambang_smape;
    const syarat = (nama) => (v.validasi?.syarat || []).find((s) => s.syarat.startsWith(nama))?.lolos;
    const nilaiPsi = v.diagnostik?.psi;
    const ket = (ok, baik, buruk) => (ok === null || ok === undefined ? "menunggu data" : `(${ok ? baik : buruk})`);
    const ubin = (judul, nilai, k, ok) => `<div class="dsb-ubin ${ok === false ? "kuning" : ""}"><span class="dsb-ubin-j">${judul}</span><div class="dsb-ubin-n">${nilai}</div><span class="dsb-ubin-k">${k}</span></div>`;
    $("dsb-metrik").innerHTML = `<div class="dsb-ubin-baris lima">
      ${ubin("sMAPE", ho.smape == null ? "–" : `${angka(ho.smape, 1)}%`, ket(syarat("sMAPE"), "baik", `di atas batas ${ambang ?? ""}%`), syarat("sMAPE"))}
      ${ubin("MASE", ho.mase == null ? "–" : angka(ho.mase, 2), ket(syarat("MASE"), "baik", "belum lolos"), syarat("MASE"))}
      ${ubin("Bias", ho.bias_persen == null ? "–" : `${angka(ho.bias_persen, 1)}%`, ket(syarat("Bias"), "rendah", "tinggi"), syarat("Bias"))}
      ${ubin(`Coverage (${persenTingkat}%)`, ho.cakupan_persen == null ? "–" : `${angka(ho.cakupan_persen, 1)}%`, ket(syarat("Cakupan"), "sesuai", "di luar 75 sampai 85%"), syarat("Cakupan"))}
      ${ubin("Drift (PSI)", nilaiPsi == null ? "–" : angka(nilaiPsi, 2), nilaiPsi == null ? "menunggu data" : nilaiPsi > 0.25 ? "(bergeser)" : "(stabil)", nilaiPsi == null ? null : nilaiPsi <= 0.25)}
    </div>`;
  }

  function faktor(v) {
    const p = v.pendorong || [];
    $("dsb-faktor").innerHTML = p.length
      ? `<ul class="dsb-faktor-daftar">${p.map((x) => {
        const panah = x.arah === "naik" ? "▲" : x.arah === "turun" ? "▼" : x.arah === "bergeser" ? "◆" : "•";
        const nilai = typeof x.nilai === "number" ? `${angka(x.nilai, x.satuan === "hari" ? 0 : 2)}${x.satuan ? (x.satuan === "%" ? "%" : ` ${x.satuan}`) : ""}` : esc(x.nilai);
        return `<li><span class="panah ${x.arah === "naik" ? "naik" : x.arah === "turun" ? "turun" : ""}">${panah}</span><span class="dsb-faktor-nama">${esc(x.nama)}</span><strong>${nilai}</strong></li>`;
      }).join("")}</ul><p class="dsb-catatan">Dihitung dari data harga sendiri, bukan SHAP.</p>`
      : '<p class="menunggu-blok">Menunggu data. Belum ada faktor yang dapat diukur.</p>';
  }

  /* ---------- kinerja rinci, uji vs kenyataan */
  function kinerja(v) {
    const ho = v.holdout, va = v.validasi || {};
    $("dsb-sub-kinerja").textContent = ho
      ? `${ho.hari} hari terakhir disisihkan dan tidak dipakai memilih cara prakiraan. ${ho.jumlah_origin} titik awal, ${angka(ho.n)} pasangan prakiraan dan kenyataan.`
      : "Belum ada masa uji akhir untuk varian ini.";
    const syarat = (va.syarat || []).map((s) => `<tr><td>${esc(s.syarat)}</td><td class="angka">${s.nilai == null ? "–" : esc(typeof s.nilai === "number" ? angka(s.nilai, Number.isInteger(s.nilai) ? 0 : 2) : s.nilai)}</td><td class="angka meta-kecil">${esc(s.target)}</td><td>${tanda(s.lolos)}</td></tr>`).join("");
    let isi = `<div class="gulir-tabel"><table class="tabel-kecil"><thead><tr><th>Syarat</th><th class="angka">Hasil</th><th class="angka">Target</th><th></th></tr></thead><tbody>${syarat || '<tr><td colspan="4" class="kosong">Tidak ada syarat yang dinilai.</td></tr>'}</tbody></table></div>`;
    if (ho) {
      const dm = ho.uji_dm, ph = ho.per_horizon || {};
      isi += `<dl class="dl" style="margin-top:10px">
        <dt>Lebih baik dari harga terakhir</dt><dd>${nilaiAtau(ho.perbaikan_vs_naif_persen, (x) => persen(x, 1, true))} <span class="meta-kecil">(menang di ${ho.menang_origin_vs_naif} dari ${ho.jumlah_origin} titik awal)</span></dd>
        <dt>Uji Diebold-Mariano</dt><dd>${dm && dm.p !== null ? `p = ${angka(dm.p, 3)} (n = ${dm.n})` : '<span class="menunggu">tidak berlaku untuk cara pembanding</span>'}</dd>
        ${["7", "14", "30"].filter((h) => ph[h]).map((h) => `<dt>Meleset ${h} hari</dt><dd>${persen(ph[h].smape, 2)} <span class="meta-kecil">(bias ${persen(ph[h].bias_persen, 2, true)}, n = ${ph[h].n})</span></dd>`).join("")}
      </dl>`;
    }
    if (va.gagal?.length) isi += `<p class="pesan peringatan" style="margin-top:10px">Belum lolos: ${va.gagal.map(esc).join(", ")}.</p>`;
    $("dsb-kinerja").innerHTML = isi;
  }

  function gambarUji(v) {
    if (S.grafikUji) { S.grafikUji.destroy(); S.grafikUji = null; }
    const wadahUji = $("dsb-uji-wadah");
    const t = v.holdout?.titik_h7 || [];
    if (!t.length || !window.Chart) { wadahUji.innerHTML = '<p class="menunggu-blok">Menunggu data. Masa uji akhir belum tersedia untuk varian ini.</p>'; return; }
    wadahUji.innerHTML = '<canvas id="dsb-grafik-uji" role="img" aria-label="Prakiraan lawan kenyataan pada masa uji"></canvas>';
    const c = { a: warna("series-1"), p: warna("series-2"), grid: warna("grid"), muted: warna("muted") };
    S.grafikUji = new window.Chart(wadahUji.querySelector("canvas"), {
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

  /* ---------- hari raya */
  function acaraVarian(v) {
    const aktif = ACARA.acara.filter((a) => a.fase !== "belum_dimulai" && a.fase !== "selesai");
    const berikut = ACARA.acara.find((a) => a.fase === "belum_dimulai");
    $("dsb-sub-acara").textContent = `Menuju Hari H dari H-7 dan H-3; sesudahnya H+3, H+7, H+14. Diuji dengan menyisihkan satu hari raya bergiliran (minimal ${ACARA.aturan.minimal_acara} hari raya sejenis).`;
    let isi = "";
    if (berikut) {
      isi += `<div class="pesan" style="margin-bottom:12px"><b>${esc(berikut.nama)}</b>, ${esc(tgl(berikut.tanggal, true))} (${berikut.hari_menuju} hari lagi). Proyeksi menuju Hari H muncul otomatis mulai ${esc(tgl(berikut.proyeksi_mulai, true))} (H-7), dihitung dari harga pada saat itu.</div>`;
    }
    for (const a of aktif) {
      const ent = a.varian.find((x) => x.kode === v.kode);
      if (!ent) continue;
      isi += `<h3 class="sub-judul">${esc(a.nama)} · ${esc(tgl(a.tanggal))}</h3><div class="gulir-tabel"><table class="tabel-kecil"><thead><tr><th>Titik</th><th class="angka">Harga asal</th><th class="angka">Prediksi</th><th class="angka">Interval ${persenTingkat}%</th><th class="angka">Selisih</th><th class="angka">Kenyataan</th><th>Status</th></tr></thead><tbody>${ent.baris.map((b) => b.prediksi === null
        ? `<tr><td>${esc(b.kode)}</td><td class="angka">${rp(b.asal)}</td><td colspan="5" class="meta-kecil">${esc(b.alasan)}</td></tr>`
        : `<tr><td>${esc(b.kode)}<br><span class="meta-kecil">${esc(tgl(b.sasaran_tanggal))}</span></td><td class="angka">${rp(b.asal)}</td><td class="angka"><strong>${rp(b.prediksi)}</strong></td><td class="angka">${rp(b.bawah)} sampai ${rp(b.atas)}</td><td class="angka dsb-ubah ${kelasUbah(b.delta_persen)}">${rp(b.delta_rp)} (${persen(b.delta_persen, 1, true)})</td><td class="angka">${b.aktual ? rp(b.aktual) : "–"}</td><td>${lencanaStatus(b.status)}</td></tr>`).join("")}</tbody></table></div>`;
    }
    const ev = ACARA.evaluasi.filter((e) => e.kode === v.kode);
    const urutOffset = ["H-7", "H-3", "H+3", "H+7", "H+14"];
    if (ev.length) {
      isi += `<h3 class="sub-judul">Uji pada hari raya yang sudah lewat · ${esc(v.nama)}</h3><div class="gulir-tabel"><table class="tabel-kecil"><thead><tr><th>Hari raya</th><th>Titik</th><th class="angka">Jumlah</th><th class="angka">Meleset</th><th class="angka">Meleset harga terakhir</th><th class="angka">Lebih baik</th><th class="angka">Tepat dalam interval</th><th>Status</th></tr></thead><tbody>${ev.flatMap((e) => urutOffset.filter((o) => e.offset[o]).map((o) => {
        const x = e.offset[o];
        return x.smape === undefined
          ? `<tr><td>${esc(e.jenis)}</td><td>${o}</td><td class="angka">${x.n_acara}</td><td colspan="4" class="meta-kecil">${esc((x.gagal || []).join(", "))}</td><td>${lencanaStatus(x.status)}</td></tr>`
          : `<tr><td>${esc(e.jenis)}</td><td>${o}</td><td class="angka">${x.n_acara}</td><td class="angka">${persen(x.smape, 2)}</td><td class="angka">${persen(x.smape_naif, 2)}</td><td class="angka">${persen(x.perbaikan_vs_naif_persen, 1, true)}</td><td class="angka">${persen(x.cakupan_persen, 0)}</td><td>${lencanaStatus(x.status)}</td></tr>`;
      })).join("")}</tbody></table></div>
      <details style="margin-top:8px"><summary class="meta-kecil">Rincian per hari raya (harga asal, prediksi, kenyataan)</summary><div class="gulir-tabel"><table class="tabel-kecil"><thead><tr><th>Hari raya</th><th>Titik</th><th>Tanggal Hari H</th><th class="angka">Harga asal</th><th class="angka">Prediksi</th><th class="angka">Kenyataan</th><th>Dalam interval</th></tr></thead><tbody>${ev.flatMap((e) => urutOffset.filter((o) => e.offset[o]?.rincian).flatMap((o) => e.offset[o].rincian.map((r) => `<tr><td>${esc(e.jenis)}</td><td>${o}</td><td>${esc(tgl(r.tanggal_hr))}</td><td class="angka">${rp(r.asal)}</td><td class="angka">${rp(r.prediksi)}</td><td class="angka">${rp(r.sasaran)}</td><td>${tanda(r.dalam_interval)}</td></tr>`))).join("")}</tbody></table></div></details>
      <p class="meta-kecil" style="margin-top:8px">Cara: harga asal dikalikan median perubahan pada hari raya sejenis sebelumnya. Cakupan interval belum bisa dinilai bila hari raya sejenis kurang dari ${ACARA.aturan.minimal_acara_cakupan}, jadi statusnya tetap Eksperimen.</p>`;
    }
    $("dsb-acara").innerHTML = isi || '<p class="menunggu-blok">Menunggu data. Belum ada hari raya yang cukup berdata.</p>';
  }

  /* ---------- periodik */
  function periodik(v) {
    const info = PERIODIK.periode[S.periode];
    const wadahP = $("dsb-periodik");
    if (S.grafikPeriodik) { S.grafikPeriodik.destroy(); S.grafikPeriodik = null; }
    if (!info) { wadahP.innerHTML = '<p class="menunggu-blok">Menunggu data.</p>'; return; }
    if (!info.tersedia) {
      const pct = Math.min(100, info.bulan_tersedia / info.minimal_bulan * 100);
      wadahP.innerHTML = `<div class="pesan peringatan"><b>Menunggu data.</b> ${esc(info.alasan)}</div>
        <div class="ind-meter" style="margin-top:10px"><span style="width:${pct.toFixed(1)}%"></span></div><p class="meta-kecil">${info.bulan_tersedia} dari ${info.minimal_bulan} bulan data tersedia.</p>`;
      return;
    }
    const p = info.varian.find((x) => x.kode === v.kode);
    if (!p || !p.dasar) { wadahP.innerHTML = `<p class="menunggu-blok">Menunggu data. ${esc((p?.gagal || ["Riwayat bulanan varian ini belum cukup."]).join(" "))}</p>`; return; }
    const r = p.rata_periode;
    wadahP.innerHTML = `
      <div class="skenario">
        <div class="skenario-kotak rendah"><span>Skenario rendah</span><strong>${rp(r.rendah)}</strong></div>
        <div class="skenario-kotak dasar"><span>Skenario dasar</span><strong>${rp(r.dasar)}</strong><em class="dsb-ubah ${kelasUbah(p.perubahan_vs_periode_lalu_persen)}">${persen(p.perubahan_vs_periode_lalu_persen, 1, true)} dari periode lalu (${rp(p.rata_periode_lalu)})</em></div>
        <div class="skenario-kotak tinggi"><span>Skenario tinggi</span><strong>${rp(r.tinggi)}</strong></div>
      </div>
      <div class="dsb-kanvas pendek"><canvas id="dsb-grafik-periodik" role="img" aria-label="Skenario harga rata-rata bulanan"></canvas></div>
      <p class="meta-kecil">${lencanaStatus(p.status)} ${p.gagal?.length ? `Belum lolos: ${p.gagal.map(esc).join(", ")}. ` : ""}Cara: ${esc(p.nama_model)}. Meleset uji ${persen(p.evaluasi.smape, 2)} (harga terakhir: ${persen(p.evaluasi.smape_naif, 2)}), tepat dalam interval ${persen(p.evaluasi.cakupan_persen, 0)}. Rata-rata ${info.bulan_per_periode} bulan ke depan: ${info.bulan_target.map((b) => esc(b)).join(", ")}. Skenario rendah dan tinggi adalah batas bawah dan atas ${persenTingkat}%.</p>`;
    if (!window.Chart) return;
    const riw = p.riwayat_bulanan || [];
    const label = [...riw.map((x) => x.bulan), ...info.bulan_target];
    const kosong = (n) => Array(n).fill(null);
    const c = { a: warna("series-1"), p: warna("series-2"), s3: warna("series-3"), s4: warna("series-4"), grid: warna("grid"), muted: warna("muted") };
    const sambung = (arr) => [...kosong(riw.length - 1), riw.at(-1)?.rata ?? null, ...arr];
    S.grafikPeriodik = new window.Chart(wadahP.querySelector("canvas"), {
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

  /* ---------- rekomendasi, lineage, jejak */
  function rekomUmum() {
    const r = A.rekomendasi_umum || [];
    const au = A.audit || {};
    $("dsb-rekom").innerHTML = `<div class="dsb-rekom-isi">
      <ol class="dsb-rekom-daftar">${r.map((x, i) => `<li><span class="dsb-no ${esc(x.warna)}">${i + 1}</span><div><strong class="${esc(x.warna)}">${esc(x.judul)}</strong><p>${esc(x.isi)}</p></div></li>`).join("")}</ol>
      <aside class="dsb-catatan-kotak"><b>Catatan:</b><ul>
        <li>Angka berasal dari ${A.mode_demo ? "data contoh (ilustratif)" : "data asli"} sampai ${esc(tgl(A.dibuat_untuk, true))}.</li>
        <li>Status Eksperimen berarti belum lolos protokol validasi; gunakan sebagai bahan pertimbangan.</li>
        <li>Dashboard ini mendukung analisis internal BPS dan dapat dipakai bersama pemangku kepentingan terkait.</li>
        ${au.status && au.status !== "HIJAU" ? `<li>Status audit ${esc(au.status)}: ${esc(au.alasan)}.</li>` : ""}
      </ul></aside></div>`;
  }

  function rekomVarian(v) {
    const terbesar = [...A.varian].filter((x) => proy(x, 30)?.perubahan_persen != null)
      .sort((a, b) => Math.abs(proy(b, 30).perubahan_persen) - Math.abs(proy(a, 30).perubahan_persen)).slice(0, 5);
    $("dsb-rekom-varian").innerHTML = `<p class="rekomendasi-utama">${esc(v.rekomendasi)}</p>
      <h3 class="sub-judul">Perubahan 30 hari terbesar</h3>
      <ul class="daftar-pendorong">${terbesar.map((x) => { const p = proy(x, 30); return `<li><button type="button" class="tautan-varian" data-kode="${esc(x.kode)}">${esc(x.nama)}</button><strong class="dsb-ubah ${kelasUbah(p.perubahan_persen)}">${persen(p.perubahan_persen, 1, true)}</strong>${x.status === "valid" ? "" : ' <span class="meta-kecil">Eksperimen</span>'}</li>`; }).join("")}</ul>`;
  }

  function lineage() {
    const g = A.garis_data;
    const model = Object.entries(A.model_dipakai || {}).sort((a, b) => b[1] - a[1]);
    const sumber = A.sumber_nama || [];
    const kotak = (warnaKotak, ikonNama, judul, subjudul, butir) => `<div class="dsb-lin ${warnaKotak}"><div class="dsb-lin-kepala"><span class="dsb-lin-ikon">${ikon(ikonNama, 22)}</span><div><b>${judul}</b><span>${subjudul}</span></div></div><ul>${butir.map((x) => `<li>${x}</li>`).join("")}</ul></div>`;
    $("dsb-lineage").innerHTML = `<div class="dsb-lin-baris">
      ${kotak("hijau", "database", "Sumber Data", `${A.kpi.sumber_aktif}/${A.kpi.sumber_terdaftar} sumber aktif`, sumber.length ? sumber.map(esc) : ["Belum ada sumber yang mengirim data"])}
      <span class="dsb-panah">→</span>
      ${kotak("biru", "roda", "Pemeriksaan dan Pembersihan", `${angka(A.kpi.varian_berdata)} varian berdata`, ["Validasi", "Standarisasi satuan dan kode", "Quality gate", `${angka(A.kpi.perlu_validasi)} data menunggu validasi`])}
      <span class="dsb-panah">→</span>
      ${kotak("biru", "dokumen", `Snapshot Data (${esc(tgl(A.dibuat_untuk))})`, `Versi data ${esc(pendek(g.versi_data))}`, ["Deret harian per varian", "Fitur lag dan rata-rata bergulir", "Fitur kalender hari raya", `Konfigurasi ${esc(pendek(g.versi_konfigurasi))}`])}
      <span class="dsb-panah">→</span>
      ${kotak("biru", "otak", "Model Champion (per varian)", `${A.kpi.varian_valid} Valid, ${A.kpi.varian_eksperimen} Eksperimen`, model.length ? model.map(([m, n]) => `${esc(NAMA_PENDEK[m] || m)} (${n})`) : ["Belum ada"])}
    </div>`;
  }

  function jejak() {
    const g = A.garis_data;
    $("dsb-jejak").innerHTML = `
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
  const atur = (grup, atribut, fn) => {
    $(grup).addEventListener("click", (e) => {
      const b = e.target.closest(`button[${atribut}]`);
      if (!b) return;
      $(grup).querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      fn(b.getAttribute(atribut));
    });
  };

  kepala();
  lineage();
  rekomUmum();
  jejak();
  atur("dsb-horizon", "data-h", (h) => { S.h = Number(h); gambarTabel(); const v = varianTerpilih(); gambarTren(v); ringkasVarian(v); });
  atur("dsb-rentang", "data-hari", (h) => { S.hari = Number(h); gambarTren(varianTerpilih()); });
  atur("dsb-periode", "data-p", (p) => { S.periode = p; periodik(varianTerpilih()); });
  $("dsb-varian").addEventListener("change", (e) => pilih(e.target.value));
  for (const id of ["dsb-kelompok", "dsb-status-filter"]) $(id).addEventListener("change", gambarTabel);
  $("dsb-ekspor").addEventListener("click", ekspor);
  $("dsb-tabel").querySelector("thead").addEventListener("click", (e) => {
    const th = e.target.closest("th[data-urut]");
    if (!th) return;
    S.urut = { kunci: th.dataset.urut, arah: S.urut.kunci === th.dataset.urut ? -S.urut.arah : 1 };
    gambarTabel();
  });
  const bukaBaris = (e) => {
    const tr = e.target.closest("tr[data-kode]");
    if (tr && (e.type === "click" || e.key === "Enter" || e.key === " ")) { e.preventDefault(); pilih(tr.dataset.kode, true); }
  };
  $("dsb-tabel").querySelector("tbody").addEventListener("click", bukaBaris);
  $("dsb-tabel").querySelector("tbody").addEventListener("keydown", bukaBaris);
  $("dsb-rekom-varian").addEventListener("click", (e) => { const b = e.target.closest("[data-kode]"); if (b) pilih(b.dataset.kode, true); });
  saatTemaBerubah(() => { if (S.kode) pilih(S.kode); });

  const awal = new URLSearchParams(location.search).get("varian");
  await pilih(A.varian.find((v) => v.kode === awal)?.kode || A.varian.find((v) => v.kode === "BRS03")?.kode || A.varian[0]?.kode);
}

// Beranda khusus tiap peran. Dashboard TPID (Gambar 12) tetap berada di index.html.
import { muatJSON, esc, rp, persen, angka, tgl, waktu } from "./app.js";
import { ikon, hitungMutu, ringkasSinyalPrioritas, nilaiUptime, bulanTahun, gambarKomoditas, selisihHarga, teksSelisih } from "./dashboard.js";
import { PERAN, sesi } from "./akses.js";
import { pasangKlikRincian, rincianArahHarga } from "./rincian.js";

const jepit = (x) => Math.max(0, Math.min(100, x));

export function ind({ i = "database", warna = "biru", label, nilai, kecil = "", sub = "", meter = null, meterWarna = "", href = "", warnaNilai = "", rincian = "" }) {
  // rincian: kotak berupa tombol yang membuka jendela rincian (lihat rincian.js).
  const tag = rincian ? "button" : href ? "a" : "div";
  const atribut = rincian ? ` type="button" data-rincian="${esc(rincian)}" aria-haspopup="dialog"` : href ? ` href="${esc(href)}"` : "";
  return `<${tag} class="ind${rincian ? " ind-klik" : ""}"${atribut}>${rincian ? `<span class="kpi-buka" aria-hidden="true">${ikon("kanan", 16)}</span>` : ""}
    <div class="ind-atas"><span class="ind-ikon ${warna}">${ikon(i, 20)}</span><span class="ind-label">${label}</span></div>
    <div class="ind-nilai ${warnaNilai}">${nilai}${kecil ? `<small>${kecil}</small>` : ""}</div>
    ${sub ? `<div class="ind-sub">${sub}</div>` : ""}
    ${meter === null ? "" : `<div class="ind-meter ${meterWarna}"><span style="width:${jepit(meter)}%"></span></div>`}</${tag}>`;
}

function sparkline(nilai, arah = "") {
  const v = nilai.filter((x) => x !== null && x !== undefined);
  if (v.length < 2) return "";
  const min = Math.min(...v), maks = Math.max(...v), r = maks - min || 1;
  const titik = v.map((x, k) => `${(k / (v.length - 1) * 100).toFixed(1)},${(28 - ((x - min) / r) * 24).toFixed(1)}`);
  return `<svg class="spark ${arah}" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
    <polygon class="isi" points="0,30 ${titik.join(" ")} 100,30"/><polyline points="${titik.join(" ")}"/></svg>`;
}

function salam(peran, judul, sub, aksi = "") {
  const s = sesi();
  return `<div class="salam"><div><span class="chip-peran">${ikon(PERAN[peran].ikon, 16)}${esc(PERAN[peran].nama)}</span>
    <h1>${esc(judul)}</h1><p>${s ? `Halo, ${esc(s.nama)} · ` : ""}${sub}</p></div><div class="aksi-cepat">${aksi}</div></div>`;
}
const tombol = (href, teks, utama = false, ekstra = "") =>
  `<a class="tombol${utama ? " utama-aksi" : ""}" href="${esc(href)}"${ekstra}>${teks}</a>`;

const arah = (x) => (x === null || x === undefined ? "datar" : x > 0.5 ? "naik" : x < -0.5 ? "turun" : "datar");
const tanda = { naik: "▲", turun: "▼", datar: "▬" };
const kosongkan = (el, html) => { el.innerHTML = html; };

/* ---------- masyarakat */
async function berandaMasyarakat(el, meta) {
  const [ringkasan, master] = await Promise.all([muatJSON("ringkasan.json"), muatJSON("master.json")]);
  const v = ringkasan.varian, k = ringkasan.kpi, h = ringkasan.hari_raya;
  const mingguan = (x) => x.perubahan?.mingguan;
  const naik = v.filter((x) => arah(mingguan(x)) === "naik"), turun = v.filter((x) => arah(mingguan(x)) === "turun");
  const stabil = v.length - naik.length - turun.length;
  const waspada = v.filter((x) => x.sinyal).length;
  const wakil = master.komoditas.map((km) => v.find((x) => km.varian.includes(x.kode))).filter(Boolean);
  const seri = await Promise.all(wakil.map((x) => muatJSON(`seri/${x.kode}.json`).catch(() => null)));
  const urut = (fn) => [...v].filter((x) => x.perubahan?.bulanan !== null && x.perubahan?.bulanan !== undefined).sort(fn).slice(0, 5);
  const teratas = urut((a, b) => b.perubahan.bulanan - a.perubahan.bulanan).filter((x) => x.perubahan.bulanan > 0);
  const terbawah = urut((a, b) => a.perubahan.bulanan - b.perubahan.bulanan).filter((x) => x.perubahan.bulanan < 0);
  const maksNaik = Math.max(1, ...teratas.map((x) => x.perubahan.bulanan)), maksTurun = Math.max(1, ...terbawah.map((x) => -x.perubahan.bulanan));
  const baris = (x, maks, kelas) => {
    const s = selisihHarga(x);
    return `<div class="baris-info"><div><div class="nama">${esc(x.nama)}</div>
      <div class="sub">${rp(x.harga_terakhir)}/${esc(x.satuan)}${s ? `, sebulan lalu ${rp(s.lalu)}` : ""}</div></div>
    <div class="batang-mini"><span style="width:${Math.abs(x.perubahan.bulanan) / maks * 100}%;background:var(--${kelas})"></span></div>
    <div class="kanan"><b>${s ? teksSelisih(s.selisih) : ""}</b><div class="sub">${persen(x.perubahan.bulanan, 1, true)}</div></div></div>`;
  };
  const lay = meta?.layanan || {};
  const aksi = tombol("harga.html", "Semua harga", true) + tombol("laporan.html", "Buletin mingguan") +
    (lay.url_pengaduan_eksternal || lay.url_pengaduan ? tombol(lay.url_pengaduan_eksternal || lay.url_pengaduan, "Lapor data") : "");
  kosongkan(el, `${salam("masyarakat", PERAN.masyarakat.judulBeranda, `Data ${tgl(meta.tanggal_data_terakhir, true)}`, aksi)}
    <p class="petunjuk-klik">Klik kotak di bawah untuk melihat barang apa saja yang naik, turun, stabil, atau perlu diwaspadai.</p>
    <div class="ind-baris" id="kotak-arah">
      ${ind({ i: "tren", warna: "merah", label: "Harga naik", nilai: naik.length, kecil: "varian", sub: "dibanding minggu lalu", meter: naik.length / v.length * 100, meterWarna: "merah", warnaNilai: "merah", rincian: "naik" })}
      ${ind({ i: "trenTurun", warna: "hijau", label: "Harga turun", nilai: turun.length, kecil: "varian", sub: "dibanding minggu lalu", meter: turun.length / v.length * 100, meterWarna: "hijau", warnaNilai: "hijau", rincian: "turun" })}
      ${ind({ i: "kubus", label: "Harga stabil", nilai: stabil, kecil: "varian", sub: "naik atau turun sedikit sekali", meter: stabil / v.length * 100, rincian: "stabil" })}
      ${ind({ i: "peringatan", warna: "oranye", label: "Perlu diwaspadai", nilai: waspada, kecil: "varian", sub: "harga jauh dari biasanya", meter: waspada / v.length * 100, meterWarna: "oranye", rincian: "waspada" })}
      ${ind({ i: "kalender", label: h.berikutnya ? esc(h.berikutnya.nama) : "Hari raya", nilai: h.berikutnya ? `H-${h.berikutnya.hari_menuju}` : "–", sub: h.berikutnya ? tgl(h.berikutnya.tanggal, true) : "belum terjadwal" })}
    </div>
    <section class="kartu"><div class="kartu-kepala"><div><h2>Harga bahan pokok</h2><p>Perubahan dibanding minggu lalu</p></div></div>
      <div class="grid-komoditas">${wakil.map((x, n) => {
        const a = arah(mingguan(x)), s = seri[n], beda = selisihHarga(x, "mingguan");
        return `<a class="komo" href="harga.html" style="text-decoration:none;color:inherit"><span class="komo-atas">${gambarKomoditas(x.kode)}<span class="komo-nama">${esc(x.nama)}</span></span>
          <span class="komo-harga">${rp(x.harga_terakhir)}<small>/${esc(x.satuan)}</small></span>
          <span class="komo-ubah ${a}"><span>${tanda[a]} ${a === "datar" ? "Hampir tetap" : beda ? teksSelisih(beda.selisih) : ""}</span><small>${persen(mingguan(x), 1, true)}</small></span>
          ${beda ? `<span class="komo-lalu">Minggu lalu ${rp(beda.lalu)}</span>` : ""}
          ${s ? sparkline(s.aktual.filter((y) => y !== null).slice(-30), a) : ""}</a>`;
      }).join("")}</div></section>
    <div class="grid dua-sama" style="margin-top:14px">
      <section class="kartu"><div class="kartu-kepala"><div><h2>Naik paling tinggi</h2><p>Dalam sebulan terakhir</p></div></div>${teratas.map((x) => baris(x, maksNaik, "d-merah")).join("") || '<p class="kosong">Tidak ada kenaikan berarti.</p>'}</section>
      <section class="kartu"><div class="kartu-kepala"><div><h2>Turun paling banyak</h2><p>Dalam sebulan terakhir</p></div></div>${terbawah.map((x) => baris(x, maksTurun, "d-hijau")).join("") || '<p class="kosong">Tidak ada penurunan berarti.</p>'}</section>
    </div>`);
  pasangKlikRincian(el.querySelector("#kotak-arah"), rincianArahHarga({ varian: v, periode: "mingguan", arah: (x) => arah(mingguan(x)), peran: "masyarakat" }));
}

/* ---------- petugas lapangan */
function sisaBatas(jam) {
  const [j, m] = String(jam ?? 14).split(/[:.]/).map(Number);
  const wib = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Jakarta" }));
  const batas = new Date(wib); batas.setHours(j, m || 0, 0, 0);
  const ms = batas - wib;
  if (ms <= 0) return { lewat: true };
  return { jam: Math.floor(ms / 3.6e6), menit: Math.floor((ms % 3.6e6) / 6e4) };
}

async function berandaPetugas(el, meta) {
  const [ringkasan, pasar, kualitas] = await Promise.all([muatJSON("ringkasan.json"), muatJSON("pasar.json"), muatJSON("kualitas.json")]);
  const k = ringkasan.kpi;
  let antrean = [];
  try { antrean = JSON.parse(localStorage.getItem("antrean_harga_v1")) || []; } catch { /* abaikan */ }
  const belum = antrean.filter((x) => !x._dikirim).length;
  const batas = sisaBatas(kualitas.pengaturan?.jam_batas_tepat_waktu);
  const target = pasar.pasar.filter((p) => p.peran === "target");
  const jamBatas = String(kualitas.pengaturan?.jam_batas_tepat_waktu ?? 14).split(/[:.]/)[0].padStart(2, "0") + ".00";
  kosongkan(el, `${salam("petugas", PERAN.petugas.judulBeranda, `Data ${tgl(meta.tanggal_data_terakhir, true)}`,
    tombol("input.html", `${ikon("toko", 16)} Catat harga sekarang`, true))}
    <div class="ind-baris">
      ${ind({ i: "ponsel", warna: belum ? "oranye" : "hijau", label: "Belum terkirim", nilai: belum, kecil: "harga", sub: belum ? "tersimpan di perangkat ini" : "semua sudah dikirim", warnaNilai: belum ? "oranye" : "hijau", href: "input.html" })}
      ${ind({ i: "jam", warna: batas.lewat ? "merah" : "biru", label: "Batas kirim", nilai: jamBatas, kecil: "WIB", sub: batas.lewat ? "hari ini sudah lewat" : `sisa ${batas.jam} jam ${batas.menit} menit` })}
      ${ind({ i: "centang", warna: "hijau", label: "Kelengkapan data", nilai: persen(k.kelengkapan_persen, 0), sub: "30 hari terakhir", meter: k.kelengkapan_persen, meterWarna: "hijau" })}
      ${ind({ i: "jam", label: "Tepat waktu", nilai: k.ketepatan_persen === null ? "–" : persen(k.ketepatan_persen, 0), sub: `target ${k.target_ketepatan_persen}%`, meter: k.ketepatan_persen ?? 0 })}
      ${ind({ i: "kubus", label: "Varian dicatat", nilai: k.jumlah_varian, sub: `${k.jumlah_komoditas} komoditas` })}
    </div>
    <div class="grid dua-kolom">
      <section class="kartu"><div class="kartu-kepala"><div><h2>Pasar saya</h2><p>Kiriman 30 hari terakhir</p></div></div>
        ${target.map((p) => { const t = p.ketepatan || {}; return `<div class="baris-info"><div><div class="nama">${esc(p.nama)}</div>
          <div class="sub">${esc(p.kecamatan || "")} · terakhir kirim ${t.tanggal_terakhir ? tgl(t.tanggal_terakhir) : "–"}${p.blank_spot ? " · blank spot" : ""}</div></div>
          <div class="batang-mini" title="Kelengkapan"><span style="width:${jepit(t.kelengkapan_persen ?? 0)}%;background:var(--d-hijau)"></span></div>
          <div class="kanan"><b>${t.kelengkapan_persen === null || t.kelengkapan_persen === undefined ? "–" : persen(t.kelengkapan_persen, 0)}</b><div class="sub">lengkap</div></div></div>`; }).join("") || '<p class="kosong">Belum ada pasar.</p>'}
      </section>
      <section class="kartu"><div class="kartu-kepala"><div><h2>Harga terakhir</h2><p>Acuan saat mencatat</p></div></div>
        <div style="max-height:300px;overflow:auto">${ringkasan.varian.map((x) => `<div class="baris-info"><div class="nama" style="font-weight:500">${esc(x.nama)}</div>
          <div class="kanan"><b>${rp(x.harga_terakhir)}</b><span class="sub">/${esc(x.satuan)}</span></div></div>`).join("")}</div>
      </section>
    </div>`);
}

/* ---------- operator data */
async function berandaOperator(el, meta) {
  const [kualitas, ringkasan] = await Promise.all([muatJSON("kualitas.json"), muatJSON("ringkasan.json")]);
  const r = kualitas.ringkasan, k = ringkasan.kpi;
  const lolos = r.per_status?.lolos ?? 0;
  const berkas = [...kualitas.batch].filter((b) => b.jenis === "harga" || !b.jenis).slice(-8).reverse();
  const unggah = meta.url_repo ? `${meta.url_repo}/upload/main/data/masuk/harga` : "";
  kosongkan(el, `${salam("operator", PERAN.operator.judulBeranda, `Data ${tgl(meta.tanggal_data_terakhir, true)}`,
    (unggah ? tombol(unggah, "Unggah berkas", true, ' target="_blank" rel="noopener"') : "") + tombol("kualitas.html", "Cek data", !unggah))}
    <div class="ind-baris">
      ${ind({ i: "dokumen", label: "Berkas diperiksa", nilai: angka(r.berkas), sub: "sejak awal" })}
      ${ind({ i: "centang", warna: "hijau", label: "Baris lolos", nilai: angka(lolos), sub: "dipakai untuk analisis", warnaNilai: "hijau" })}
      ${ind({ i: "peringatan", warna: "merah", label: "Menunggu keputusan", nilai: angka(kualitas.jumlah_perlu_validasi), sub: "menunggu keputusan", warnaNilai: kualitas.jumlah_perlu_validasi ? "merah" : "", href: "kualitas.html" })}
      ${ind({ i: "kurang", warna: "oranye", label: "Baris ditolak", nilai: angka(r.baris_ditolak_skema), sub: "salah isi atau format", warnaNilai: r.baris_ditolak_skema ? "oranye" : "" })}
      ${ind({ i: "database", label: "Data ganda dibuang", nilai: angka(r.duplikat_dibuang), sub: "sudah disaring" })}
      ${ind({ i: "jam", label: "Kelengkapan", nilai: persen(k.kelengkapan_persen, 0), sub: "30 hari terakhir", meter: k.kelengkapan_persen, meterWarna: "hijau" })}
    </div>
    <div class="grid dua-kolom">
      <section class="kartu"><div class="kartu-kepala"><div><h2>Berkas terbaru</h2></div><a class="dash-tautan" href="kualitas.html">Semua</a></div>
        ${berkas.map((b) => { const gagal = !!b.galat_berkas; const tolak = b.ditolak > 0;
          return `<div class="baris-info"><span class="titik-status ${gagal ? "merah" : tolak ? "oranye" : "hijau"}"></span>
            <div><div class="nama" style="font-weight:500;word-break:break-all">${esc(String(b.berkas).split("/").pop())}</div><div class="sub">${angka(b.diterima)} baris masuk${tolak ? `, ${angka(b.ditolak)} ditolak` : ""}${gagal ? `, ${esc(b.galat_berkas)}` : ""}</div></div></div>`; }).join("") || '<p class="kosong">Belum ada berkas.</p>'}
      </section>
      <section class="kartu"><div class="kartu-kepala"><div><h2>Per pasar</h2><p>Kelengkapan dan ketepatan waktu</p></div></div>
        ${(kualitas.ketepatan.per_pasar || []).map((p) => `<div class="baris-info"><div><div class="nama">${esc(p.nama_pasar)}</div>
          <div class="sub">Tepat waktu ${p.ketepatan_persen === null ? "–" : persen(p.ketepatan_persen, 0)}</div></div>
          <div class="batang-mini"><span style="width:${jepit(p.kelengkapan_persen ?? 0)}%;background:var(--d-hijau)"></span></div>
          <div class="kanan"><b>${persen(p.kelengkapan_persen, 0)}</b></div></div>`).join("")}
      </section>
    </div>`);
}

/* ---------- analis */
async function berandaAnalis(el, meta) {
  const [ringkasan, sinyal, kualitas, model] = await Promise.all([muatJSON("ringkasan.json"), muatJSON("sinyal.json"), muatJSON("kualitas.json"), muatJSON("model.json")]);
  const k = ringkasan.kpi, mutu = hitungMutu(model, sinyal.sinyal), namaV = Object.fromEntries(ringkasan.varian.map((x) => [x.kode, x.nama]));
  const aktif = sinyal.sinyal.filter((s) => s.aktif).slice(0, 5);
  const antrean = kualitas.perlu_validasi.slice(0, 6);
  const jenis = Object.entries(sinyal.ringkasan.per_jenis || {});
  const maksJenis = Math.max(1, ...jenis.map(([, n]) => n));
  const f1 = mutu[2], rc = mutu[3];
  const warnaK = { tinggi: "merah", sedang: "oranye", rendah: "abu" };
  kosongkan(el, `${salam("analis", PERAN.analis.judulBeranda, `Data ${tgl(meta.tanggal_data_terakhir, true)}`,
    tombol("kualitas.html", "Buka antrean", true) + tombol("#beranda-tpid", "Ke dashboard TPID"))}
    <div class="ind-baris">
      ${ind({ i: "peringatan", warna: "merah", label: "Menunggu keputusan", nilai: angka(kualitas.jumlah_perlu_validasi), sub: "data ditahan", warnaNilai: kualitas.jumlah_perlu_validasi ? "merah" : "", href: "kualitas.html" })}
      ${ind({ i: "lonceng", warna: "oranye", label: "Peringatan aktif", nilai: angka(k.sinyal_aktif), sub: `${k.sinyal_tinggi} prioritas tinggi`, href: "sinyal.html" })}
      ${ind({ i: f1.ikon, warna: f1.status[1] === "baik" ? "hijau" : "oranye", label: f1.arti, nilai: f1.nilai, sub: f1.status[0], warnaNilai: "" })}
      ${ind({ i: rc.ikon, warna: rc.status[1] === "baik" ? "hijau" : "oranye", label: rc.arti, nilai: rc.nilai, sub: rc.status[0] })}
      ${ind({ i: "denyut", warna: mutu[5].status[1] === "baik" ? "hijau" : "oranye", label: mutu[5].arti, nilai: mutu[5].nilai, sub: mutu[5].status[0] })}
      ${ind({ i: "tren", label: "Prakiraan unggul", nilai: `${model.ringkasan.lolos_smape}/${model.ringkasan.varian_dinilai}`, sub: "lebih tepat dari cara sederhana", meter: model.ringkasan.lolos_smape / model.ringkasan.varian_dinilai * 100, href: "model.html" })}
    </div>
    <div class="grid tiga-kolom">
      <section class="kartu"><div class="kartu-kepala"><div><h2>Peringatan aktif</h2></div><a class="dash-tautan" href="sinyal.html">Semua</a></div>
        ${aktif.map((s) => `<div class="baris-info"><span class="titik-status ${warnaK[s.keparahan] === "abu" ? "abu" : warnaK[s.keparahan]}"></span>
          <div><div class="nama" style="font-weight:500">${esc(s.varian || s.judul)}</div><div class="sub">${esc(s.judul.length > 60 ? s.judul.slice(0, 58) + "…" : s.judul)}</div></div></div>`).join("") || '<p class="kosong">Tidak ada peringatan aktif.</p>'}
      </section>
      <section class="kartu"><div class="kartu-kepala"><div><h2>Menunggu keputusan</h2></div><a class="dash-tautan" href="kualitas.html">Buka</a></div>
        ${antrean.map((o) => `<div class="baris-info"><div><div class="nama" style="font-weight:500">${esc(namaV[o.kode_varian] || o.kode_varian)}</div>
          <div class="sub">${tgl(o.tanggal)} · ${esc(o.kode_pasar)}</div></div><div class="kanan"><b>${rp(o.harga)}</b></div></div>`).join("") || '<p class="kosong">Antrean kosong.</p>'}
      </section>
      <section class="kartu"><div class="kartu-kepala"><div><h2>Jenis peringatan</h2></div></div>
        ${jenis.map(([n, jml]) => `<div class="baris-info"><div class="nama" style="font-weight:500;min-width:110px">${esc(({ anomali_harga: "Harga janggal", proyeksi_naik: "Diperkirakan naik", risiko_hari_raya: "Hari raya", data_terlambat: "Data terlambat", drift: "Pola berubah" })[n] || n)}</div>
          <div class="batang-mini"><span style="width:${jml / maksJenis * 100}%"></span></div><div class="kanan"><b>${jml}</b></div></div>`).join("")}
      </section>
    </div>`);
}

/* ---------- administrator */
async function berandaAdmin(el, meta) {
  const [ringkasan, kualitas, sinyal, kinerja, master, sumber] = await Promise.all([muatJSON("ringkasan.json"), muatJSON("kualitas.json"), muatJSON("sinyal.json"), muatJSON("kinerja.json").catch(() => null),
    muatJSON("master.json"), muatJSON("sumber.json").catch(() => null)]);
  let jumlahAkun = "–";
  if (meta.login === "contoh") { try { jumlahAkun = (await (await fetch("data/pengguna.json")).json()).akun.length; } catch { /* abaikan */ } }
  const umur = (Date.now() - new Date(meta.dibuat).getTime()) / 3.6e6;
  const uptime = nilaiUptime(kinerja);
  const notifAktif = meta.pesan_notifikasi && !/tidak dikirim|belum|dilewati/i.test(meta.pesan_notifikasi);
  const jamLalu = umur < 1 ? "baru saja" : umur < 48 ? `${Math.round(umur)} jam lalu` : `${Math.round(umur / 24)} hari lalu`;
  const cek = [
    [umur < 36, "Data terbaru", `Diperbarui ${jamLalu}`],
    [kualitas.jumlah_perlu_validasi === 0, "Antrean validasi", `${angka(kualitas.jumlah_perlu_validasi)} menunggu`],
    [uptime !== null && uptime >= 99.5, "Dashboard bisa dibuka", uptime === null ? "belum ada log" : persen(uptime, 1)],
    [notifAktif, "Notifikasi", notifAktif ? "aktif" : "belum aktif"],
    [meta.login === "firebase", "Login aman", meta.login === "firebase" ? "Firebase" : meta.login === "contoh" ? "akun contoh" : "belum ada"],
    [!meta.mode_demo, "Data asli", meta.mode_demo ? "masih data contoh" : "sudah dipakai"],
  ];
  const repo = meta.url_repo;
  const repoBerkas = (nama) => (repo ? `${repo}/blob/main/config/${nama}` : "");
  const aksi = tombol("pengaturan.html", "Pengaturan", true) + tombol("pengguna.html", "Pengguna dan peran") + tombol("#beranda-tpid", "Ke dashboard TPID") +
    (meta.url_run ? tombol(meta.url_run, "Log proses", false, ' target="_blank" rel="noopener"') : "");
  const ubinStatis = `        ${ind({ i: "keranjang", label: "Komoditas", nilai: master.komoditas.length, sub: `${master.varian.filter((v) => v.aktif !== false).length} varian aktif`, href: repoBerkas("komoditas.csv") })}
        ${ind({ i: "toko", label: "Pasar", nilai: master.pasar.length, sub: `${master.pasar.filter((x) => x.blank_spot).length} blank spot`, href: repoBerkas("pasar.csv") })}
        ${ind({ i: "peta", label: "Wilayah", nilai: master.wilayah.length, sub: "target dan pembanding", href: repoBerkas("wilayah.csv") })}
        ${ind({ i: "database", label: "Sumber data", nilai: sumber ? sumber.sumber.length : "–", sub: sumber ? `${sumber.sumber.filter((x) => x.status === "aktif").length} aktif` : "belum ada", href: repoBerkas("sumber.csv") })}
        ${ind({ i: "kalender", label: "Hari raya", nilai: master.kalender.length, sub: "tanggal terjadwal", href: repoBerkas("kalender.csv") })}
        ${ind({ i: "orang", label: "Akun", nilai: jumlahAkun, sub: meta.login === "firebase" ? "diatur di Firebase" : "akun contoh", href: "pengguna.html" })}`;
  const ubinDinamis = `        ${ind({ i: "kalender", label: "Harga terakhir", nilai: tgl(meta.tanggal_data_terakhir), sub: jamLalu })}
        ${ind({ i: "database", label: "Data dipakai", nilai: angka(meta.jumlah.observasi_dipakai), sub: `dari ${angka(meta.jumlah.observasi_total)} masuk`, meter: meta.jumlah.observasi_dipakai / Math.max(1, meta.jumlah.observasi_total) * 100 })}
        ${ind({ i: "dokumen", label: "Berkas masuk", nilai: angka(meta.jumlah.berkas), sub: "sejak awal" })}
        ${ind({ i: "lonceng", warna: "oranye", label: "Peringatan aktif", nilai: angka(ringkasan.kpi.sinyal_aktif), sub: `${ringkasan.kpi.sinyal_tinggi} prioritas tinggi`, href: "sinyal.html" })}
        ${ind({ i: "peringatan", warna: "merah", label: "Menunggu keputusan", nilai: angka(kualitas.jumlah_perlu_validasi), sub: "menunggu keputusan", href: "kualitas.html" })}
        ${ind({ i: "centang", warna: "hijau", label: "Kelengkapan", nilai: persen(ringkasan.kpi.kelengkapan_persen, 0), sub: "30 hari terakhir", meter: ringkasan.kpi.kelengkapan_persen, meterWarna: "hijau" })}`;
  kosongkan(el, `${salam("admin", PERAN.admin.judulBeranda, `Data ${tgl(meta.tanggal_data_terakhir, true)}`, aksi)}
    <div class="ind-baris">
      ${ind({ i: "sinkron", warna: umur < 36 ? "hijau" : "merah", label: "Pembaruan terakhir", nilai: waktu(meta.dibuat).replace(":", ".").split(" ").pop(), kecil: "WIB", sub: `${tgl(meta.dibuat)} · ${jamLalu}`, warnaNilai: umur < 36 ? "" : "merah" })}
      ${ind({ i: "roda", label: "Versi sistem", nilai: `v${esc(meta.versi)}`, sub: meta.commit ? `commit ${esc(meta.commit.slice(0, 7))}` : "lokal" })}
      ${ind({ i: "jam", warna: "hijau", label: "Dashboard bisa dibuka", nilai: uptime === null ? "–" : persen(uptime, 1), sub: uptime === null ? "belum ada log" : "target 99,5%", meter: uptime === null ? null : uptime, meterWarna: "hijau", href: "kinerja.html" })}
      ${ind({ i: "database", label: "Berkas masuk", nilai: angka(meta.jumlah.berkas), sub: `${angka(meta.jumlah.observasi_dipakai)} data dipakai` })}
    </div>
    <section class="kartu" id="panel-data"></section>
    <div class="grid dua-kolom">
      <section class="kartu"><div class="kartu-kepala"><div><h2>Pemeriksaan sistem</h2></div></div>
        ${cek.map(([baik, nama, ket]) => `<div class="baris-info"><span class="titik-status ${baik ? "hijau" : "oranye"}"></span><div class="nama" style="font-weight:500">${nama}</div><div class="kanan sub">${ket}</div></div>`).join("")}
      </section>
      <section class="kartu"><div class="kartu-kepala"><div><h2>Akses cepat</h2></div></div>
        <div class="aksi-cepat" style="flex-direction:column;align-items:stretch">
          ${tombol("pengguna.html", "Kelola pengguna dan peran")}
          ${tombol("pengaturan.html", "Pengaturan AI, kunci, dan fungsi")}
          ${repo ? tombol(`${repo}/actions`, "Lihat proses otomatis", false, ' target="_blank" rel="noopener"') : ""}
          ${tombol("alur.html", "Alur dan arsitektur")}
          ${tombol("sumber.html", "Sumber data")}
        </div>
      </section>
    </div>`);
  pasangPanelData(el.querySelector("#panel-data"), { ubinStatis, ubinDinamis, master, sumber, ringkasan, sinyal, kualitas });
}


/* ---------- panel data statis dan dinamis (admin) */
function tabel(kolom, baris, kosongTeks = "Belum ada data.") {
  if (!baris.length) return `<p class="kosong">${kosongTeks}</p>`;
  return `<div class="gulir-tabel" style="max-height:380px"><table><thead><tr>${kolom.map(([h, , angka]) => `<th${angka ? ' class="angka"' : ""}>${h}</th>`).join("")}</tr></thead>
    <tbody>${baris.map((b) => `<tr>${kolom.map(([, f, angka]) => `<td${angka ? ' class="angka"' : ""}>${f(b)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

function pasangPanelData(el, { ubinStatis, ubinDinamis, master, sumber, ringkasan, sinyal, kualitas }) {
  const namaVarian = Object.fromEntries(master.varian.map((v) => [v.kode, v.nama]));
  const pctSel = (x) => (x === null || x === undefined ? "–" : `<span class="${x > 0.5 ? "naik" : x < -0.5 ? "turun" : ""}">${persen(x, 1, true)}</span>`);
  const SET = {
    statis: {
      ubin: ubinStatis, judul: "Data statis", ket: "Acuan yang jarang berubah. Diatur lewat berkas di config/.",
      tabel: {
        komoditas: ["Komoditas", () => tabel([["Kode", (x) => `<code>${esc(x.kode)}</code>`], ["Komoditas", (x) => esc(x.nama)], ["Jumlah varian", (x) => x.varian.length, true]], master.komoditas)],
        varian: ["Varian", () => tabel([["Kode", (x) => `<code>${esc(x.kode)}</code>`], ["Varian", (x) => esc(x.nama)], ["Satuan", (x) => esc(x.satuan)], ["Kelompok", (x) => esc(x.kelompok)],
          ["Batas wajar", (x) => `${rp(x.batas_bawah)} sampai ${rp(x.batas_atas)}`, true], ["Aktif", (x) => (x.aktif ? "Ya" : "Tidak")]], master.varian)],
        pasar: ["Pasar", () => tabel([["Kode", (x) => `<code>${esc(x.kode)}</code>`], ["Pasar", (x) => esc(x.nama)], ["Kecamatan", (x) => esc(x.kecamatan || "–")],
          ["Blank spot", (x) => (x.blank_spot ? "Ya" : "Tidak")], ["Titik peta", (x) => (x.koordinat_terverifikasi ? "Sudah dicek" : "Perkiraan")]], master.pasar)],
        wilayah: ["Wilayah", () => tabel([["Kode", (x) => `<code>${esc(x.kode)}</code>`], ["Wilayah", (x) => esc(x.nama)], ["Peran", (x) => (x.peran === "target" ? "Sasaran" : "Pembanding")]], master.wilayah)],
        sumber: ["Sumber", () => tabel([["Kode", (x) => `<code>${esc(x.kode)}</code>`], ["Sumber", (x) => esc(x.nama)], ["Status", (x) => esc(String(x.status).replace(/_/g, " "))], ["Prioritas", (x) => x.prioritas, true]], sumber?.sumber || [])],
        hariraya: ["Hari raya", () => tabel([["Tanggal", (x) => esc(tgl(x.tanggal))], ["Nama", (x) => esc(x.nama)], ["Status", (x) => esc(x.status)]], master.kalender)],
      },
    },
    dinamis: {
      ubin: ubinDinamis, judul: "Data dinamis", ket: "Berubah tiap kali data masuk dan sistem diperbarui.",
      tabel: {
        harga: ["Harga terakhir", () => tabel([["Varian", (x) => esc(x.nama)], ["Harga", (x) => `${rp(x.harga_terakhir)}/${esc(x.satuan)}`, true], ["Harian", (x) => pctSel(x.perubahan?.harian), true],
          ["Mingguan", (x) => pctSel(x.perubahan?.mingguan), true], ["Bulanan", (x) => pctSel(x.perubahan?.bulanan), true]], ringkasan.varian)],
        peringatan: ["Peringatan", () => tabel([["Peringatan", (x) => esc(x.judul)], ["Tingkat", (x) => esc(x.keparahan)], ["Status", (x) => esc(String(x.status).replace(/_/g, " "))], ["Sejak", (x) => esc(tgl(x.tanggal_mulai))]],
          sinyal.sinyal.filter((x) => x.aktif), "Tidak ada peringatan aktif.")],
        antrean: ["Antrean validasi", () => tabel([["Tanggal", (x) => esc(tgl(x.tanggal))], ["Varian", (x) => esc(namaVarian[x.kode_varian] || x.kode_varian)], ["Pasar", (x) => esc(x.kode_pasar)],
          ["Harga", (x) => rp(x.harga), true], ["Tanda", (x) => esc((x.tanda || []).join(", ").replace(/_/g, " "))]], kualitas.perlu_validasi.slice(0, 100), "Tidak ada yang menunggu.")],
        berkas: ["Berkas masuk", () => tabel([["Berkas", (x) => `<span style="word-break:break-all">${esc(String(x.berkas).split("/").pop())}</span>`], ["Jenis", (x) => esc(x.jenis)],
          ["Diterima", (x) => angka(x.diterima), true], ["Ditolak", (x) => angka(x.ditolak), true]], [...kualitas.batch].reverse().slice(0, 100))],
      },
    },
  };
  let mode = "statis", isi = { statis: "komoditas", dinamis: "harga" };
  function gambar() {
    const d = SET[mode];
    el.innerHTML = `<div class="kartu-kepala"><div><h2>${d.judul}</h2><p>${d.ket}</p></div>
      <div class="segmen" role="group" aria-label="Jenis data">${Object.entries(SET).map(([k, v]) => `<button type="button" data-mode="${k}" aria-pressed="${k === mode}">${v.judul}</button>`).join("")}</div></div>
      <div class="ind-baris">${d.ubin}</div>
      <div class="segmen" role="group" aria-label="Pilih tabel" style="margin-bottom:12px">${Object.entries(d.tabel).map(([k, v]) => `<button type="button" data-tabel="${k}" aria-pressed="${k === isi[mode]}">${v[0]}</button>`).join("")}</div>
      <div>${d.tabel[isi[mode]][1]()}</div>`;
    el.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => { mode = b.dataset.mode; gambar(); }));
    el.querySelectorAll("[data-tabel]").forEach((b) => b.addEventListener("click", () => { isi[mode] = b.dataset.tabel; gambar(); }));
  }
  gambar();
}

const PETA = { masyarakat: berandaMasyarakat, petugas: berandaPetugas, operator: berandaOperator, analis: berandaAnalis, admin: berandaAdmin };

export async function renderBerandaPeran(peran, meta, el) {
  const f = PETA[peran] || berandaMasyarakat;
  await f(el, meta);
}

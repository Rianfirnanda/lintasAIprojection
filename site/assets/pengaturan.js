// Panel pengaturan admin. Formulir dibuat dari config/skema_pengaturan.json (diterbitkan ke data/skema_pengaturan.json).
// Dua cara menyimpan, dengan tampilan yang sama:
//   - Login Google (Firebase): disimpan di Firestore dengan akun admin yang sedang masuk, tanpa token GitHub.
//     Mesin pengolah mengambilnya lalu menerapkannya (pipeline/firestore_sinkron.py). Lihat pengaturan-firestore.js.
//   - Tanpa Firebase: disimpan sebagai commit pada config/pengaturan.json dan GitHub Secrets, memakai token GitHub
//     admin yang hanya hidup di tab ini. Tidak ada server perantara.
import { pasangKerangka, muatJSON, esc, waktu } from "./app.js";
import { ind } from "./peran.js";
import { GalatGitHub, KlienGitHub, bacaRepo } from "./github.js";
import {
  ambil, atur, bedaPengaturan, dariTampilan, keTampilan, periksa, periksaRahasia, salin, sama, teksNilai, tulisPengaturan,
} from "./pengaturan-inti.js";

const meta = await pasangKerangka("pengaturan.html");
/** true bila situs memakai login Google: semua lewat Firestore, tanpa token GitHub. */
const FS = meta?.login === "firebase";
const rahasiaFirebase = (nama) => nama.startsWith("FIREBASE_");
const BERKAS = "config/pengaturan.json";
const KUNCI_SESI = "lintas-gh-sambungan";
const $ = (id) => document.getElementById(id);
const MODEL_AI = { gemini: "ai.model_gemini", groq: "ai.model_groq", cerebras: "ai.model_cerebras", openrouter: "ai.model_openrouter",
  mistral: "ai.model_mistral", github_models: "ai.model_github", anthropic: "ai.model_anthropic" };

let skema, terbit;
try {
  [skema, terbit] = await Promise.all([muatJSON("skema_pengaturan.json"), muatJSON("pengaturan.json")]);
} catch (e) {
  $("panel").insertAdjacentHTML("beforeend", `<div class="pesan galat">Data pengaturan belum tersedia di situs ini (${esc(e.message)}). Jalankan pembaruan data dulu, lalu buka halaman ini lagi.</div>`);
  throw e;
}

const S = {
  awal: salin(terbit), kini: salin(terbit), sha: null,
  klien: null, pengguna: null, cabang: "main",
  rahasia: null, rahasiaGalat: "",
  tab: skema.kelompok[0].kode,
  pantau: {}, proses: {},
};

const bacaSesi = () => { try { return JSON.parse(sessionStorage.getItem(KUNCI_SESI)); } catch { return null; } };
const tulisSesi = (v) => { try { v ? sessionStorage.setItem(KUNCI_SESI, JSON.stringify(v)) : sessionStorage.removeItem(KUNCI_SESI); } catch { /* abaikan */ } };
const adaPerubahan = () => bedaPengaturan(S.awal, S.kini, skema).length > 0;
const pesanHtml = (jenis, teks) => `<div class="pesan ${jenis}" role="${jenis === "galat" ? "alert" : "status"}">${teks}</div>`;
const tampilPesan = (el, jenis, teks) => { el.innerHTML = teks ? pesanHtml(jenis, teks) : ""; };
/** Galat dari GitHub dan galat yang sudah kita jelaskan ke pengguna tidak perlu masuk konsol. */
const lapor = (e) => { if (!(e instanceof GalatGitHub)) console.error(e); };
/** Tautan dari balasan GitHub hanya dipakai bila benar-benar mengarah ke github.com. */
const urlAman = (u) => (/^https:\/\/github\.com\//.test(String(u)) ? String(u) : "#");
const galatTeks = (e) => (e instanceof GalatGitHub ? e.message : e?.message || "Terjadi kesalahan yang tidak dikenal.");

/** Kunci yang diatur lewat panel ini. Dengan Firebase, kunci Firebase sendiri tetap di GitHub Secrets. */
const daftarKunci = () => skema.rahasia.filter((r) => !(FS && rahasiaFirebase(r.nama)));

/* ------------------------------------------------------------------ ringkasan */
function renderRingkas() {
  const nAda = S.rahasia ? daftarKunci().filter((r) => S.rahasia.has(r.nama)).length : null;
  const penyedia = ambil(S.kini, "ai.penyedia").nilai;
  const kolomAi = skema.kolom.find((k) => k.jalur === "ai.penyedia");
  const beda = bedaPengaturan(S.awal, S.kini, skema).length;
  $("ringkas").innerHTML = [
    ind({ i: "tautan", warna: S.klien ? "hijau" : "oranye", label: FS ? "Sambungan" : "Sambungan GitHub", nilai: S.klien ? "Tersambung" : "Belum",
      sub: S.klien ? (FS ? esc(S.pengguna.login) : `@${esc(S.pengguna.login)} · ${esc(S.klien.namaRepo)}`) : (FS ? "masuk sebagai admin" : "Tempel token di bawah") }),
    ind({ i: "gembokPerisai", warna: nAda ? "hijau" : "abu", label: "Kunci terisi", nilai: nAda === null ? "–" : `${nAda}/${daftarKunci().length}`,
      sub: nAda === null ? (S.rahasiaGalat ? "tidak bisa dicek" : "sambungkan dulu") : (FS ? "tersimpan aman" : "di GitHub Secrets"), meter: nAda === null ? null : nAda / daftarKunci().length * 100, meterWarna: "hijau" }),
    ind({ i: "otak", label: "AI yang dipakai", nilai: `<span style="font-size:1.05rem;line-height:1.3;display:block">${esc(teksNilai(kolomAi, penyedia).replace(/ \(.*\)$/, ""))}</span>`,
      sub: penyedia === "otomatis" ? esc(teksNilai(skema.kolom.find((k) => k.jalur === "ai.urutan_otomatis"), ambil(S.kini, "ai.urutan_otomatis").nilai))
        : esc(ambil(S.kini, MODEL_AI[penyedia] || "ai.model_gemini").nilai) }),
    ind({ i: "dokumen", warna: beda ? "oranye" : "hijau", label: "Belum disimpan", nilai: beda, kecil: "perubahan", sub: beda ? "klik Simpan di bawah" : "semua sudah tersimpan", warnaNilai: beda ? "oranye" : "" }),
  ].join("");
}

/* ------------------------------------------------------------------ sambungan */
function renderSambunganFirestore(kartu) {
  if (S.klien) {
    const tunda = S.menunggu ? `<p class="pesan peringatan" style="margin-top:10px">Ada perubahan yang disimpan ${S.menunggu.oleh ? `oleh ${esc(S.menunggu.oleh)} ` : ""}dan sedang menunggu diproses. Isian di bawah sudah memuat perubahan itu.</p>` : "";
    kartu.innerHTML = `<div class="kartu-kepala"><div><h2 id="j-sambungan">Penyimpanan</h2></div></div>
      <div class="tersambung"><p>Masuk sebagai <b>${esc(S.pengguna.login)}</b>. Perubahan, kunci, dan permintaan di halaman ini langsung tersimpan.
        Sistem menerapkannya otomatis, biasanya dalam 15 sampai 30 menit pada jam kerja. Tidak perlu membuka GitHub.</p>
        <div class="baris-kontrol"><button class="tombol" type="button" id="btn-muat">Muat ulang</button></div></div>${tunda}
      <div id="pesan-sambungan" class="pesan-bagian"></div>`;
    $("btn-muat").addEventListener("click", () => {
      if (adaPerubahan() && !confirm("Perubahan yang belum disimpan akan hilang. Lanjutkan?")) return;
      sambungFirestore({ muatUlang: true });
    });
    return;
  }
  kartu.innerHTML = `<div class="kartu-kepala"><div><h2 id="j-sambungan">Penyimpanan</h2>
      <p>Menghubungkan dengan akun Anda…</p></div></div><div id="pesan-sambungan" class="pesan-bagian"></div>`;
}

async function sambungFirestore({ muatUlang = false } = {}) {
  try {
    const { KlienFirestore } = await import("./pengaturan-firestore.js");
    const klien = await KlienFirestore.sambung({ terbit, versiTerbit: meta?.pengaturan_versi || 0 });
    const [pengguna, berkas] = await Promise.all([klien.pengguna(), klien.bacaBerkas()]);
    const data = JSON.parse(berkas.teks);
    Object.values(S.pantau).forEach((h) => h());
    Object.assign(S, { klien, pengguna, awal: data, kini: salin(data), sha: berkas.sha, pantau: {},
      menunggu: berkas.menunggu ? { oleh: berkas.diubahOleh } : null });
    await Promise.all([muatRahasia(), ...skema.alur_kerja.map((a) => muatProses(a.berkas))]);
    renderSemua();
    for (const a of skema.alur_kerja) {
      S.pantau[a.berkas] = klien.pantauProses(a.berkas, (p) => { S.proses = { ...S.proses, [a.berkas]: p }; tampilProses(a.berkas); });
    }
    if (muatUlang) tampilPesan($("pesan-sambungan"), "sukses", "Pengaturan dimuat ulang.");
  } catch (e) {
    lapor(e);
    S.klien = null;
    renderSemua();
    tampilPesan($("pesan-sambungan"), "galat", `${esc(galatTeks(e))} <button class="tombol kecil" type="button" id="btn-ulang">Coba lagi</button>`);
    $("btn-ulang")?.addEventListener("click", () => sambungFirestore());
  }
}

function renderSambungan() {
  const kartu = $("kartu-sambungan");
  if (FS) return renderSambunganFirestore(kartu);
  if (S.klien) {
    kartu.innerHTML = `<div class="kartu-kepala"><div><h2 id="j-sambungan">Sambungan GitHub</h2></div></div>
      <div class="tersambung"><p>Tersambung sebagai <b>@${esc(S.pengguna.login)}</b> ke <a href="${esc(S.klien.alamatRepo)}" rel="noopener">${esc(S.klien.namaRepo)}</a> (cabang ${esc(S.cabang)}).</p>
        <div class="baris-kontrol"><button class="tombol" type="button" id="btn-muat">Muat ulang dari GitHub</button><button class="tombol" type="button" id="btn-putus">Putuskan</button></div></div>
      <div id="pesan-sambungan" class="pesan-bagian"></div>`;
    $("btn-muat").addEventListener("click", () => {
      if (adaPerubahan() && !confirm("Perubahan yang belum disimpan akan hilang. Lanjutkan?")) return;
      const sesi = bacaSesi();
      if (sesi?.token) sambungkan(sesi.token, sesi.repo, { muatUlang: true });
    });
    $("btn-putus").addEventListener("click", putuskan);
    return;
  }
  const sesi = bacaSesi();
  kartu.innerHTML = `<div class="kartu-kepala"><div><h2 id="j-sambungan">Sambungkan ke GitHub</h2>
      <p>Panel ini mengubah pengaturan lewat akun GitHub Anda. Tanpa sambungan, halaman ini hanya bisa dibaca.</p></div></div>
    <div class="grid-sambungan">
      <label>Repositori<input type="text" id="in-repo" autocomplete="off" spellcheck="false" placeholder="pemilik/nama-repositori" value="${esc(sesi?.repo || repoDariMeta())}"></label>
      <label>Token GitHub<input type="password" id="in-token" autocomplete="off" spellcheck="false" autocapitalize="off" data-lpignore="true" data-1p-ignore placeholder="github_pat_..."></label>
      <button class="tombol utama-aksi" type="button" id="btn-sambung">Sambungkan</button>
    </div>
    <div id="pesan-sambungan" class="pesan-bagian"></div>
    <p class="meta-kecil" style="margin-top:10px">Token hanya disimpan di tab ini dan hilang saat tab ditutup. Halaman ini hanya berhubungan dengan situs ini dan api.github.com.</p>
    <details style="margin-top:8px"><summary>Cara membuat token</summary>
      <ol class="langkah-token">
        <li>Buka <a href="https://github.com/settings/personal-access-tokens/new" rel="noopener" target="_blank">github.com/settings/personal-access-tokens/new</a> dan masuk.</li>
        <li>Beri nama bebas, misalnya <i>Panel Lintas Benteng</i>. Pilih masa berlaku pendek, misalnya 30 hari.</li>
        <li>Pada <i>Repository access</i>, pilih <i>Only select repositories</i>, lalu pilih repositori ini saja.</li>
        <li>Pada <i>Repository permissions</i>, atur: <b>Contents</b>: Read and write, <b>Secrets</b>: Read and write, <b>Actions</b>: Read and write. (<i>Metadata</i> otomatis Read-only.)</li>
        <li>Klik <i>Generate token</i>, salin tokennya, lalu tempel di kolom di atas.</li>
      </ol>
      <p class="meta-kecil" style="margin-top:8px">Token bisa dicabut kapan saja di halaman yang sama. Jangan kirim token ke siapa pun.</p></details>`;
  const kirim = () => sambungkan($("in-token").value, $("in-repo").value);
  $("btn-sambung").addEventListener("click", kirim);
  $("in-token").addEventListener("keydown", (e) => { if (e.key === "Enter") kirim(); });
}

function repoDariMeta() {
  const r = bacaRepo(meta?.url_repo || "");
  return r ? `${r.pemilik}/${r.repo}` : "";
}

async function sambungkan(tokenMentah, repoTeks, { diam = false, muatUlang = false } = {}) {
  const pesan = () => $("pesan-sambungan");
  const repo = bacaRepo(repoTeks);
  const token = String(tokenMentah || "").trim();
  if (!repo) return tampilPesan(pesan(), "galat", "Isi nama repositori dengan bentuk pemilik/nama, misalnya Rianfirnanda/lintasAIprojection.");
  if (!token) return tampilPesan(pesan(), "galat", "Tempel token GitHub dulu.");
  const tombol = $("btn-sambung") || $("btn-muat");
  if (tombol) { tombol.disabled = true; tombol.textContent = "Menghubungkan…"; }
  if (!diam && pesan()) tampilPesan(pesan(), "", "");
  try {
    const klien = new KlienGitHub({ token, ...repo });
    const [pengguna, info] = await Promise.all([klien.pengguna(), klien.info()]);
    const cabang = info.default_branch || "main";
    const berkas = await klien.bacaBerkas(BERKAS, cabang);
    let data;
    try { data = JSON.parse(berkas.teks); } catch { throw new GalatGitHub(`Isi ${BERKAS} di GitHub rusak dan tidak bisa dibaca sebagai JSON. Perbaiki dulu di GitHub.`, { kode: "ditolak" }); }
    Object.assign(S, { klien, pengguna, cabang, awal: data, kini: salin(data), sha: berkas.sha });
    tulisSesi({ token, repo: klien.namaRepo });
    await Promise.all([muatRahasia(), ...skema.alur_kerja.map((a) => muatProses(a.berkas))]);
    renderSemua();
    const tulis = info.permissions ? info.permissions.push || info.permissions.admin : true;
    if (!tulis) tampilPesan($("pesan-sambungan"), "peringatan", "Akun ini hanya bisa membaca repositori, jadi menyimpan perubahan kemungkinan ditolak GitHub.");
    else if (muatUlang) tampilPesan($("pesan-sambungan"), "sukses", "Pengaturan dimuat ulang dari GitHub.");
  } catch (e) {
    lapor(e);
    if (diam) { tulisSesi(null); S.klien = null; renderSemua(); return; }
    if (tombol) { tombol.disabled = false; tombol.textContent = muatUlang ? "Muat ulang dari GitHub" : "Sambungkan"; }
    tampilPesan(pesan(), "galat", esc(galatTeks(e)));
  }
}

function putuskan() {
  if (adaPerubahan() && !confirm("Perubahan yang belum disimpan akan hilang. Lanjutkan?")) return;
  tulisSesi(null);
  Object.values(S.pantau).forEach(clearInterval);
  Object.assign(S, { klien: null, pengguna: null, sha: null, rahasia: null, rahasiaGalat: "", awal: salin(terbit), kini: salin(terbit), pantau: {}, proses: {} });
  renderSemua({ bersih: true });
}

/* ------------------------------------------------------------------ kunci rahasia */
async function muatRahasia() {
  try { S.rahasia = await S.klien.daftarRahasia(); S.rahasiaGalat = ""; } catch (e) { S.rahasia = null; S.rahasiaGalat = galatTeks(e); }
}

function tglSingkat(iso) { return iso ? waktu(iso).split(" ").slice(0, 3).join(" ") : ""; }

function htmlRahasia(r) {
  if (FS && rahasiaFirebase(r.nama)) {
    // Kunci Firebase dipakai mesin untuk masuk ke Firestore, jadi tetap disimpan di GitHub Secrets (diatur sekali di awal).
    return `<div class="isian"><div class="rahasia-kepala"><span class="label-isian">${esc(r.label)}</span><span class="lencana polos">di GitHub Secrets</span></div>
      <span class="bantuan">${esc(r.bantuan)} Diatur sekali saat memasang Firebase, jadi tidak diubah dari sini (lihat docs/FIREBASE.md).</span></div>`;
  }
  const ada = S.rahasia?.get(r.nama);
  const lencana = !S.klien ? '<span class="lencana polos">sambungkan dulu</span>'
    : S.rahasiaGalat ? '<span class="lencana rendah">tidak bisa dicek</span>'
      : ada ? `<span class="lencana baik">sudah diisi · ${esc(tglSingkat(ada.diperbarui))}</span>` : '<span class="lencana polos">belum diisi</span>';
  const id = `r-${r.nama}`;
  return `<div class="isian" data-rahasia-kotak="${esc(r.nama)}">
    <div class="rahasia-kepala"><label for="${esc(id)}">${esc(r.label)}</label>${lencana}</div>
    <input id="${esc(id)}" data-rahasia="${esc(r.nama)}" type="${r.sensitif ? "password" : "text"}" autocomplete="off" spellcheck="false" autocapitalize="off"
      data-lpignore="true" data-1p-ignore placeholder="${ada ? "Sudah diisi. Isi lagi untuk mengganti." : "Belum diisi"}" ${S.klien ? "" : "disabled"}>
    <span class="bantuan">${esc(r.bantuan)}${ada && S.klien ? ` <button type="button" class="tautan-bahaya" data-hapus="${esc(r.nama)}">Hapus kunci ini</button>` : ""}</span>
    <span class="galat-isian" role="alert"></span></div>`;
}

async function simpanKunci(wadah) {
  const pesan = wadah.querySelector(".pesan-bagian");
  const isi = [...wadah.querySelectorAll("[data-rahasia]")].map((el) => ({ el, def: skema.rahasia.find((r) => r.nama === el.dataset.rahasia), nilai: el.value.trim() })).filter((x) => x.nilai);
  wadah.querySelectorAll(".galat-isian").forEach((g) => { g.textContent = ""; });
  if (!isi.length) return tampilPesan(pesan, "peringatan", "Isi dulu kunci yang mau disimpan.");
  let salah = 0;
  for (const x of isi) {
    const m = periksaRahasia(x.def, x.nilai);
    if (m) { x.el.closest(".isian").querySelector(".galat-isian").textContent = m; salah++; }
  }
  if (salah) return tampilPesan(pesan, "galat", "Ada isian yang belum benar. Belum ada yang disimpan.");
  const tombol = wadah.querySelector("[data-simpan-kunci]");
  const nama = wadah.dataset.bagian;
  tombol.disabled = true;
  const berhasil = [];
  let hasil;
  try {
    for (const x of isi) {
      await S.klien.simpanRahasia(x.def.nama, x.nilai);
      x.el.value = "";
      berhasil.push(x.def.label);
    }
    hasil = ["sukses", FS
      ? `Tersimpan: ${esc(berhasil.join(", "))}. Nilainya tidak bisa dilihat lagi dari situs, hanya bisa diganti. Mulai dipakai pada proses berikutnya.`
      : `Tersimpan di GitHub Secrets: ${esc(berhasil.join(", "))}. Nilainya tidak bisa dilihat lagi, hanya bisa diganti.`];
  } catch (e) {
    hasil = ["galat", `${berhasil.length ? `Sudah tersimpan: ${esc(berhasil.join(", "))}. ` : ""}Gagal menyimpan berikutnya: ${esc(galatTeks(e))}`];
  }
  await muatRahasia();
  // Gambar ulang supaya status "sudah diisi" muncul. Kunci yang berhasil sudah dikosongkan; yang gagal atau belum dikirim tetap terisi.
  renderPanelIsi(); renderRingkas();
  tampilPesan(document.querySelector(`[data-bagian="${CSS.escape(nama)}"] .pesan-bagian`), ...hasil);
}

async function hapusKunci(nama, wadah) {
  const def = skema.rahasia.find((r) => r.nama === nama);
  if (!confirm(`Hapus kunci "${def.label}"? Fungsi yang memakainya berhenti sampai kunci diisi lagi.`)) return;
  const bagian = wadah.dataset.bagian;
  let hasil;
  try {
    await S.klien.hapusRahasia(nama);
    hasil = ["sukses", FS ? `Kunci "${esc(def.label)}" sudah dihapus. Bila kunci yang sama ada di GitHub Secrets, kunci itu yang dipakai.`
      : `Kunci "${esc(def.label)}" sudah dihapus dari GitHub Secrets.`];
  } catch (e) {
    hasil = ["galat", esc(galatTeks(e))];
  }
  await muatRahasia();
  renderPanelIsi(); renderRingkas();
  tampilPesan(document.querySelector(`[data-bagian="${CSS.escape(bagian)}"] .pesan-bagian`), ...hasil);
}

/* ------------------------------------------------------------------ isian pengaturan */
const idKolom = (k) => `f-${k.jalur.replace(/\./g, "-")}`;

function htmlKontrol(k) {
  const nilai = ambil(S.kini, k.jalur).nilai;
  const id = idKolom(k);
  const mati = S.klien ? "" : "disabled";
  const d = `id="${id}" data-jalur="${esc(k.jalur)}" ${mati}`;
  switch (k.tipe) {
    case "bulat":
    case "desimal":
      return `<div class="kotak-angka"><input ${d} type="text" inputmode="decimal" autocomplete="off" value="${esc(keTampilan(k, nilai))}">${k.satuan ? `<span class="satuan">${esc(k.satuan)}</span>` : ""}</div>`;
    case "saklar":
      return `<label class="sakelar"><input ${d} type="checkbox" ${nilai ? "checked" : ""}><span class="geser" aria-hidden="true"></span><span class="teks-sakelar">${nilai ? "Menyala" : "Mati"}</span></label>`;
    case "pilihan":
    case "urutan": {
      const pilihan = k.pilihan.map((p, i) => `<option value="${i}" ${sama(p.nilai, nilai) ? "selected" : ""}>${esc(p.label)}</option>`);
      if (!k.pilihan.some((p) => sama(p.nilai, nilai))) pilihan.unshift(`<option value="-1" selected>Lainnya: ${esc(teksNilai(k, nilai))}</option>`);
      return `<select ${d}>${pilihan.join("")}</select>`;
    }
    case "banyak_pilihan":
      return `<div class="kelompok-centang" role="group" aria-labelledby="l-${id}">${k.pilihan.map((p, i) =>
        `<label class="chip-centang"><input type="checkbox" data-jalur="${esc(k.jalur)}" data-indeks="${i}" ${Array.isArray(nilai) && nilai.includes(p.nilai) ? "checked" : ""} ${mati}><span>${esc(p.label)}</span></label>`).join("")}</div>`;
    case "teks":
      return `<input ${d} type="text" autocomplete="off" spellcheck="false" ${k.saran ? `list="dl-${id}"` : ""} value="${esc(nilai)}">${k.saran ? `<datalist id="dl-${id}">${k.saran.map((s) => `<option value="${esc(s)}">`).join("")}</datalist>` : ""}`;
    case "url":
      return `<input ${d} type="url" inputmode="url" autocomplete="off" spellcheck="false" placeholder="https://" value="${esc(nilai)}">`;
    default:
      return "";
  }
}

function htmlKolom(k) {
  const id = idKolom(k);
  const grup = k.tipe === "banyak_pilihan" || k.tipe === "saklar";
  return `<div class="isian" data-kotak="${esc(k.jalur)}">
    ${grup ? `<span class="label-isian" id="l-${id}">${esc(k.label)}</span>` : `<label for="${id}">${esc(k.label)}</label>`}
    ${htmlKontrol(k)}
    ${k.bantuan ? `<span class="bantuan">${esc(k.bantuan)}</span>` : ""}
    <span class="galat-isian" role="alert"></span></div>`;
}

function nilaiDariElemen(k, el) {
  switch (k.tipe) {
    case "bulat":
    case "desimal": return dariTampilan(k, el.value);
    case "saklar": return el.checked;
    case "pilihan":
    case "urutan": return Number(el.value) >= 0 ? k.pilihan[Number(el.value)].nilai : ambil(S.kini, k.jalur).nilai;
    case "banyak_pilihan": {
      const terpilih = [...document.querySelectorAll(`input[data-jalur="${CSS.escape(k.jalur)}"]`)];
      return k.pilihan.filter((_, i) => terpilih[i]?.checked).map((p) => p.nilai);
    }
    default: return el.value;
  }
}

function saatIsianBerubah(e) {
  const el = e.target;
  if (!el.dataset?.jalur) return;
  const k = skema.kolom.find((x) => x.jalur === el.dataset.jalur);
  atur(S.kini, k.jalur, nilaiDariElemen(k, el));
  if (k.tipe === "saklar") el.closest(".sakelar").querySelector(".teks-sakelar").textContent = el.checked ? "Menyala" : "Mati";
  perbarui();
}

function perbarui() {
  const masalah = periksa(S.kini, skema);
  const peta = new Map();
  for (const m of masalah) if (!peta.has(m.jalur)) peta.set(m.jalur, m.pesan);
  document.querySelectorAll("[data-kotak]").forEach((kotak) => {
    const j = kotak.dataset.kotak;
    const k = skema.kolom.find((x) => x.jalur === j);
    const pesan = peta.get(j) || "";
    kotak.classList.toggle("berubah", !sama(ambil(S.awal, j).nilai, ambil(S.kini, j).nilai));
    kotak.classList.toggle("salah", !!pesan);
    kotak.querySelector(".galat-isian").textContent = pesan.startsWith(`${k.label}: `) ? pesan.slice(k.label.length + 2) : pesan;
  });
  renderBilah(masalah.length);
  renderRingkas();
}

/* ------------------------------------------------------------------ bilah simpan */
function renderBilah(jumlahMasalah = periksa(S.kini, skema).length) {
  const beda = bedaPengaturan(S.awal, S.kini, skema);
  const bilah = $("bilah-simpan");
  bilah.hidden = beda.length === 0;
  if (!beda.length) return;
  const daftar = beda.slice(0, 40).map((b) => `<li>${esc(b.kolom.label)}: ${esc(teksNilai(b.kolom, b.dari))} menjadi ${esc(teksNilai(b.kolom, b.ke))}</li>`).join("");
  const html = `<div class="ringkas-simpan"><b>${beda.length}</b> perubahan belum disimpan${jumlahMasalah ? ` · <span class="jumlah-masalah">${jumlahMasalah} isian belum benar</span>` : ""}
      <details><summary>Lihat perubahan</summary><ul>${daftar}</ul></details></div>
    <div class="aksi-simpan"><button class="tombol" type="button" id="btn-batal">Batalkan perubahan</button>
      <button class="tombol utama-aksi" type="button" id="btn-simpan" ${S.klien && !jumlahMasalah ? "" : "disabled"} title="${S.klien || FS ? "" : "Sambungkan ke GitHub dulu"}">Simpan perubahan</button></div>`;
  // Jangan gambar ulang bila isinya sama. Kalau tidak, tombol yang sedang diklik bisa terganti di tengah klik
  // (mis. saat isian kehilangan fokus karena tombol ditekan) dan kliknya hilang.
  if (bilah.dataset.tanda === html) return;
  bilah.dataset.tanda = html;
  bilah.innerHTML = html;
  $("btn-batal").addEventListener("click", () => { S.kini = salin(S.awal); renderPanelIsi(); renderRingkas(); renderBilah(); });
  $("btn-simpan").addEventListener("click", simpanPengaturan);
}

async function simpanPengaturan() {
  const pesan = $("ket-simpan");
  const beda = bedaPengaturan(S.awal, S.kini, skema);
  if (!S.klien || !beda.length) return;
  const tombol = $("btn-simpan");
  tombol.disabled = true;
  tombol.textContent = "Menyimpan…";
  try {
    // Ambil berkas terbaru, lalu terapkan hanya isian yang Anda ubah, supaya perubahan orang lain tidak tertimpa.
    const segar = await S.klien.bacaBerkas(BERKAS, S.cabang);
    const data = JSON.parse(segar.teks);
    const bentrok = beda.filter((b) => !sama(ambil(data, b.jalur).nilai, b.dari));
    if (bentrok.length) {
      throw new GalatGitHub(`Isian berikut sudah diubah orang lain sejak dimuat: ${bentrok.map((b) => b.kolom.label).join(", ")}. Tekan Muat ulang di atas, lalu ulangi perubahan Anda.`, { kode: "bentrok" });
    }
    for (const b of beda) atur(data, b.jalur, b.ke);
    const masalah = periksa(data, skema);
    if (masalah.length) throw new GalatGitHub(`Hasil akhirnya belum sah: ${masalah[0].pesan}`, { kode: "ditolak" });
    const ringkas = beda.slice(0, 20).map((b) => `- ${b.kolom.label}: ${teksNilai(b.kolom, b.dari)} menjadi ${teksNilai(b.kolom, b.ke)}`).join("\n");
    const hasil = await S.klien.simpanBerkas({
      path: BERKAS, teks: tulisPengaturan(data), sha: segar.sha, cabang: S.cabang,
      pesan: `Pengaturan: ${beda.length} isian diubah lewat panel admin\n\n${ringkas}${beda.length > 20 ? `\n- dan ${beda.length - 20} lainnya` : ""}\n\nDiubah oleh @${S.pengguna.login} lewat panel admin.`,
    });
    S.awal = salin(data);
    S.kini = salin(data);
    S.sha = hasil.sha;
    if (FS) { S.menunggu = { oleh: S.pengguna.login }; renderSambungan(); }
    renderPanelIsi(); renderRingkas(); renderBilah();
    tampilPesan(pesan, "sukses", FS
      ? "Tersimpan. Sistem menerapkannya dan memperbarui dashboard otomatis, biasanya dalam 15 sampai 30 menit pada jam kerja."
      : `Tersimpan. <a href="${esc(urlAman(hasil.urlCommit))}" rel="noopener" target="_blank">Lihat perubahannya di GitHub</a>. Dashboard diperbarui otomatis sekitar 2 sampai 3 menit lagi.`);
    mulaiPantau("pipeline.yml", Date.now());
  } catch (e) {
    lapor(e);
    tampilPesan(pesan, "galat", esc(galatTeks(e)));
    renderBilah();
  }
}

/* ------------------------------------------------------------------ alur kerja */
const NAMA_STATUS = { queued: "menunggu giliran", in_progress: "sedang berjalan", waiting: "menunggu", requested: "menunggu", pending: "menunggu" };
const NAMA_HASIL = { success: "selesai dengan baik", failure: "gagal", cancelled: "dibatalkan", skipped: "dilewati", timed_out: "kehabisan waktu" };

function htmlProses(p) {
  if (!p) return "Belum pernah dijalankan";
  const teks = FS && p.status === "queued" ? "menunggu diambil (biasanya kurang dari 1 menit pada jam kerja)"
    : p.status === "completed" ? (NAMA_HASIL[p.hasil] || p.hasil || "selesai") : (NAMA_STATUS[p.status] || p.status);
  const warna = p.status !== "completed" ? "info" : p.hasil === "success" ? "baik" : "tinggi";
  const tautan = p.url ? ` · <a href="${esc(urlAman(p.url))}" rel="noopener" target="_blank">${FS ? "rincian proses" : "lihat di GitHub"}</a>` : "";
  return `<span class="lencana ${warna}">${esc(teks)}</span> ${esc(waktu(p.dibuat))}${p.oleh ? ` oleh ${esc(p.oleh)}` : ""}${tautan}${p.pesan ? `<br><span class="meta-kecil">${esc(p.pesan)}</span>` : ""}`;
}

async function muatProses(berkas) {
  try { S.proses = { ...(S.proses || {}), [berkas]: await S.klien.prosesTerakhir(berkas, S.cabang) }; } catch { /* tidak kritis */ }
}

function tampilProses(berkas) {
  const el = document.getElementById(`proses-${berkas}`);
  if (el) el.innerHTML = htmlProses(S.proses?.[berkas]);
}

/** Memeriksa proses terakhir tiap 8 detik sampai selesai (paling lama sekitar 6 menit). */
function mulaiPantau(berkas, sejak) {
  if (FS) return; // dengan Firestore, status dipantau langsung sejak tersambung
  clearInterval(S.pantau[berkas]);
  let hitung = 0;
  S.pantau[berkas] = setInterval(async () => {
    hitung += 1;
    await muatProses(berkas);
    const p = S.proses?.[berkas];
    const baru = p && new Date(p.dibuat).getTime() >= sejak - 20000;
    if (baru) tampilProses(berkas);
    if ((baru && p.status === "completed") || hitung > 45 || !S.klien) clearInterval(S.pantau[berkas]);
  }, 8000);
}

function htmlAlur(a) {
  const bidang = a.masukan.map((m) => {
    const id = `a-${a.berkas}-${m.nama}`;
    const kontrol = m.tipe === "pilihan"
      ? `<select id="${id}" data-masukan="${m.nama}">${m.pilihan.map((p) => `<option value="${esc(p.nilai)}" ${p.nilai === m.bawaan ? "selected" : ""}>${esc(p.label)}</option>`).join("")}</select>`
      : `<input id="${id}" data-masukan="${m.nama}" type="text" maxlength="${m.maks_panjang || 200}" autocomplete="off" value="${esc(m.bawaan || "")}" placeholder="${esc(m.contoh || "")}">`;
    return `<label>${esc(m.label)}${m.wajib ? " *" : ""}${kontrol}</label>`;
  }).join("");
  return `<section class="kartu-alur" data-berkas="${a.berkas}">
    <h3>${esc(a.judul)}</h3><p class="bantuan">${esc(a.bantuan)}</p>
    <div class="form-grid">${bidang}</div>
    <div class="baris-kontrol" style="margin-top:14px"><button class="tombol utama-aksi" type="button" data-jalankan ${S.klien ? "" : "disabled"}>Jalankan sekarang</button>
      <span class="status-proses" id="proses-${a.berkas}">${S.klien ? htmlProses(S.proses?.[a.berkas]) : (FS ? "Menghubungkan…" : "Sambungkan ke GitHub dulu")}</span></div>
    <div class="pesan-bagian" role="status"></div></section>`;
}

async function jalankan(wadah) {
  const a = skema.alur_kerja.find((x) => x.berkas === wadah.dataset.berkas);
  const pesan = wadah.querySelector(".pesan-bagian");
  const masukan = {};
  for (const m of a.masukan) {
    const nilai = wadah.querySelector(`[data-masukan="${m.nama}"]`).value.trim();
    if (m.wajib && !nilai) return tampilPesan(pesan, "galat", `Isi dulu "${esc(m.label)}".`);
    if (nilai) masukan[m.nama] = nilai;
  }
  const tombol = wadah.querySelector("[data-jalankan]");
  tombol.disabled = true;
  try {
    const mulai = Date.now();
    await S.klien.jalankanAlur(a.berkas, S.cabang, masukan);
    tampilPesan(pesan, "sukses", FS
      ? "Permintaan tersimpan. Sistem mengambilnya dalam sekitar 1 menit pada jam kerja (10 menit di luar jam kerja), lalu statusnya berubah sendiri di sebelah tombol."
      : `Sudah diminta dijalankan. Statusnya muncul di sebelah tombol dalam beberapa detik. <a href="${esc(S.klien.alamatRepo)}/actions/workflows/${esc(a.berkas)}" rel="noopener" target="_blank">Lihat di GitHub</a>.`);
    mulaiPantau(a.berkas, mulai);
  } catch (e) {
    tampilPesan(pesan, "galat", esc(galatTeks(e)));
  } finally {
    tombol.disabled = false;
  }
}

/* ------------------------------------------------------------------ panel dan tab */
function urutBagian(kode) {
  const bagian = new Map();
  const ambilBagian = (nama) => { if (!bagian.has(nama)) bagian.set(nama, { kolom: [], rahasia: [] }); return bagian.get(nama); };
  skema.kolom.filter((k) => k.kelompok === kode).forEach((k) => ambilBagian(k.bagian).kolom.push(k));
  skema.rahasia.filter((r) => r.kelompok === kode).forEach((r) => ambilBagian(r.bagian).rahasia.push(r));
  return bagian;
}

// Kunci tiap AI. GitHub Models memakai akses bawaan GitHub Actions, jadi tanpa kunci.
const KUNCI_AI = [["Gemini", "GEMINI_API_KEY"], ["Groq", "GROQ_API_KEY"], ["Cerebras", "CEREBRAS_API_KEY"],
  ["OpenRouter", "OPENROUTER_API_KEY"], ["Mistral", "MISTRAL_API_KEY"]];

function htmlKesiapanAi() {
  const ada = (n) => S.rahasia?.has(n);
  const status = (nama, siap, ket) => `<span class="lencana ${siap ? "baik" : "polos"}">${nama}: ${ket}</span>`;
  const tahu = S.klien && !S.rahasiaGalat;
  const nSiap = 1 + KUNCI_AI.filter(([, k]) => ada(k)).length;
  return `<div class="kesiapan-ai">
    ${KUNCI_AI.map(([nama, k]) => status(nama, ada(k), tahu ? (ada(k) ? "kunci sudah diisi" : "kunci belum diisi") : "belum dicek")).join("\n    ")}
    ${status("GitHub Models", true, "siap, tanpa kunci")}
    ${status("Claude", ada("ANTHROPIC_API_KEY"), tahu ? (ada("ANTHROPIC_API_KEY") ? "kunci sudah diisi" : "tidak dipakai") : "belum dicek")}
    ${status("Pencarian web (Tavily)", ada("TAVILY_API_KEY"), tahu ? (ada("TAVILY_API_KEY") ? "aktif" : "kunci belum diisi") : "belum dicek")}</div>
    <p class="ringkas-tab">Pada mode Otomatis, kalau satu AI kena batas pemakaian gratis, sistem pindah ke AI berikutnya. Makin banyak kunci gratis yang diisi, makin kecil kemungkinan gagal${tahu ? ` (sekarang ${nSiap} AI gratis siap)` : ""}. Dengan kunci Tavily, sistem lebih dulu mencari di web, lalu AI menyusun kandidat dari hasil pencarian itu, jadi alamat webnya nyata. Untuk mencoba, buka tab <a href="#" data-ke-tab="jalankan">Jalankan</a> lalu pilih "Cari sumber data dengan AI".</p>`;
}

/** Isian yang diketik tapi belum dikirim (kunci rahasia dan masukan alur kerja), supaya tidak hilang saat panel digambar ulang. */
function ambilDraf() {
  const draf = {};
  document.querySelectorAll("[data-rahasia]").forEach((el) => { if (el.value) draf[`r:${el.dataset.rahasia}`] = el.value; });
  document.querySelectorAll("[data-masukan]").forEach((el) => { draf[`a:${el.closest(".kartu-alur").dataset.berkas}:${el.dataset.masukan}`] = el.value; });
  return draf;
}

function pulihkanDraf(draf) {
  for (const [kunci, nilai] of Object.entries(draf)) {
    const [jenis, a, b] = kunci.split(":");
    const el = jenis === "r" ? document.getElementById(`r-${a}`) : document.querySelector(`.kartu-alur[data-berkas="${CSS.escape(a)}"] [data-masukan="${CSS.escape(b)}"]`);
    if (el && !el.disabled) el.value = nilai;
  }
}

function renderPanelIsi({ bersih = false } = {}) {
  const draf = bersih ? {} : ambilDraf();
  const kelompok = skema.kelompok.map((g) => {
    const bagian = [...urutBagian(g.kode)].map(([nama, isi]) => `<div class="bagian-pengaturan" data-bagian="${esc(nama)}">
      <h3>${esc(nama)}</h3>
      ${isi.kolom.length ? `<div class="kolom-isian">${isi.kolom.map(htmlKolom).join("")}</div>` : ""}
      ${isi.rahasia.length && FS && isi.rahasia.every((r) => rahasiaFirebase(r.nama)) ? `<div class="kolom-isian">${isi.rahasia.map(htmlRahasia).join("")}</div>`
        : isi.rahasia.length ? `<div class="kolom-isian">${isi.rahasia.map(htmlRahasia).join("")}</div>
        <div class="rahasia-aksi"><button class="tombol utama-aksi kecil" type="button" data-simpan-kunci ${S.klien ? "" : "disabled"}>Simpan kunci yang diisi</button>
          <span class="meta-kecil">${S.klien ? (S.rahasiaGalat ? esc(S.rahasiaGalat) : FS ? "Kunci hanya bisa ditulis dari sini dan hanya dibaca mesin pengolah. Tidak ada yang bisa membacanya lewat situs." : "Kunci dienkripsi di browser, lalu disimpan di GitHub Secrets.") : (FS ? "Menghubungkan…" : "Sambungkan ke GitHub dulu.")}</span></div>
        <div class="pesan-bagian" role="status"></div>` : ""}
    </div>`).join("");
    return `<div class="panel-pengaturan" data-panel="${g.kode}" ${g.kode === S.tab ? "" : "hidden"}>
      <p class="ringkas-tab">${esc(g.ringkas)}</p>${g.kode === "ai" ? htmlKesiapanAi() : ""}${bagian}</div>`;
  }).join("");
  const alur = `<div class="panel-pengaturan" data-panel="jalankan" ${S.tab === "jalankan" ? "" : "hidden"}>
    <p class="ringkas-tab">${FS ? "Minta sistem menjalankan proses sekarang, tanpa menunggu jadwal." : "Jalankan proses di GitHub tanpa membuka GitHub."}</p>${skema.alur_kerja.map(htmlAlur).join("")}</div>`;
  $("panel-isi").innerHTML = kelompok + alur;
  pulihkanDraf(draf);
  perbarui();
}

function renderTab() {
  const semua = [...skema.kelompok.map((g) => [g.kode, g.judul]), ["jalankan", "Jalankan"]];
  $("tab").innerHTML = semua.map(([kode, judul]) => `<button type="button" data-tab="${kode}" aria-pressed="${kode === S.tab}">${esc(judul)}</button>`).join("");
}

function pilihTab(kode) {
  S.tab = kode;
  document.querySelectorAll("[data-tab]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tab === kode)));
  document.querySelectorAll("[data-panel]").forEach((p) => { p.hidden = p.dataset.panel !== kode; });
}

function renderKeterangan() {
  $("ket-simpan").textContent = FS
    ? (S.klien ? "Perubahan tersimpan langsung, lalu sistem menerapkannya dan memperbarui dashboard otomatis." : "Menghubungkan dengan akun Anda…")
    : S.klien
      ? "Perubahan disimpan sebagai commit di GitHub, lalu dashboard diperbarui otomatis."
      : "Tampilan baca saja. Sambungkan ke GitHub di atas untuk mengubah.";
}

function renderSemua({ bersih = false } = {}) {
  renderSambungan();
  renderTab();
  renderPanelIsi({ bersih });
  renderKeterangan();
  renderRingkas();
}

/* ------------------------------------------------------------------ pasang */
$("tab").addEventListener("click", (e) => { const b = e.target.closest("[data-tab]"); if (b) pilihTab(b.dataset.tab); });
const isi = $("panel-isi");
isi.addEventListener("input", saatIsianBerubah);
isi.addEventListener("change", saatIsianBerubah);
isi.addEventListener("click", (e) => {
  const ke = e.target.closest("[data-ke-tab]");
  if (ke) { e.preventDefault(); pilihTab(ke.dataset.keTab); return; }
  const simpan = e.target.closest("[data-simpan-kunci]");
  if (simpan) return simpanKunci(simpan.closest(".bagian-pengaturan"));
  const hapus = e.target.closest("[data-hapus]");
  if (hapus) return hapusKunci(hapus.dataset.hapus, hapus.closest(".bagian-pengaturan"));
  const jalan = e.target.closest("[data-jalankan]");
  if (jalan) return jalankan(jalan.closest(".kartu-alur"));
});
window.addEventListener("beforeunload", (e) => { if (adaPerubahan()) { e.preventDefault(); e.returnValue = ""; } });

renderSemua();
if (FS) {
  await sambungFirestore();
} else {
  const sesiTersimpan = bacaSesi();
  if (sesiTersimpan?.token) await sambungkan(sesiTersimpan.token, sesiTersimpan.repo, { diam: true });
}

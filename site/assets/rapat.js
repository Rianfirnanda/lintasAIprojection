// Mode Videotron (dulu Mode Rapat TPID): layar penuh untuk rapat, TV, atau videotron. Tampilan dashboard berganti otomatis
// (ringkasan, harga semua bahan pokok, pergerakan sebulan, tren 30 hari, peringatan, perkiraan 7 hari, hari raya) dengan
// teks berjalan berisi semua harga di bawah layar. Tidak ada tombol di layar: operator memakai keyboard (Esc keluar,
// panah kiri/kanan pindah, spasi jeda) atau ketuk dua kali untuk keluar. Data diperbarui sendiri tanpa memuat ulang halaman,
// jadi layar penuh tidak terputus. Isi tampilan disusun di videotron-isi.js.
import { muatJSON, esc } from "./app.js";
import { ikon } from "./dashboard.js";
import { susunTampilan, teksBerjalan, tglPanjang, kartuHarga } from "./videotron-isi.js";

const SEGAR_MS = 10 * 60e3; // periksa data baru tiap 10 menit
let layar = null, tampilan = [], urutan = 0, jeda = false, mulai = 0, rafId = 0, jamId = 0, segarId = 0, kursorId = 0;
let data = null, versiData = "";

function muatGaya() {
  if (document.querySelector("link[data-videotron]")) return;
  const l = document.createElement("link");
  l.rel = "stylesheet";
  l.href = "assets/videotron.css";
  l.dataset.videotron = "";
  document.head.append(l);
}

async function muatData() {
  const [ringkasan, sinyal, meta] = await Promise.all([muatJSON("ringkasan.json"), muatJSON("sinyal.json").catch(() => null), muatJSON("meta.json").catch(() => null)]);
  // Deret harian untuk tren 30 hari: satu barang wakil tiap komoditas.
  const { wakilKomoditas } = await import("./videotron-isi.js");
  const wakil = wakilKomoditas(ringkasan.varian || []).slice(0, 8);
  const seri = Object.fromEntries((await Promise.all(wakil.map((v) => muatJSON(`seri/${v.kode}.json`).then((s) => [v.kode, s]).catch(() => null)))).filter(Boolean));
  return { ringkasan, sinyal, seri, meta };
}

/** Berapa kartu harga muat di satu layar: ukur satu kartu contoh di panggung (menyesuaikan ukuran dan arah layar). */
function ukuranGrid() {
  const fs = parseFloat(getComputedStyle(layar).fontSize) || 20;
  const panggung = layar.querySelector(".vt-panggung"), isi = layar.querySelector(".vt-isi");
  const { width: lebar, height: tinggi } = panggung.getBoundingClientRect();
  const celah = fs * 0.8;
  const kolom = Math.max(1, Math.min(6, Math.floor((lebar + celah) / (fs * 15 + celah))));
  const terpanjang = [...(data.ringkasan.varian || [])].sort((a, b) => b.nama.length - a.nama.length)[0];
  isi.style.setProperty("--skala", 1);
  isi.innerHTML = `<div class="vt-grid-harga" style="--kolom:${kolom}">${terpanjang ? kartuHarga(terpanjang) : ""}</div>`;
  const kartu = isi.querySelector(".vt-harga");
  const tinggiKartu = kartu ? kartu.getBoundingClientRect().height : fs * 9;
  const baris = Math.max(1, Math.min(6, Math.floor((tinggi + celah) / (tinggiKartu + celah))));
  const barisTren = Math.max(1, Math.floor(tinggi / (fs * 10)));
  return { kolom, perHalaman: kolom * baris, jumlahTren: Math.max(4, Math.min(8, Math.min(kolom, 4) * barisTren)),
    barisKira: Math.max(4, Math.min(10, Math.floor(tinggi / (fs * 2.9)) - 2)) };
}

/** Jaga-jaga: bila isi satu tampilan masih lebih tinggi dari layar, kecilkan sedikit supaya tidak terpotong. */
function pasKan() {
  const isi = layar.querySelector(".vt-isi"), panggung = layar.querySelector(".vt-panggung");
  let skala = 1;
  isi.style.setProperty("--skala", skala);
  // ukur dari panggung (tidak ikut diperkecil), ulangi sampai isinya muat
  for (let i = 0; i < 4 && panggung.scrollHeight > panggung.clientHeight + 1 && skala > 0.5; i++) {
    skala = Math.max(0.5, skala * (panggung.clientHeight / panggung.scrollHeight) * 0.98);
    isi.style.setProperty("--skala", skala.toFixed(3));
  }
}

function susun() {
  const g = ukuranGrid();
  tampilan = susunTampilan(data, { ...g, ikon });
  layar.style.setProperty("--kolom", g.kolom);
  layar.querySelector(".vt-titik").innerHTML = tampilan.map(() => "<i></i>").join("");
  layar.querySelector(".vt-jalan-trek").innerHTML = (() => { const t = teksBerjalan(data.ringkasan.varian); return `<div>${t}</div><div aria-hidden="true">${t}</div>`; })();
  const jumlah = (data.ringkasan.varian || []).length;
  layar.querySelector(".vt-jalan-trek").style.setProperty("--lama", `${Math.max(40, jumlah * 5)}s`);
  const tanggal = data.meta?.tanggal_data_terakhir || data.ringkasan.varian?.[0]?.tanggal_terakhir;
  layar.querySelector(".vt-data").innerHTML = `<i></i>Data ${esc(tglPanjang(tanggal))}`;
  if (urutan >= tampilan.length) urutan = 0;
}

function gambar() {
  const t = tampilan[urutan];
  if (!t) return;
  layar.querySelector(".vt-judul").textContent = t.judul;
  layar.querySelector(".vt-sub").innerHTML = t.sub || "";
  layar.querySelector(".vt-nomor").textContent = `${urutan + 1}/${tampilan.length}`;
  const isi = layar.querySelector(".vt-isi");
  isi.classList.remove("vt-masuk");
  void isi.offsetWidth;
  isi.innerHTML = t.isi;
  isi.dataset.kunci = t.kunci;
  pasKan();
  isi.classList.add("vt-masuk");
  layar.querySelectorAll(".vt-titik i").forEach((b, i) => b.classList.toggle("kini", i === urutan));
  mulai = performance.now();
}

function pindah(arah) {
  urutan = (urutan + arah + tampilan.length) % tampilan.length;
  gambar();
}

function putar(kini) {
  if (!layar) return;
  const bar = layar.querySelector(".vt-kemajuan i");
  const lama = (tampilan[urutan]?.lama || 15) * 1000;
  if (jeda) mulai = kini - Number(bar.dataset.t || 0);
  else {
    const t = kini - mulai;
    bar.style.transform = `scaleX(${Math.min(1, t / lama)})`;
    bar.dataset.t = t;
    if (t >= lama) pindah(1);
  }
  rafId = requestAnimationFrame(putar);
}

function tulisJam() {
  const d = new Date();
  const hari = d.toLocaleDateString("id-ID", { timeZone: "Asia/Jakarta", weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const jam = d.toLocaleTimeString("id-ID", { timeZone: "Asia/Jakarta", hour: "2-digit", minute: "2-digit" }).replace(":", ".");
  layar.querySelector(".vt-jam").innerHTML = `<b>${jam}</b><span>WIB</span><small>${esc(hari)}</small>`;
}

/** Data baru: perbarui isi tanpa memuat ulang halaman (layar penuh tetap). */
async function segarkan(paksa = false) {
  try {
    if (!paksa) {
      const r = await fetch(`data/meta.json?t=${Date.now()}`, { cache: "no-store" });
      const m = r.ok ? await r.json() : null;
      if (!m?.dibuat || m.dibuat === versiData) return;
      const { catatMetaBaru } = await import("./app.js");
      catatMetaBaru?.(m);
    }
    data = await muatData();
    versiData = data.meta?.dibuat || versiData;
    susun();
    gambar();
  } catch (e) {
    console.warn("videotron: data belum bisa diperbarui", e);
  }
}

function tutup() {
  cancelAnimationFrame(rafId);
  clearInterval(jamId);
  clearInterval(segarId);
  clearTimeout(kursorId);
  document.removeEventListener("keydown", tombol);
  window.removeEventListener("resize", ubahUkuran);
  window.removeEventListener("lbp:data-baru", dataBaru);
  if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
  layar?.remove();
  layar = null;
  document.documentElement.classList.remove("rincian-terbuka", "videotron-aktif");
  try { sessionStorage.removeItem("lbp-videotron"); } catch { /* abaikan */ }
}

function tombol(e) {
  if (!layar) return;
  if (e.key === "Escape") { e.preventDefault(); tutup(); }
  else if (e.key === "ArrowRight" || e.key === "PageDown") { e.preventDefault(); pindah(1); }
  else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); pindah(-1); }
  else if (e.key === " " || e.key.toLowerCase() === "p") { e.preventDefault(); jeda = !jeda; layar.classList.toggle("jeda", jeda); }
  else if (e.key.toLowerCase() === "f") layar.requestFullscreen?.().catch(() => {});
}

let jedaUkuran = 0;
function ubahUkuran() {
  clearTimeout(jedaUkuran);
  jedaUkuran = setTimeout(() => { if (layar && data) { const k = tampilan[urutan]?.kunci; susun(); urutan = Math.max(0, tampilan.findIndex((t) => t.kunci === k)); gambar(); } }, 300);
}

const dataBaru = () => segarkan(true);

/** Kursor disembunyikan bila tetikus diam, supaya layar bersih. */
function aturKursor() {
  layar.classList.remove("kursor-sembunyi");
  clearTimeout(kursorId);
  kursorId = setTimeout(() => layar?.classList.add("kursor-sembunyi"), 2500);
}

export async function bukaModeRapat() {
  if (layar) return;
  muatGaya();
  layar = document.createElement("div");
  layar.className = "videotron";
  layar.setAttribute("role", "region");
  layar.setAttribute("aria-label", "Mode Videotron: harga pangan Kabupaten Bengkulu Tengah");
  layar.tabIndex = -1;
  layar.innerHTML = `
    <header class="vt-kepala">
      <div class="vt-merek"><img src="assets/logo-takar-pangan.webp" alt="" width="56" height="56">
        <div><b>Harga Pangan Kabupaten Bengkulu Tengah</b><span>Takar Pangan 10•21 · BPS Kabupaten Bengkulu Tengah</span></div></div>
      <div class="vt-kanan"><span class="vt-data"><i></i>Memuat data…</span><div class="vt-jam"></div></div>
    </header>
    <div class="vt-bilah"><div><h1 class="vt-judul">Memuat…</h1><p class="vt-sub"></p></div>
      <div class="vt-posisi"><span class="vt-titik" aria-hidden="true"></span><span class="vt-nomor"></span></div></div>
    <div class="vt-kemajuan" aria-hidden="true"><i></i></div>
    <main class="vt-panggung"><div class="vt-isi" aria-live="polite"></div></main>
    <div class="vt-jalan" aria-label="Harga semua bahan pokok"><span class="vt-jalan-label">Harga hari ini</span><div class="vt-jalan-jendela"><div class="vt-jalan-trek"></div></div></div>
    <footer class="vt-kaki"><span>Sumber: SP2KP Kemendag, PIHPS Bank Indonesia, dan petugas pasar BPS. Perkiraan bukan angka resmi.</span>
      <span class="vt-petunjuk">Tekan Esc atau ketuk dua kali untuk keluar</span></footer>`;
  document.body.append(layar);
  document.documentElement.classList.add("rincian-terbuka", "videotron-aktif");
  try { sessionStorage.setItem("lbp-videotron", "1"); } catch { /* abaikan */ }
  layar.requestFullscreen?.().catch(() => {});
  layar.focus({ preventScroll: true });
  document.addEventListener("keydown", tombol);
  layar.addEventListener("dblclick", tutup);
  layar.addEventListener("pointermove", aturKursor, { passive: true });
  window.addEventListener("resize", ubahUkuran);
  window.addEventListener("lbp:data-baru", dataBaru);
  aturKursor();
  tulisJam();
  jamId = setInterval(tulisJam, 15000);
  setTimeout(() => layar?.querySelector(".vt-petunjuk")?.classList.add("pudar"), 8000);
  try {
    data = await muatData();
  } catch (e) {
    layar.querySelector(".vt-isi").innerHTML = `<p class="vt-kalimat">Data belum bisa dimuat: ${esc(e.message || e)}</p>`;
    return;
  }
  if (!layar) return;
  versiData = data.meta?.dibuat || "";
  // tunggu ukuran layar penuh selesai berubah sebelum menghitung isi tiap layar
  await new Promise((r) => setTimeout(r, document.fullscreenElement ? 50 : 350));
  susun();
  gambar();
  rafId = requestAnimationFrame(putar);
  segarId = setInterval(() => segarkan(false), SEGAR_MS);
}

export const _uji = { tutup };

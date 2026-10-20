// Pencarian cepat (Ctrl+K, / atau tombol cari di bilah atas): ketik "cabai", "beras", "peringatan", dan langsung
// lompat ke barang, peringatan, halaman, atau perintah. Isinya disaring sesuai halaman yang boleh dibuka peran.
import { muatJSON, esc, rp, persen } from "./app.js";
import { ikon } from "./dashboard.js";
import { peranAktif, bolehAkses } from "./akses.js";

let dialog = null, daftar = [], pilihan = 0, hasil = [];

/** Ubah teks jadi bentuk pencarian: huruf kecil tanpa tanda baca. */
export const normal = (s) => String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9 ]+/g, " ").trim();

/** Skor kecocokan sederhana: semua kata yang diketik harus ada; awal kata dan judul diberi nilai lebih. */
export function skor(item, kueri) {
  const q = normal(kueri).split(/\s+/).filter(Boolean);
  if (!q.length) return item.awal ? 1 : 0;
  const judul = normal(item.judul), semua = `${judul} ${normal(item.kata || "")} ${normal(item.sub || "")}`;
  let nilai = 0;
  for (const k of q) {
    if (!semua.includes(k)) return 0;
    nilai += judul.startsWith(k) ? 6 : new RegExp(`\\b${k}`).test(judul) ? 4 : judul.includes(k) ? 2 : 1;
  }
  return nilai + (item.bobot || 0);
}

async function bangunDaftar(halaman) {
  const peran = peranAktif();
  const boleh = (h) => bolehAkses(peran, h);
  const isi = halaman.filter((h) => boleh(h.href)).map((h) => ({ jenis: "Halaman", ikon: "dokumen", judul: h.label, sub: h.ket || "", href: h.href, awal: true, bobot: 1 }));
  const perintah = [];
  if (boleh("index.html") && ["tpid", "analis", "admin"].includes(peran)) {
    perintah.push({ jenis: "Perintah", ikon: "layar", judul: "Mode Videotron", sub: "Layar penuh untuk rapat, TV, atau videotron, berganti otomatis", kata: "presentasi rapat tpid proyektor videotron layar tv",
      jalankan: () => import("./rapat.js").then((m) => m.bukaModeRapat()), awal: true, bobot: 2 });
  }
  perintah.push({ jenis: "Perintah", ikon: "ai", judul: "Tanya Takar", sub: "Tanya soal harga dengan kalimat biasa", kata: "tanya ai chatbot asisten bantuan",
    jalankan: () => import("./tanya.js").then((m) => m.bukaTanya()), awal: true, bobot: 2 });
  const [ringkasan, sinyal] = await Promise.all([muatJSON("ringkasan.json").catch(() => null), boleh("sinyal.html") ? muatJSON("sinyal.json").catch(() => null) : null]);
  const barang = (ringkasan?.varian || []).map((v) => ({
    jenis: "Harga", ikon: "keranjang", judul: v.nama, kata: `${v.komoditas} harga`,
    sub: `${rp(v.harga_terakhir)}/${v.satuan}${v.perubahan?.bulanan !== null && v.perubahan?.bulanan !== undefined ? ` · ${persen(v.perubahan.bulanan, 1, true)} sebulan` : ""}`,
    href: boleh("harga.html") ? `harga.html#barang=${encodeURIComponent(v.kode)}` : "index.html", bobot: 1,
  }));
  const peringatan = (sinyal?.sinyal || []).filter((s) => s.aktif).slice(0, 40).map((s) => ({
    jenis: "Peringatan", ikon: "lonceng", judul: s.judul, kata: `${s.varian || ""} ${s.komoditas || ""} peringatan ${s.keparahan}`,
    sub: `Tingkat ${s.keparahan}`, href: `sinyal.html#${encodeURIComponent(s.id)}`,
  }));
  return [...perintah, ...isi, ...barang, ...peringatan];
}

function siapkan() {
  if (dialog) return dialog;
  dialog = document.createElement("dialog");
  dialog.className = "cari-cepat";
  dialog.setAttribute("aria-label", "Pencarian cepat");
  dialog.innerHTML = `<div class="cc-kotak">
    <label class="cc-masukan">${ikon("cari", 20)}<input type="search" placeholder="Cari barang, peringatan, atau halaman…" aria-label="Cari" autocomplete="off" spellcheck="false">
      <kbd>Esc</kbd></label>
    <ul class="cc-hasil" role="listbox" aria-label="Hasil pencarian"></ul>
    <p class="cc-kaki"><span><kbd>↑</kbd><kbd>↓</kbd> pilih</span><span><kbd>Enter</kbd> buka</span><span><kbd>Ctrl</kbd>+<kbd>K</kbd> dari halaman mana pun</span></p>
  </div>`;
  document.body.append(dialog);
  const masukan = dialog.querySelector("input");
  masukan.addEventListener("input", () => { pilihan = 0; gambar(masukan.value); });
  masukan.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      pilihan = (pilihan + (e.key === "ArrowDown" ? 1 : -1) + hasil.length) % Math.max(1, hasil.length);
      tandai();
    } else if (e.key === "Enter" && hasil[pilihan]) {
      e.preventDefault();
      buka(hasil[pilihan]);
    }
  });
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog) { dialog.close(); return; }
    const li = e.target.closest("[data-i]");
    if (li) buka(hasil[Number(li.dataset.i)]);
  });
  return dialog;
}

function buka(item) {
  if (!item) return;
  dialog.close();
  if (item.jalankan) { item.jalankan(); return; }
  const [hal, hash] = item.href.split("#");
  if (hal === location.pathname.split("/").pop() && hash) { location.hash = hash; return; }
  location.href = item.href;
}

function tandai() {
  dialog.querySelectorAll("[data-i]").forEach((li) => li.setAttribute("aria-selected", String(Number(li.dataset.i) === pilihan)));
  dialog.querySelector(`[data-i="${pilihan}"]`)?.scrollIntoView({ block: "nearest" });
}

function gambar(kueri) {
  hasil = daftar.map((x) => ({ x, n: skor(x, kueri) })).filter((x) => x.n > 0).sort((a, b) => b.n - a.n).slice(0, 12).map((x) => x.x);
  const ul = dialog.querySelector(".cc-hasil");
  ul.innerHTML = hasil.length ? hasil.map((x, i) => `<li role="option" data-i="${i}" aria-selected="${i === pilihan}">
      <span class="cc-ikon">${ikon(x.ikon, 18)}</span><span class="cc-teks"><b>${esc(x.judul)}</b>${x.sub ? `<small>${esc(x.sub)}</small>` : ""}</span>
      <span class="cc-jenis">${esc(x.jenis)}</span></li>`).join("")
    : `<li class="cc-kosong">Tidak ada yang cocok. Coba kata lain, mis. "cabai" atau "laporan", atau tanyakan ke Tanya Takar.</li>`;
}

/** Membuka pencarian cepat. `halaman`: [{ href, label, ket }] dari menu situs. */
export async function bukaCariCepat(halaman) {
  const d = siapkan();
  if (!d.open) d.showModal();
  const masukan = d.querySelector("input");
  masukan.value = "";
  masukan.focus();
  if (!daftar.length) {
    d.querySelector(".cc-hasil").innerHTML = `<li class="cc-kosong">Memuat…</li>`;
    daftar = await bangunDaftar(halaman);
  }
  pilihan = 0;
  gambar("");
}

// Tanya Takar: jendela tanya-jawab di setiap halaman (tombol "Tanya" di pojok kanan bawah).
// Pertanyaan dijawab dulu oleh mesin jawab (tanya-mesin.js) dari data situs, cepat dan tanpa kunci. Bila pertanyaannya
// bebas dan tidak ada di data, AI dipakai hanya bila peran ini boleh membaca kunci AI (Administrator), dengan batas
// pemakaian harian supaya kuota gratis tidak habis. AI hanya diberi data situs sebagai bahan jawaban.
import { muatJSON, muatMeta, esc } from "./app.js";
import { ikon } from "./dashboard.js";
import { peranAktif, bolehAkses } from "./akses.js";
import { jawab, konteksAi, SISTEM_AI } from "./tanya-mesin.js";

const KUNCI_RIWAYAT = "lbp-tanya-riwayat";
const KUNCI_KUOTA = "lbp-tanya-ai";
const BATAS_AI_HARIAN = 30;
const SARAN_AWAL = ["Harga cabai hari ini", "Apa yang naik paling tinggi?", "Perkiraan harga beras minggu depan", "Ada peringatan apa?", "Kapan hari raya berikutnya?"];

let panel = null, data = null, meta = null, sibuk = false;
const seri = {};
const kurangiGerak = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const baca = (k, awal) => { try { return JSON.parse(sessionStorage.getItem(k)) ?? awal; } catch { return awal; } };
const simpan = (k, v) => { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch { /* abaikan */ } };

function bolehAi() {
  return peranAktif() === "admin" && meta?.login === "firebase";
}
function sisaKuotaAi() {
  const hariIni = new Date().toLocaleDateString("sv-SE", { timeZone: "Asia/Jakarta" });
  let k;
  try { k = JSON.parse(localStorage.getItem(KUNCI_KUOTA)) || {}; } catch { k = {}; }
  return { hariIni, pakai: k.tanggal === hariIni ? k.pakai || 0 : 0 };
}
function catatPakaiAi() {
  const { hariIni, pakai } = sisaKuotaAi();
  try { localStorage.setItem(KUNCI_KUOTA, JSON.stringify({ tanggal: hariIni, pakai: pakai + 1 })); } catch { /* abaikan */ }
}

async function siapkanData() {
  if (data) return data;
  meta ||= await muatMeta().catch(() => null);
  const peran = peranAktif();
  const [ringkasan, sinyal, berita] = await Promise.all([
    muatJSON("ringkasan.json"),
    bolehAkses(peran, "sinyal.html") ? muatJSON("sinyal.json").catch(() => null) : null,
    bolehAkses(peran, "berita.html") ? muatJSON("berita.json").catch(() => null) : null,
  ]);
  data = { ringkasan, sinyal, meta, berita: berita?.kesimpulan?.[0]?.ringkas || "" };
  return data;
}

function tautanBoleh(daftar) {
  const peran = peranAktif();
  return (daftar || []).filter((t) => bolehAkses(peran, t.href.split("#")[0]));
}

function gelembung(p) {
  const tautan = tautanBoleh(p.tautan);
  return `<li class="tj-pesan ${p.dari === "saya" ? "saya" : "takar"}${p.ai ? " ai" : ""}">
    ${p.dari === "saya" ? "" : `<span class="tj-avatar" aria-hidden="true">${p.ai ? "AI" : "T"}</span>`}
    <div class="tj-gelembung">${(p.baris || []).map((b) => `<p>${esc(b)}</p>`).join("")}
      ${tautan.length ? `<div class="tj-tautan">${tautan.map((t) => `<a href="${esc(t.href)}">${esc(t.label)} →</a>`).join("")}</div>` : ""}
      ${p.ai ? `<small class="tj-asal">Jawaban AI dari data situs${p.model ? ` · ${esc(p.model)}` : ""}. Bisa keliru, cek angkanya di halaman Harga.</small>` : ""}
    </div></li>`;
}

function gambarRiwayat() {
  const riwayat = baca(KUNCI_RIWAYAT, []);
  const ul = panel.querySelector(".tj-daftar");
  ul.innerHTML = riwayat.length ? riwayat.map(gelembung).join("")
    : gelembung({ dari: "takar", baris: ["Halo! Saya Tanya Takar. Tanyakan harga pangan di Bengkulu Tengah dengan kalimat biasa, misalnya \"harga cabai hari ini\"."] });
  gambarSaran(riwayat.length ? riwayat[riwayat.length - 1].saran || [] : SARAN_AWAL);
  ul.scrollTop = ul.scrollHeight;
}

function gambarSaran(saran) {
  const wadah = panel.querySelector(".tj-saran");
  const isi = (saran?.length ? saran : SARAN_AWAL).slice(0, 4);
  wadah.innerHTML = isi.map((s) => `<button type="button" class="chip-saring">${esc(s)}</button>`).join("");
}

/** Munculkan isi jawaban kata demi kata, supaya terasa sedang "diketik". */
async function ketikkan(li) {
  if (kurangiGerak()) return;
  const paragraf = [...li.querySelectorAll(".tj-gelembung > p")];
  const asli = paragraf.map((p) => p.textContent);
  paragraf.forEach((p) => { p.textContent = ""; });
  const ul = panel.querySelector(".tj-daftar");
  for (let i = 0; i < paragraf.length; i++) {
    const kata = asli[i].split(" ");
    const jeda = Math.max(8, Math.min(28, 900 / kata.length));
    for (let j = 0; j < kata.length; j++) {
      paragraf[i].textContent = kata.slice(0, j + 1).join(" ");
      if (j % 3 === 0) ul.scrollTop = ul.scrollHeight;
      await new Promise((r) => setTimeout(r, jeda));
    }
  }
  ul.scrollTop = ul.scrollHeight;
}

async function kirim(pertanyaan) {
  pertanyaan = pertanyaan.trim().slice(0, 300);
  if (!pertanyaan || sibuk) return;
  sibuk = true;
  const ul = panel.querySelector(".tj-daftar");
  const riwayat = baca(KUNCI_RIWAYAT, []);
  riwayat.push({ dari: "saya", baris: [pertanyaan] });
  simpan(KUNCI_RIWAYAT, riwayat);
  gambarRiwayat();
  ul.insertAdjacentHTML("beforeend", `<li class="tj-pesan takar tj-ketik"><span class="tj-avatar" aria-hidden="true">T</span><div class="tj-gelembung"><span class="tj-titik"><i></i><i></i><i></i></span></div></li>`);
  ul.scrollTop = ul.scrollHeight;
  let balasan;
  try {
    const d = await siapkanData();
    const r = await jawab(pertanyaan, d, (kode) => (seri[kode] ||= muatJSON(`seri/${kode}.json`)));
    balasan = { dari: "takar", baris: r.baris, tautan: r.tautan, saran: r.saran };
    if (r.perluAi) {
      if (bolehAi() && sisaKuotaAi().pakai < BATAS_AI_HARIAN) {
        try {
          const { jawabBebas } = await import("./ai-situs.js");
          const a = await jawabBebas(SISTEM_AI, `DATA:\n${konteksAi(d)}\n\nPERTANYAAN: ${pertanyaan}`);
          catatPakaiAi();
          balasan = { dari: "takar", ai: true, model: a.model, baris: a.teks.split(/\n+/).map((x) => x.replace(/^[*#\s]+/, "").replace(/\*\*/g, "")).filter(Boolean),
            tautan: r.tautan, saran: r.saran };
        } catch (e) {
          balasan.baris = [...r.baris, `AI belum bisa menjawab: ${e.message || e}`];
        }
      } else if (bolehAi()) {
        balasan.baris = [...r.baris, `Batas ${BATAS_AI_HARIAN} pertanyaan AI hari ini sudah tercapai, supaya kuota gratis tidak habis. Pertanyaan tentang harga tetap bisa dijawab.`];
      } else if (r.niat === "tidak_dikenal") {
        balasan.baris = [...r.baris, "Saya bisa menjawab tentang harga barang, naik-turun harga, perkiraan, peringatan, hari raya, dan kapan data diperbarui. Coba salah satu pertanyaan di bawah."];
      }
    }
  } catch (e) {
    balasan = { dari: "takar", baris: [`Maaf, data belum bisa dimuat: ${e.message || e}`] };
  }
  riwayat.push(balasan);
  simpan(KUNCI_RIWAYAT, riwayat.slice(-40));
  ul.querySelector(".tj-ketik")?.remove();
  ul.insertAdjacentHTML("beforeend", gelembung(balasan));
  gambarSaran(balasan.saran);
  await ketikkan(ul.lastElementChild);
  sibuk = false;
}

function siapkanPanel() {
  if (panel) return panel;
  panel = document.createElement("section");
  panel.className = "tanya-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Tanya Takar");
  panel.hidden = true;
  panel.innerHTML = `
    <header class="tj-kepala"><span class="tj-logo" aria-hidden="true">${ikon("ai", 22)}</span>
      <div><b>Tanya Takar</b><small>Menjawab dari data harga situs ini</small></div>
      <button type="button" class="tj-hapus" title="Mulai percakapan baru" aria-label="Mulai percakapan baru">${ikon("sinkron", 18)}</button>
      <button type="button" class="tj-tutup" aria-label="Tutup">${ikon("silang", 18)}</button></header>
    <ul class="tj-daftar" aria-live="polite"></ul>
    <div class="tj-saran" aria-label="Contoh pertanyaan"></div>
    <form class="tj-form"><label class="sr-only" for="tj-masukan">Pertanyaan</label>
      <input id="tj-masukan" type="text" maxlength="300" autocomplete="off" placeholder="Tulis pertanyaan, mis. harga bawang merah">
      <button type="submit" class="tombol utama-aksi" aria-label="Kirim">${ikon("kanan", 18)}</button></form>
    <p class="tj-kaki">Jawaban dari data situs. Angka resmi tetap di halaman Harga dan Laporan.</p>`;
  document.body.append(panel);
  panel.querySelector(".tj-tutup").addEventListener("click", tutupTanya);
  panel.querySelector(".tj-hapus").addEventListener("click", () => { simpan(KUNCI_RIWAYAT, []); gambarRiwayat(); });
  panel.querySelector(".tj-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const m = panel.querySelector("#tj-masukan");
    const q = m.value;
    m.value = "";
    kirim(q);
  });
  panel.querySelector(".tj-saran").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) kirim(b.textContent); });
  panel.addEventListener("keydown", (e) => { if (e.key === "Escape") tutupTanya(); });
  return panel;
}

export async function bukaTanya() {
  meta ||= await muatMeta().catch(() => null);
  siapkanPanel();
  panel.hidden = false;
  document.body.classList.add("tanya-terbuka");
  document.querySelector(".tanya-fab")?.setAttribute("aria-expanded", "true");
  gambarRiwayat();
  panel.querySelector("#tj-masukan").focus({ preventScroll: true });
}

export function tutupTanya() {
  if (!panel) return;
  panel.hidden = true;
  document.body.classList.remove("tanya-terbuka");
  const fab = document.querySelector(".tanya-fab");
  fab?.setAttribute("aria-expanded", "false");
  fab?.focus({ preventScroll: true });
}

/** Tombol "Tanya" melayang di pojok kanan bawah setiap halaman. */
export function pasangTombolTanya(metaSitus) {
  meta = metaSitus;
  if (document.querySelector(".tanya-fab")) return;
  const b = document.createElement("button");
  b.type = "button";
  b.className = "tanya-fab";
  b.setAttribute("aria-expanded", "false");
  b.setAttribute("aria-label", "Tanya Takar: tanya soal harga dengan kalimat biasa");
  b.innerHTML = `${ikon("ai", 22)}<span>Tanya</span>`;
  b.addEventListener("click", () => (panel && !panel.hidden ? tutupTanya() : bukaTanya()));
  document.body.append(b);
}

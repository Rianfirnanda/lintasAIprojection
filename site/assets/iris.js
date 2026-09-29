// Iris Harga: pandangan radial seluruh varian. Tiap batang = deviasi harga terakhir terhadap baseline 28 hari.
// Keluar (merah) = di atas pola normal, ke dalam (biru) = di bawah; lingkar tengah = baseline. Skala linear.
import { esc, rp, persen, warna } from "./app.js";

const NS = "http://www.w3.org/2000/svg";
const C = 300;
const R_PUPIL = 96;
const R_BASE = 166;       // lingkar baseline (deviasi 0)
const SKALA = 2;          // px per 1% deviasi (linear)
const BATAS = 30;         // batang dijepit ±30%; angka sebenarnya tetap tertulis
const R_BUSUR = 243;      // busur kelompok komoditas
const R_LABEL = 251;      // pita label kelompok (teks melengkung)
const R_BEZEL = 292;

let nomor = 0;

function titik(r, sudut) {
  return [C + r * Math.cos(sudut), C + r * Math.sin(sudut)];
}

function sektor(r1, r2, a1, a2) {
  const [x1, y1] = titik(r1, a1), [x2, y2] = titik(r2, a1), [x3, y3] = titik(r2, a2), [x4, y4] = titik(r1, a2);
  const besar = a2 - a1 > Math.PI ? 1 : 0;
  return `M${x1.toFixed(2)},${y1.toFixed(2)} L${x2.toFixed(2)},${y2.toFixed(2)} A${r2},${r2} 0 ${besar} 1 ${x3.toFixed(2)},${y3.toFixed(2)} L${x4.toFixed(2)},${y4.toFixed(2)} A${r1},${r1} 0 ${besar} 0 ${x1.toFixed(2)},${y1.toFixed(2)} Z`;
}

function busur(r, a1, a2, searah = true) {
  const [x1, y1] = titik(r, searah ? a1 : a2), [x2, y2] = titik(r, searah ? a2 : a1);
  return `M${x1.toFixed(2)},${y1.toFixed(2)} A${r},${r} 0 ${Math.abs(a2 - a1) > Math.PI ? 1 : 0} ${searah ? 1 : 0} ${x2.toFixed(2)},${y2.toFixed(2)}`;
}

function el(tag, attr = {}, induk) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attr)) e.setAttribute(k, v);
  if (induk) induk.append(e);
  return e;
}

/**
 * @param wadah  elemen .iris-wadah
 * @param varian ringkasan.varian
 * @param komoditas master.komoditas (menentukan urutan & kelompok)
 * @param ambang {kelompok: persen} — batas "di luar pola normal"
 * @param opsi {diLuar, sinyalTinggi, saatPilih(kode)}
 */
export function gambarIris(wadah, varian, komoditas, ambang, opsi = {}) {
  wadah.innerHTML = "";
  const id = `iris${++nomor}`;
  const w = {
    brass: warna("brass"), rule: warna("rule-2"), halus: warna("rule"), ink: warna("ink"), ink2: warna("ink-2"),
    muted: warna("muted"), up: warna("up"), down: warna("down"), netral: warna("baseline"), kritis: warna("critical"),
    bg: warna("bg"), surface2: warna("surface-2"),
  };
  const svg = el("svg", { viewBox: "0 0 600 600", role: "img",
    "aria-label": `Iris harga: deviasi ${varian.length} varian terhadap baseline 28 hari` });
  wadah.append(svg);
  const sapuan = document.createElement("div");
  sapuan.className = "iris-sapuan";
  wadah.append(sapuan);
  const tip = document.createElement("div");
  tip.className = "iris-tip";
  tip.setAttribute("role", "status");
  wadah.append(tip);

  const defs = el("defs", {}, svg);
  const akar = el("g", { class: "iris-muncul" }, svg);
  const huruf = { "font-family": "Plex Mono, monospace" };

  // Bezel instrumen: 120 tik, tiap 10 lebih panjang
  el("circle", { cx: C, cy: C, r: R_BEZEL, fill: "none", stroke: w.halus }, akar);
  const tik = el("g", { stroke: w.brass, "stroke-opacity": 0.45 }, akar);
  for (let i = 0; i < 120; i++) {
    const a = (i / 120) * Math.PI * 2 - Math.PI / 2;
    const [x1, y1] = titik(R_BEZEL, a), [x2, y2] = titik(i % 10 === 0 ? 276 : 285, a);
    el("line", { x1, y1, x2, y2, "stroke-width": i % 10 === 0 ? 1.1 : 0.6 }, tik);
  }

  // Serat iris di sekitar pupil (tekstur)
  const serat = el("g", { stroke: w.brass, "stroke-opacity": 0.08 }, akar);
  for (let i = 0; i < 180; i++) {
    const a = (i / 180) * Math.PI * 2;
    const [x1, y1] = titik(R_PUPIL + 4, a), [x2, y2] = titik(R_PUPIL + 22 + (i % 3) * 7, a);
    el("line", { x1, y1, x2, y2, "stroke-width": 0.7 }, serat);
  }

  // Lingkar acuan ±10/20/30% dan baseline
  for (const d of [-30, -20, -10, 10, 20, 30]) {
    el("circle", { cx: C, cy: C, r: R_BASE + d * SKALA, fill: "none", stroke: w.halus, "stroke-width": 0.8 }, akar);
  }
  el("circle", { cx: C, cy: C, r: R_BASE, fill: "none", stroke: w.rule, "stroke-width": 1.2 }, akar);

  // Tata letak sudut: celah di atas untuk label skala, celah kecil antar-komoditas
  const grup = komoditas.map((k) => ({ ...k, isi: k.varian.map((kode) => varian.find((v) => v.kode === kode)).filter(Boolean) }))
    .filter((k) => k.isi.length);
  const slotCelahAtas = 2.2, slotCelahGrup = 0.7;
  const totalSlot = grup.reduce((a, g) => a + g.isi.length, 0) + slotCelahGrup * grup.length + slotCelahAtas;
  const lebarSlot = (Math.PI * 2) / totalSlot;
  let sudut = -Math.PI / 2 + (slotCelahAtas / 2) * lebarSlot;

  const batangSemua = el("g", {}, akar);
  const labelGrup = el("g", { class: "iris-lg", ...huruf, "font-size": 9, "letter-spacing": 1.4, fill: w.ink2 }, akar);
  for (const g of grup) {
    const a0 = sudut;
    for (const v of g.isi) {
      const tengah = sudut + lebarSlot / 2;
      const setengah = lebarSlot * 0.31;
      const adaData = v.deviasi_persen !== null && v.deviasi_persen !== undefined;
      const devAsli = v.deviasi_persen ?? 0;
      const dev = Math.max(-BATAS, Math.min(BATAS, devAsli));
      const panjang = Math.max(Math.abs(dev) * SKALA, 2.5);
      const keluar = dev >= 0;
      const r1 = keluar ? R_BASE : R_BASE - panjang;
      const r2 = keluar ? R_BASE + panjang : R_BASE;
      const diLuar = adaData && Math.abs(devAsli) >= (ambang[v.kelompok] ?? 10);
      const isi = Math.abs(devAsli) < 1 ? w.netral : keluar ? w.up : w.down;

      const kel = el("g", { class: "iris-batang", tabindex: 0, role: "button",
        "aria-label": adaData ? `${v.nama}: ${persen(v.deviasi_persen, 1, true)} dari baseline${v.sinyal ? `, sinyal ${v.sinyal}` : ""}`
          : `${v.nama}: belum ada data`,
        style: `opacity:${diLuar ? 1 : 0.62}` }, batangSemua);
      el("path", { d: sektor(R_PUPIL, R_BUSUR, tengah - lebarSlot / 2, tengah + lebarSlot / 2), fill: "transparent" }, kel);
      // alur slot ±30%: memberi struktur "kelopak" pada iris
      el("path", { d: sektor(R_BASE - BATAS * SKALA, R_BASE + BATAS * SKALA, tengah - setengah, tengah + setengah),
        fill: w.brass, "fill-opacity": 0.045 }, kel);
      if (adaData) el("path", { d: sektor(r1, r2, tengah - setengah, tengah + setengah), fill: isi }, kel);
      if (Math.abs(devAsli) > BATAS) {
        // tanda batang terpotong skala: dua garis melintang di ujung
        for (const dr of [-5, -9]) {
          const r = keluar ? r2 + dr : r1 - dr;
          const [x1, y1] = titik(r, tengah - setengah * 1.1), [x2, y2] = titik(r, tengah + setengah * 1.1);
          el("line", { x1, y1, x2, y2, stroke: w.bg, "stroke-width": 1.6 }, kel);
        }
      }
      if (diLuar) {
        // angka deviasi di sisi baseline yang kosong pada slot yang sama
        const [tx, ty] = titik(keluar ? R_BASE - 13 : R_BASE + 13, tengah);
        const teks = el("text", { class: "iris-nilai", x: tx, y: ty + 3, ...huruf, "font-size": 9.5, "font-weight": 500, fill: w.ink,
          "text-anchor": "middle" }, kel);
        teks.textContent = persen(v.deviasi_persen, 0, true);
      }
      if (v.sinyal === "tinggi") {
        const [x, y] = titik(Math.min((keluar ? r2 : R_BASE) + 9, R_BUSUR - 5), tengah);
        el("circle", { cx: x, cy: y, r: 4.2, fill: w.kritis, stroke: w.bg, "stroke-width": 2 }, kel);
      }
      const tampil = () => {
        const kotak = wadah.getBoundingClientRect();
        const [px, py] = titik(r2 + 14, tengah);
        const skalaPx = kotak.width / 600;
        if (!adaData) {
          tip.innerHTML = `<div class="n">${esc(v.nama)}</div><div>Belum ada data yang lolos quality gate.</div>`;
        } else tip.innerHTML = `<div class="n">${esc(v.nama)}</div>
          <div class="v">${rp(v.harga_terakhir)} <span class="s">/${esc(v.satuan)}</span></div>
          <div>Terhadap baseline: <b>${persen(v.deviasi_persen, 1, true)}</b></div>
          <div>Mingguan ${persen(v.perubahan?.mingguan, 1, true)} · bulanan ${persen(v.perubahan?.bulanan, 1, true)}</div>
          ${v.sinyal ? `<div class="sinyal">Sinyal aktif: ${esc(v.sinyal)}</div>` : ""}`;
        const kiri = Math.min(Math.max(px * skalaPx - 100, 0), Math.max(0, kotak.width - 210));
        tip.style.left = `${kiri}px`;
        tip.style.top = `${Math.max(0, Math.min(py * skalaPx + (py > C ? 10 : -118), kotak.height - 110))}px`;
        tip.classList.add("tampil");
      };
      const sembunyi = () => tip.classList.remove("tampil");
      kel.addEventListener("pointerenter", tampil);
      kel.addEventListener("pointerleave", sembunyi);
      kel.addEventListener("focus", tampil);
      kel.addEventListener("blur", sembunyi);
      kel.addEventListener("click", () => adaData && opsi.saatPilih?.(v.kode));
      kel.addEventListener("keydown", (e) => {
        if ((e.key === "Enter" || e.key === " ") && adaData) { e.preventDefault(); opsi.saatPilih?.(v.kode); }
      });
      sudut += lebarSlot;
    }
    const a1 = sudut;
    el("path", { d: busur(R_BUSUR, a0 + lebarSlot * 0.12, a1 - lebarSlot * 0.12), fill: "none", stroke: w.brass,
      "stroke-opacity": 0.55, "stroke-width": 1 }, akar);
    // label kelompok melengkung mengikuti cincin; di belahan bawah dibalik agar tetap terbaca
    const tengahGrup = (a0 + a1) / 2;
    const bawah = Math.sin(tengahGrup) > 0.05;
    const idJalur = `${id}-${g.kode}`;
    const lebar = Math.PI * 0.9;
    el("path", { id: idJalur, d: busur(bawah ? R_LABEL + 8 : R_LABEL, tengahGrup - lebar / 2, tengahGrup + lebar / 2, !bawah),
      fill: "none" }, defs);
    const teks = el("text", { "text-anchor": "middle" }, labelGrup);
    const jalur = el("textPath", { href: `#${idJalur}`, startOffset: "50%" }, teks);
    jalur.textContent = g.nama.toUpperCase();
    sudut += lebarSlot * slotCelahGrup;
  }

  // Label skala di celah atas (latar dipotong agar tidak tertimpa garis lingkar)
  const skala = el("g", { class: "iris-kecil", ...huruf, "font-size": 8.5, fill: w.muted, "text-anchor": "middle", stroke: w.bg,
    "stroke-width": 3, "paint-order": "stroke" }, akar);
  for (const d of [30, 20, 10, 0, -10, -20, -30]) {
    const t = el("text", { x: C, y: C - (R_BASE + d * SKALA) + 3 }, skala);
    t.textContent = d === 0 ? "0" : `${d > 0 ? "+" : "−"}${Math.abs(d)}%`;
  }

  // Pupil
  el("circle", { cx: C, cy: C, r: R_PUPIL, fill: w.surface2, stroke: w.brass, "stroke-opacity": 0.5, "stroke-width": 1 }, akar);
  el("circle", { cx: C, cy: C, r: R_PUPIL - 7, fill: "none", stroke: w.brass, "stroke-opacity": 0.14, "stroke-width": 0.8,
    "stroke-dasharray": "1 3" }, akar);
  if (opsi.sinyalTinggi) {
    el("circle", { cx: C, cy: C, r: R_PUPIL + 6, fill: "none", stroke: w.kritis, "stroke-width": 1.2, class: "iris-pupil-denyut" }, akar);
  }
  const t0 = el("text", { x: C, y: C - 42, "text-anchor": "middle", ...huruf, "font-size": 8.5, "letter-spacing": 2.6, fill: w.brass }, akar);
  t0.textContent = "LINTAS AI";
  const angkaBesar = el("text", { x: C, y: C + 18, "text-anchor": "middle", "font-family": "Instrument Serif, serif",
    "font-size": 76, fill: w.ink }, akar);
  angkaBesar.textContent = opsi.diLuar === null || opsi.diLuar === undefined ? "–" : String(opsi.diLuar);
  const t1 = el("text", { class: "iris-kecil", x: C, y: C + 40, "text-anchor": "middle", ...huruf, "font-size": 8.5, "letter-spacing": 1.4, fill: w.muted }, akar);
  const menunggu = opsi.diLuar === null || opsi.diLuar === undefined;
  t1.textContent = menunggu ? "MENUNGGU DATA" : "DI LUAR POLA NORMAL";
  const t2 = el("text", { class: "iris-kecil", x: C, y: C + 53, "text-anchor": "middle", ...huruf, "font-size": 8.5, "letter-spacing": 1.4, fill: w.muted }, akar);
  t2.textContent = menunggu ? `${varian.length} VARIAN DIPANTAU` : `DARI ${varian.length} VARIAN`;
}

export function legendaIris() {
  return `<span><span class="kunci-pita" style="background:var(--up)"></span>Di atas baseline</span>
    <span><span class="kunci-pita" style="background:var(--down)"></span>Di bawah baseline</span>
    <span><span class="kunci-pita" style="background:var(--baseline)"></span>Selisih &lt;1%</span>
    <span><span class="kunci-titik" style="background:var(--critical)"></span>Sinyal prioritas</span>
    <span class="catatan">Batang terang = melewati ambang kelompok · skala linear, dipotong di ±30%</span>`;
}

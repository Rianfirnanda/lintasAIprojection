// Grafik pergerakan harga: aktual, baseline, proyeksi + interval, anomali, dan wilayah pembanding.
import { esc, rp, tgl, warna } from "./app.js";

const garisPenunjuk = {
  id: "garisPenunjuk",
  afterDatasetsDraw(chart) {
    const aktif = chart.tooltip?.getActiveElements?.() || [];
    if (!aktif.length) return;
    const x = aktif[0].element.x;
    const { top, bottom } = chart.chartArea;
    const ctx = chart.ctx;
    ctx.save();
    ctx.strokeStyle = warna("axis");
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, bottom);
    ctx.stroke();
    ctx.restore();
  },
};

/** Animasi grafik saat dibuat: garis tergambar dari kiri ke kanan (jumlah = banyak titik), batang tumbuh dari bawah.
 *  Mati (false) bila perangkat meminta gerak dikurangi. Saat disorot atau diubah ukurannya grafik tidak diulang. */
export function animasiGrafik(jumlah = 0, jenis = "garis", lama = 900) {
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return false;
  if (jenis === "batang" || !jumlah) return { duration: 700, easing: "easeOutQuart" };
  const jeda = lama / Math.max(1, jumlah);
  const yAwal = (ctx) => {
    const sebelum = ctx.index > 0 ? ctx.chart.getDatasetMeta(ctx.datasetIndex).data[ctx.index - 1] : null;
    const y = sebelum?.getProps(["y"], true).y;
    return Number.isFinite(y) ? y : ctx.chart.chartArea?.bottom ?? 0;
  };
  const tunda = (kunci) => (ctx) => {
    if (ctx.type !== "data" || ctx[kunci]) return 0;
    ctx[kunci] = true;
    return ctx.index * jeda;
  };
  return {
    x: { type: "number", easing: "linear", duration: jeda, from: NaN, delay: tunda("xMulai") },
    y: { type: "number", easing: "linear", duration: jeda, from: yAwal, delay: tunda("yMulai") },
  };
}

// Nama garis harga utama: Bengkulu Tengah, atau wilayah cadangan bila pasar Bengkulu Tengah belum mencatat varian ini.
export function namaAktual(seri) {
  const s = seri.sumber_seri;
  const wil = s?.pengganti ? String(s.wilayah || "wilayah cadangan") : "Bengkulu Tengah";
  return `${wil} (harga tercatat)`;
}

export function potongSeri(seri, hari) {
  if (!hari) return seri;
  const n = seri.tanggal.length;
  const mulai = Math.max(0, n - hari);
  const potong = (a) => a.slice(mulai);
  const pembanding = {};
  for (const [k, p] of Object.entries(seri.pembanding || {})) pembanding[k] = { ...p, nilai: potong(p.nilai) };
  return { ...seri, tanggal: potong(seri.tanggal), aktual: potong(seri.aktual), baseline: potong(seri.baseline),
           rata7: potong(seri.rata7), pembanding };
}

export function gambarGrafikHarga(canvas, seri, opsi = {}) {
  const dash = opsi.gaya === "dashboard";
  const tipe = opsi.tipe || "garis"; // "garis", "area", atau "batang"
  const tampilPembanding = dash ? false : (opsi.pembanding ?? true);
  const proy = opsi.horizon ? (seri.proyeksi || []).slice(0, opsi.horizon) : (seri.proyeksi || []);
  const tingkat = Math.round((opsi.tingkat ?? 0.8) * 100);
  const tanggalProyeksi = proy.map((p) => p.tanggal);
  const label = [...seri.tanggal, ...tanggalProyeksi];
  const n = seri.tanggal.length;
  const kosong = (k) => Array(k).fill(null);
  const idxAkhir = seri.aktual.map((v, i) => (v === null ? -1 : i)).filter((i) => i >= 0).pop();
  const nilaiAkhir = idxAkhir !== undefined ? seri.aktual[idxAkhir] : null;

  const proyeksi = kosong(label.length);
  const bawah = kosong(label.length);
  const atas = kosong(label.length);
  if (nilaiAkhir !== null && proy.length) {
    proyeksi[n - 1] = nilaiAkhir;
    bawah[n - 1] = nilaiAkhir;
    atas[n - 1] = nilaiAkhir;
    proy.forEach((p, i) => {
      proyeksi[n + i] = p.prediksi;
      bawah[n + i] = p.bawah;
      atas[n + i] = p.atas;
    });
  }
  const setAnomali = new Set(seri.anomali || []);
  const anomali = [...seri.tanggal.map((t, i) => (setAnomali.has(t) ? seri.aktual[i] : null)), ...kosong(tanggalProyeksi.length)];

  const c = {
    s1: warna("series-1"), s2: warna("series-2"), s3: warna("series-3"), s4: warna("series-4"),
    base: warna("baseline"), grid: warna("grid"), muted: warna("muted"), ink2: warna("ink-2"),
    surface: warna("surface"), kritis: warna("critical"),
  };
  const huruf = { family: warna("sans"), size: 11 };
  const garis = (lbl, data, warnaGaris, extra = {}) => ({
    label: lbl, data, borderColor: warnaGaris, backgroundColor: warnaGaris, borderWidth: 2, pointRadius: 0,
    pointHoverRadius: 4, tension: 0, spanGaps: true, borderCapStyle: "round", borderJoinStyle: "round", ...extra,
  });

  const datasets = [
    garis("Batas bawah rentang", bawah, "transparent", { borderWidth: 0, pointHoverRadius: 0, _interval: true }),
    garis(`Rentang perkiraan ${tingkat}%`, atas, "transparent", {
      borderWidth: 0, pointHoverRadius: 0, fill: "-1", backgroundColor: c.s2 + (dash ? "2e" : "22"), _interval: true,
    }),
    dash
      ? garis("Harga normal (nilai tengah 28 hari)", [...seri.baseline, ...kosong(tanggalProyeksi.length)], c.s1, { borderWidth: 1.6, borderDash: [5, 4] })
      : garis("Harga normal (nilai tengah 28 hari)", [...seri.baseline, ...kosong(tanggalProyeksi.length)], c.base, { borderWidth: 1.5 }),
    dash
      ? garis("Perkiraan", proyeksi, c.s2, { borderDash: [5, 4], borderWidth: 2, pointRadius: 2, pointBackgroundColor: c.s2 })
      : garis("Perkiraan", proyeksi, c.s2, { borderDash: [6, 4] }),
  ];
  const warnaPembanding = [c.s3, c.s4];
  if (tampilPembanding) {
    Object.values(seri.pembanding || {}).forEach((p, i) => {
      datasets.push(garis(p.nama, [...p.nilai, ...kosong(tanggalProyeksi.length)], warnaPembanding[i % 2], { borderWidth: 1.5 }));
    });
  }
  datasets.push(garis(dash ? "Harga tercatat" : namaAktual(seri), [...seri.aktual, ...kosong(tanggalProyeksi.length)], c.s1,
    dash ? { borderWidth: 2.4, pointRadius: n > 45 ? 0 : 3, pointBackgroundColor: c.s1 } : {}));
  if (tipe !== "garis") {
    const aktualDs = datasets[datasets.length - 1];
    const proyDs = datasets.find((d) => d.label === "Perkiraan");
    if (tipe === "area") {
      Object.assign(aktualDs, { fill: "origin", backgroundColor: c.s1 + "26", pointRadius: 0 });
      Object.assign(proyDs, { fill: "origin", backgroundColor: c.s2 + "1f" });
    } else {
      Object.assign(aktualDs, { type: "bar", backgroundColor: c.s1 + "cc", borderWidth: 0, borderRadius: 3, maxBarThickness: 18, order: 5 });
      Object.assign(proyDs, {
        type: "bar", data: proyeksi.map((v, i) => (i < n ? null : v)), backgroundColor: c.s2 + "99", borderWidth: 0,
        borderRadius: 3, maxBarThickness: 18, order: 5,
      });
    }
  }
  datasets.push({
    label: "Harga janggal", data: anomali, showLine: false, pointRadius: 5, pointHoverRadius: 7,
    pointBackgroundColor: c.kritis, pointBorderColor: c.surface, pointBorderWidth: 2, borderColor: c.kritis,
  });

  const chart = new window.Chart(canvas, {
    type: "line",
    data: { labels: label, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, normalized: true,
      animation: animasiGrafik(tipe === "batang" ? 0 : label.length, tipe === "batang" ? "batang" : "garis"),
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          usePointStyle: true,
          filter: (item) => item.raw !== null && !item.dataset._interval,
          callbacks: {
            title: (items) => {
              const t = items[0]?.label;
              return tgl(t) + (tanggalProyeksi.includes(t) ? " (perkiraan)" : "");
            },
            label: (item) => `${rp(item.raw)}  ${item.dataset.label}`,
            afterBody: (items) => {
              const i = items[0]?.dataIndex;
              if (i === undefined || i < n) return [];
              return [`Rentang ${tingkat}%: ${rp(bawah[i])} – ${rp(atas[i])}`];
            },
          },
        },
      },
      scales: {
        x: {
          grid: { display: false }, border: { color: c.grid },
          ticks: { color: c.muted, font: huruf, maxRotation: 0, autoSkipPadding: 24, callback(v) { return tgl(this.getLabelForValue(v)); } },
        },
        y: {
          grid: { color: c.grid }, border: { display: false }, beginAtZero: opsi.dariNol ?? dash,
          ticks: { color: c.muted, font: huruf, callback: (v) => (dash ? new Intl.NumberFormat("id-ID").format(v) : rp(v)) },
        },
      },
    },
    plugins: [garisPenunjuk],
  });
  if (opsi.interaktif !== false) pasangGeserPerbesar(chart);
  return chart;
}

export function legendaHarga(seri, tampilPembanding = true) {
  const item = [
    ['<span class="kunci-garis" style="border-color:var(--series-1)"></span>', esc(namaAktual(seri))],
    ['<span class="kunci-garis" style="border-color:var(--baseline)"></span>', "Harga normal (nilai tengah 28 hari)"],
    ['<span class="kunci-garis putus" style="border-color:var(--series-2)"></span>', "Perkiraan"],
    ['<span class="kunci-pita" style="background:color-mix(in srgb, var(--series-2) 18%, transparent)"></span>', "Rentang perkiraan 80%"],
    ['<span class="kunci-titik" style="background:var(--critical)"></span>', "Harga janggal"],
  ];
  if (tampilPembanding) {
    const w = ["var(--series-3)", "var(--series-4)"];
    Object.values(seri.pembanding || {}).forEach((p, i) => item.push([`<span class="kunci-garis" style="border-color:${w[i % 2]}"></span>`, `${esc(p.nama)} (pembanding)`]));
  }
  return item.map(([k, t]) => `<span>${k}${t}</span>`).join("");
}

export function legendaDashboard() {
  return [
    ['<span class="kunci-garis" style="border-color:var(--series-1)"></span>', "Harga tercatat"],
    ['<span class="kunci-garis putus" style="border-color:var(--series-1)"></span>', "Harga normal"],
    ['<span class="kunci-garis putus" style="border-color:var(--series-2)"></span>', "Perkiraan"],
    ['<span class="kunci-pita" style="background:color-mix(in srgb, var(--series-2) 22%, transparent)"></span>', "Rentang perkiraan"],
    ['<span class="kunci-titik" style="background:var(--critical)"></span>', "Harga janggal"],
  ].map(([k, t]) => `<span>${k}${t}</span>`).join("");
}

/* ---------- grafik interaktif: perbesar, perkecil, geser, dan kembali ke semua tanggal
 * Tombol kecil di pojok grafik. Seret grafik ke kiri/kanan untuk menggeser setelah diperbesar; Ctrl + gulir (atau cubit
 * di layar sentuh) juga memperbesar. Ketuk dua kali untuk kembali melihat semua tanggal. */
export function pasangGeserPerbesar(chart) {
  const kanvas = chart.canvas, wadah = kanvas.parentElement;
  if (!wadah) return;
  kanvas._lepasGeser?.();
  const n = chart.data.labels.length;
  if (n < 8) { wadah.querySelector(".alat-grafik")?.remove(); return; }
  let mulai = 0, akhir = n - 1;
  const terap = () => {
    chart.options.scales.x.min = mulai;
    chart.options.scales.x.max = akhir;
    chart.update("none");
    alat.querySelector("[data-semua]").disabled = mulai === 0 && akhir === n - 1;
  };
  const perbesar = (faktor, pusat = (mulai + akhir) / 2) => {
    const lebar = Math.max(6, Math.min(n - 1, Math.round((akhir - mulai) * faktor)));
    mulai = Math.round(pusat - lebar * ((pusat - mulai) / Math.max(1, akhir - mulai)));
    mulai = Math.max(0, Math.min(n - 1 - lebar, mulai));
    akhir = mulai + lebar;
    terap();
  };
  let alat = wadah.querySelector(".alat-grafik");
  if (!alat) {
    alat = document.createElement("div");
    alat.className = "alat-grafik";
    alat.innerHTML = `<button type="button" data-perbesar aria-label="Perbesar grafik" title="Perbesar">+</button>
      <button type="button" data-perkecil aria-label="Perkecil grafik" title="Perkecil">−</button>
      <button type="button" data-semua title="Tampilkan semua tanggal">Semua</button>`;
    wadah.append(alat);
  }
  const klikAlat = (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.hasAttribute("data-perbesar")) perbesar(0.6);
    else if (b.hasAttribute("data-perkecil")) perbesar(1 / 0.6);
    else { mulai = 0; akhir = n - 1; terap(); }
  };
  const pusatDari = (x) => {
    const s = chart.scales.x;
    return Math.max(0, Math.min(n - 1, s.getValueForPixel(x)));
  };
  const roda = (e) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    const r = kanvas.getBoundingClientRect();
    perbesar(e.deltaY < 0 ? 0.8 : 1.25, pusatDari(e.clientX - r.left));
  };
  let seret = null;
  const turun = (e) => {
    if (mulai === 0 && akhir === n - 1) return;
    seret = { x: e.clientX, mulai, akhir };
    kanvas.setPointerCapture?.(e.pointerId);
    kanvas.classList.add("digeser");
  };
  const gerak = (e) => {
    if (!seret) return;
    const s = chart.scales.x;
    const perTitik = (s.right - s.left) / Math.max(1, seret.akhir - seret.mulai);
    const geser = Math.round((seret.x - e.clientX) / perTitik);
    const lebar = seret.akhir - seret.mulai;
    mulai = Math.max(0, Math.min(n - 1 - lebar, seret.mulai + geser));
    akhir = mulai + lebar;
    terap();
  };
  const naik = () => { seret = null; kanvas.classList.remove("digeser"); };
  const ganda = () => { mulai = 0; akhir = n - 1; terap(); };
  alat.addEventListener("click", klikAlat);
  kanvas.addEventListener("wheel", roda, { passive: false });
  kanvas.addEventListener("pointerdown", turun);
  kanvas.addEventListener("pointermove", gerak);
  kanvas.addEventListener("pointerup", naik);
  kanvas.addEventListener("pointercancel", naik);
  kanvas.addEventListener("dblclick", ganda);
  kanvas._lepasGeser = () => {
    alat.removeEventListener("click", klikAlat);
    kanvas.removeEventListener("wheel", roda);
    kanvas.removeEventListener("pointerdown", turun);
    kanvas.removeEventListener("pointermove", gerak);
    kanvas.removeEventListener("pointerup", naik);
    kanvas.removeEventListener("pointercancel", naik);
    kanvas.removeEventListener("dblclick", ganda);
  };
  alat.querySelector("[data-semua]").disabled = true;
}

/** Grafik perbandingan beberapa varian: perubahan harga (%) sejak tanggal awal yang dipilih, supaya barang yang harganya
 *  jauh berbeda (mis. beras dan daging) bisa dibandingkan dalam satu grafik. */
export function gambarBanding(kanvas, daftarSeri, hari = 90) {
  const potong = daftarSeri.map((s) => potongSeri(s, hari));
  const semuaTanggal = [...new Set(potong.flatMap((s) => s.tanggal))].sort();
  const warnaSeri = ["series-1", "series-2", "series-3", "series-4"].map((k) => warna(k));
  const datasets = potong.map((s, i) => {
    const peta = new Map(s.tanggal.map((t, j) => [t, s.aktual[j]]));
    const awal = s.aktual.find((x) => x !== null && x !== undefined);
    return {
      label: s.nama, borderColor: warnaSeri[i % 4], backgroundColor: warnaSeri[i % 4], borderWidth: 2.2, pointRadius: 0, pointHoverRadius: 4,
      tension: 0, spanGaps: true, _harga: semuaTanggal.map((t) => peta.get(t) ?? null),
      data: semuaTanggal.map((t) => { const x = peta.get(t); return x === null || x === undefined || !awal ? null : ((x - awal) / awal) * 100; }),
    };
  });
  const huruf = { family: warna("sans"), size: 11 };
  return new window.Chart(kanvas, {
    type: "line",
    data: { labels: semuaTanggal, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, normalized: true, animation: animasiGrafik(semuaTanggal.length),
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: true, labels: { usePointStyle: true, boxWidth: 8, color: warna("ink-2"), font: huruf } },
        tooltip: {
          usePointStyle: true, filter: (item) => item.raw !== null,
          callbacks: {
            title: (items) => tgl(items[0]?.label),
            label: (item) => `${item.dataset.label}: ${rp(item.dataset._harga[item.dataIndex])} (${item.raw > 0 ? "+" : ""}${item.raw.toLocaleString("id-ID", { maximumFractionDigits: 1 })}%)`,
          },
        },
      },
      scales: {
        x: { grid: { display: false }, border: { color: warna("grid") },
          ticks: { color: warna("muted"), font: huruf, maxRotation: 0, autoSkipPadding: 24, callback(v) { return tgl(this.getLabelForValue(v)); } } },
        y: { grid: { color: warna("grid") }, border: { display: false },
          ticks: { color: warna("muted"), font: huruf, callback: (v) => `${v > 0 ? "+" : ""}${v.toLocaleString("id-ID")}%` } },
      },
    },
    plugins: [garisPenunjuk],
  });
}

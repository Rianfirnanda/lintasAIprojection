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
      borderWidth: 0, pointHoverRadius: 0, fill: "-1", backgroundColor: dash ? "rgba(128,138,152,0.24)" : c.s2 + "22", _interval: true,
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
      responsive: true, maintainAspectRatio: false, animation: false, normalized: true,
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
    ['<span class="kunci-pita" style="background:rgba(128,138,152,0.32)"></span>', "Rentang perkiraan"],
    ['<span class="kunci-titik" style="background:var(--critical)"></span>', "Harga janggal"],
  ].map(([k, t]) => `<span>${k}${t}</span>`).join("");
}

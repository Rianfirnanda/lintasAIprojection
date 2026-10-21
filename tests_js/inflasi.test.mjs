// Inflasi resmi BPS: sasaran nasional, angka utama (rilis lebih baru daripada tabel), dan layar Mode Videotron.
import assert from "node:assert/strict";
import test from "node:test";
import { sasaran, statusSasaran, angkaUtama } from "../site/assets/inflasi-inti.js";
import { susunTampilan } from "../site/assets/videotron-isi.js";

const IB = {
  periode: "2026-05", umum: { nama: "Umum", mtm: 0.86, ytd: 1.39, yoy: 3.01 },
  rilis: [{ periode: "2026-09", yoy: 3.38, mtm: 0.38, tanggal: "2026-10-01", url: "https://bengkulu.bps.go.id/id/x.html" },
    { periode: "2026-08", yoy: 3.99, mtm: 0.31, tanggal: "2026-09-01" }],
  wilayah_ihk: { periode: "2026-09", daftar: [{ nama: "Kab. Mukomuko", mtm: null, yoy: 4.39 }, { nama: "Kota Bengkulu", mtm: null, yoy: 3.05 },
    { nama: "Provinsi Bengkulu", mtm: null, yoy: 3.38 }] },
};

test("sasaran inflasi 2,5 ± 1% dan statusnya", () => {
  assert.equal(sasaran("2026-09").teks, "2,5 ± 1%");
  assert.equal(sasaran("2030-01"), null); // sasaran tahun itu belum ditetapkan
  assert.deepEqual(statusSasaran(3.38, "2026-09"), ["Dalam sasaran", "baik"]);
  assert.deepEqual(statusSasaran(3.99, "2026-08"), ["Di atas sasaran", "perhatian"]);
  assert.deepEqual(statusSasaran(-0.2, "2025-02"), ["Di bawah sasaran", "netral"]);
  assert.equal(statusSasaran(null, "2026-09"), null);
});

test("angka utama dari rilis resmi bila lebih baru daripada tabel", () => {
  assert.deepEqual(angkaUtama(IB), { periode: "2026-09", yoy: 3.38, mtm: 0.38, ytd: null, asal: "rilis", tanggal: "2026-10-01",
    url: "https://bengkulu.bps.go.id/id/x.html" });
  assert.deepEqual(angkaUtama({ ...IB, rilis: [] }), { periode: "2026-05", yoy: 3.01, mtm: 0.86, ytd: 1.39, asal: "tabel" });
});

test("Mode Videotron menampilkan inflasi resmi bila datanya ada", () => {
  const varian = [{ kode: "BRS03", nama: "Beras", satuan: "kg", harga_terakhir: 14000, perubahan: {} }];
  const tanpa = susunTampilan({ ringkasan: { varian } });
  assert.ok(!tanpa.some((t) => t.kunci === "inflasi"));
  const t = susunTampilan({ ringkasan: { varian, inflasi_bps: IB } }).find((x) => x.kunci === "inflasi");
  assert.equal(t.sub, "Provinsi Bengkulu, September 2026");
  assert.match(t.isi, /sebesar 3,38%, masih dalam sasaran nasional 2,5 ± 1%/);
  assert.match(t.isi, /Kota Bengkulu, setahun/);
  assert.match(t.isi, /vt-kpi-4/);
  assert.match(t.isi, /terbit 1 Oktober 2026/);
  assert.doesNotMatch(t.isi, /Provinsi Bengkulu, setahun|undefined|NaN|null/);
});

test("Tanya Takar menjawab pertanyaan inflasi dari angka BPS", async () => {
  const { jawab, konteksAi } = await import("../site/assets/tanya-mesin.js");
  const data = { ringkasan: { varian: [], inflasi_bps: { ...IB, makanan: { nama: "Makanan, Minuman, dan Tembakau", yoy: 6.07 },
    ntp: { periode: "2026-09", nilai: 206.79 } } } };
  const r = await jawab("berapa inflasi bulan ini?", data);
  assert.equal(r.niat, "inflasi");
  assert.match(r.baris[0], /^Inflasi setahun Provinsi Bengkulu September 2026 sebesar 3,38%, dan 0,38% dibanding bulan sebelumnya \(rilis BPS 1 Oktober 2026\)\. Angka ini masih dalam sasaran nasional 2,5/);
  assert.match(r.baris.join(" "), /makanan, minuman, dan tembakau 6,07% setahun \(Mei 2026/);
  assert.doesNotMatch(r.baris.join(" "), /petani/);
  assert.match((await jawab("NTP petani berapa?", data)).baris.join(" "), /Nilai tukar petani September 2026: 206,79/);
  assert.equal((await jawab("inflasi?", { ringkasan: { varian: [] } })).baris[0], "Angka inflasi resmi BPS belum tersedia di situs ini.");
  assert.match(konteksAi(data), /Inflasi resmi BPS Provinsi Bengkulu 2026-09: \+3,38% setahun/);
});

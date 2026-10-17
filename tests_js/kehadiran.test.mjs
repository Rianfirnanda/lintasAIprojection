// Kehadiran: status aktif/diam/tidak aktif, pembulatan lokasi per peran, dan urutan daftar untuk Administrator.
import assert from "node:assert/strict";
import test from "node:test";
import { bulatkanLokasi, statusKehadiran, berapaLama, susunBaris, hitung } from "../site/assets/kehadiran.js";

const KINI = Date.parse("2026-10-17T10:00:00+07:00");
const menitLalu = (m) => KINI - m * 60e3;

test("status mengikuti waktu terakhir aktif", () => {
  assert.equal(statusKehadiran({ status: "aktif", terakhir_aktif: menitLalu(3) }, KINI).kode, "aktif");
  assert.equal(statusKehadiran({ status: "aktif", terakhir_aktif: menitLalu(15) }, KINI).kode, "diam");
  assert.equal(statusKehadiran({ status: "diam", terakhir_aktif: menitLalu(2) }, KINI).kode, "diam");
  assert.equal(statusKehadiran({ status: "aktif", terakhir_aktif: menitLalu(45) }, KINI).kode, "tidak");
  assert.equal(statusKehadiran({ status: "keluar", terakhir_aktif: menitLalu(1) }, KINI).label, "Keluar");
  assert.equal(statusKehadiran(null, KINI).label, "Tidak aktif");
  // Timestamp Firestore (punya toMillis)
  assert.equal(statusKehadiran({ status: "aktif", terakhir_aktif: { toMillis: () => menitLalu(1) } }, KINI).kode, "aktif");
});

test("lokasi petugas tepat, peran lain dibulatkan sekitar 1 km", () => {
  const k = { latitude: -3.7212345, longitude: 102.4498765, accuracy: 12.4 };
  assert.deepEqual(bulatkanLokasi(k, "petugas"), { lat: -3.72123, lon: 102.44988, akurasi: 12, perkiraan: false });
  assert.deepEqual(bulatkanLokasi(k, "masyarakat"), { lat: -3.72, lon: 102.45, akurasi: 1100, perkiraan: true });
  assert.equal(bulatkanLokasi({ ...k, accuracy: 3000 }, "tpid").akurasi, 3000);
});

test("lama waktu dalam kalimat biasa", () => {
  assert.equal(berapaLama(0.4), "baru saja");
  assert.equal(berapaLama(12), "12 menit lalu");
  assert.equal(berapaLama(180), "3 jam lalu");
  assert.equal(berapaLama(3 * 1440), "3 hari lalu");
  assert.equal(berapaLama(Infinity), "belum pernah");
});

test("daftar admin: hanya akun aktif, yang aktif di atas, lokasi hanya bila izin 'ya'", () => {
  const akun = [
    { uid: "a", nama: "Ani", peran: "masyarakat", status: "aktif" },
    { uid: "b", nama: "Budi", peran: "petugas", status: "aktif" },
    { uid: "c", nama: "Cici", peran: "tpid", status: "aktif" },
    { uid: "d", nama: "Dodi", peran: null, status: "menunggu" },
  ];
  const L = { lat: -3.7, lon: 102.4, akurasi: 10, perkiraan: false };
  const hadir = [
    { uid: "a", status: "aktif", terakhir_aktif: menitLalu(40), izin_lokasi: "tidak", lokasi: L },
    { uid: "b", status: "aktif", terakhir_aktif: menitLalu(2), izin_lokasi: "ya", lokasi: L },
    { uid: "c", status: "diam", terakhir_aktif: menitLalu(5), izin_lokasi: "belum" },
  ];
  const baris = susunBaris(akun, hadir, KINI);
  assert.deepEqual(baris.map((b) => b.uid), ["b", "c", "a"]);
  assert.equal(baris.find((b) => b.uid === "a").lokasi, null);
  assert.deepEqual(hitung(baris), { aktif: 1, diam: 1, tidak: 1, lokasi: 1 });
});

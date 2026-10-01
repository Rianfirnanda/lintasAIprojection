import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  ambil, atur, bedaPengaturan, dariTampilan, keTampilan, periksa, periksaKolom, periksaRahasia, rapikan, salin, teksNilai, tulisPengaturan,
} from "../site/assets/pengaturan-inti.js";

const baca = (p) => JSON.parse(readFileSync(new URL(`../config/${p}`, import.meta.url), "utf-8"));
const skema = baca("skema_pengaturan.json");
const pengaturan = baca("pengaturan.json");
const kolom = (jalur) => skema.kolom.find((k) => k.jalur === jalur);

test("pengaturan yang berlaku sekarang sah menurut skema", () => {
  assert.deepEqual(periksa(pengaturan, skema), []);
});

test("setiap isian skema punya nilai bawaan di pengaturan.json dan label yang jelas", () => {
  for (const k of skema.kolom) {
    assert.ok(ambil(pengaturan, k.jalur).ada, `${k.jalur} tidak ada di pengaturan.json`);
    assert.ok(k.label && k.label.length > 3, `${k.jalur} tanpa label`);
    assert.ok(skema.kelompok.some((g) => g.kode === k.kelompok), `${k.jalur}: kelompok tidak dikenal`);
  }
});

test("nilai batas bawah dan atas diterima, di luar batas ditolak", () => {
  for (const k of skema.kolom.filter((x) => x.tipe === "bulat" || x.tipe === "desimal")) {
    assert.equal(periksaKolom(k, k.min), null, `${k.jalur} min`);
    assert.equal(periksaKolom(k, k.maks), null, `${k.jalur} maks`);
    assert.ok(periksaKolom(k, k.min - 1), `${k.jalur} di bawah min`);
    assert.ok(periksaKolom(k, k.maks + 1), `${k.jalur} di atas maks`);
    assert.ok(periksaKolom(k, "12"), `${k.jalur} teks`);
    assert.ok(periksaKolom(k, null), `${k.jalur} null`);
    assert.ok(periksaKolom(k, Number.NaN), `${k.jalur} NaN`);
  }
  assert.ok(periksaKolom(kolom("analisis.horizon_hari"), 14.5), "bilangan bulat");
});

test("jenis isian lain diperiksa", () => {
  assert.equal(periksaKolom(kolom("notifikasi.aktif"), true), null);
  assert.ok(periksaKolom(kolom("notifikasi.aktif"), "ya"));
  assert.equal(periksaKolom(kolom("ai.penyedia"), "gemini"), null);
  assert.ok(periksaKolom(kolom("ai.penyedia"), "openai"));
  assert.equal(periksaKolom(kolom("hari_pencatatan"), [0, 4]), null);
  assert.ok(periksaKolom(kolom("hari_pencatatan"), []), "minimal satu hari");
  assert.ok(periksaKolom(kolom("hari_pencatatan"), [7]));
  assert.ok(periksaKolom(kolom("hari_pencatatan"), [1, 1]));
  assert.equal(periksaKolom(kolom("ai.urutan_otomatis"), ["github_models", "gemini"]), null);
  assert.ok(periksaKolom(kolom("ai.urutan_otomatis"), []));
  assert.ok(periksaKolom(kolom("ai.urutan_otomatis"), ["gemini", "gemini"]));
  assert.equal(periksaKolom(kolom("ai.model_gemini"), "gemini-flash-latest"), null);
  assert.ok(periksaKolom(kolom("ai.model_gemini"), "model dengan spasi"));
  assert.ok(periksaKolom(kolom("ai.model_gemini"), ""));
  assert.equal(periksaKolom(kolom("layanan.url_survei_eksternal"), ""), null);
  assert.equal(periksaKolom(kolom("layanan.url_survei_eksternal"), "https://contoh.go.id/survei"), null);
  assert.ok(periksaKolom(kolom("layanan.url_survei_eksternal"), "javascript:alert(1)"));
  assert.ok(periksaKolom(kolom("layanan.url_survei_eksternal"), "https://a b"));
});

test("aturan silang dan isian yang hilang dilaporkan", () => {
  const p = salin(pengaturan);
  atur(p, "sinyal.rasio_volatilitas_batas.0", 1);
  atur(p, "sinyal.rasio_volatilitas_batas.1", 1);
  assert.deepEqual(periksa(p, skema).map((m) => m.jalur), ["sinyal.rasio_volatilitas_batas.1"]);
  const q = salin(pengaturan);
  atur(q, "target_kinerja.cakupan_interval_min_persen", 96);
  assert.deepEqual(periksa(q, skema).map((m) => m.jalur), ["target_kinerja.cakupan_interval_maks_persen"]);
  const r = salin(pengaturan);
  delete r.analisis.horizon_hari;
  assert.match(periksa(r, skema)[0].pesan, /belum diisi/);
});

test("ambil dan atur bekerja pada objek dan larik", () => {
  const d = { a: { b: [1, { c: 2 }] } };
  assert.deepEqual(ambil(d, "a.b.1.c"), { ada: true, nilai: 2 });
  assert.equal(ambil(d, "a.b.5").ada, false);
  assert.equal(ambil(d, "a.x").ada, false);
  atur(d, "a.b.0", 9);
  atur(d, "a.baru.dalam", true);
  assert.deepEqual(d, { a: { b: [9, { c: 2 }], baru: { dalam: true } } });
});

test("rapikan: hasil bisa dibaca kembali, stabil, dan bentuknya mengikuti berkas yang ada", () => {
  const teks = rapikan(pengaturan);
  assert.deepEqual(JSON.parse(teks), pengaturan);
  assert.equal(rapikan(JSON.parse(teks)), teks);
  assert.match(teks, /"jendela_hari_raya": \{"sebelum": 14, "sesudah": 3\}/);
  assert.match(teks, /"hari_pencatatan": \[0, 1, 2, 3, 4\]/);
  assert.match(teks, /"kolom_terlarang": \["nama_pedagang"/);
  assert.match(teks, /^\{\n  "zona_waktu": "Asia\/Jakarta",/);
  assert.ok(tulisPengaturan(pengaturan).endsWith("}\n"));
  assert.equal(rapikan({}), "{}");
  assert.equal(rapikan({ a: [] }), '{\n  "a": []\n}');
  assert.deepEqual(JSON.parse(rapikan({ x: [{ y: 1 }, { y: 2 }] })), { x: [{ y: 1 }, { y: 2 }] });
});

test("bedaPengaturan hanya memuat isian skema yang berubah", () => {
  const p = salin(pengaturan);
  atur(p, "jam_batas_tepat_waktu", 15);
  atur(p, "notifikasi.jenis", ["drift"]);
  atur(p, "zona_waktu", "UTC"); // bukan isian skema
  const beda = bedaPengaturan(pengaturan, p, skema);
  assert.deepEqual(beda.map((b) => b.jalur).sort(), ["jam_batas_tepat_waktu", "notifikasi.jenis"]);
  const jam = beda.find((b) => b.jalur === "jam_batas_tepat_waktu");
  assert.equal(`${teksNilai(jam.kolom, jam.dari)} -> ${teksNilai(jam.kolom, jam.ke)}`, "14 WIB -> 15 WIB");
});

test("tampilan angka: persen, koma desimal, dan nilai kosong", () => {
  const k = kolom("analisis.tingkat_interval");
  assert.equal(keTampilan(k, 0.9), "90");
  assert.equal(dariTampilan(k, "90"), 0.9);
  assert.equal(dariTampilan(k, "57"), 0.57);
  assert.equal(dariTampilan(kolom("sinyal.z_ambang"), "3,5"), 3.5);
  assert.equal(dariTampilan(kolom("sinyal.z_ambang"), ""), null);
  assert.equal(dariTampilan(kolom("sinyal.z_ambang"), "abc"), null);
  assert.equal(teksNilai(kolom("notifikasi.aktif"), false), "mati");
  assert.equal(teksNilai(kolom("ai.penyedia"), "anthropic"), "Claude (berbayar)");
  assert.equal(teksNilai(kolom("hari_pencatatan"), [0, 1]), "Senin, Selasa");
});

test("bentuk kunci rahasia diperiksa dengan wajar", () => {
  const r = (nama) => skema.rahasia.find((x) => x.nama === nama);
  assert.equal(periksaRahasia(r("GEMINI_API_KEY"), "AIzaSyDaJ1234567890abcdefghijklmnopqrs"), null);
  assert.ok(periksaRahasia(r("GEMINI_API_KEY"), "pendek"));
  assert.ok(periksaRahasia(r("GEMINI_API_KEY"), "ada spasi di dalam kunci yang panjang sekali"));
  assert.equal(periksaRahasia(r("TELEGRAM_BOT_TOKEN"), "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"), null);
  assert.ok(periksaRahasia(r("TELEGRAM_BOT_TOKEN"), "tokensalah"));
  assert.equal(periksaRahasia(r("TELEGRAM_CHAT_ID"), "-1001234567890"), null);
  assert.equal(periksaRahasia(r("SMTP_PORT"), "465"), null);
  assert.ok(periksaRahasia(r("SMTP_PORT"), "70000"));
  assert.equal(periksaRahasia(r("EMAIL_KE"), "a@bps.go.id, b@bps.go.id"), null);
  assert.ok(periksaRahasia(r("EMAIL_KE"), "bukan-email"));
  assert.ok(periksaRahasia(r("SMTP_HOST"), "https://smtp.gmail.com"));
  assert.equal(periksaRahasia(r("SMTP_HOST"), "smtp.gmail.com"), null);
  assert.equal(periksaRahasia(r("GEMINI_API_KEY"), ""), "belum diisi");
});

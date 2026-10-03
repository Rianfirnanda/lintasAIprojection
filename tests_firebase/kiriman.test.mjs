// Uji aturan Firestore untuk pekerjaan harian lewat situs: harga, cek data, tindak lanjut, persetujuan model,
// pengaturan, kunci rahasia, permintaan jalankan, dan status.
import { readFileSync } from "node:fs";
import { after, before, beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { assertFails, assertSucceeds, initializeTestEnvironment } from "@firebase/rules-unit-testing";
import {
  addDoc, collection, deleteDoc, doc, getDoc, getDocs, query, serverTimestamp, setDoc, updateDoc, where, writeBatch,
} from "firebase/firestore";

const aturan = readFileSync(new URL("../firestore.rules", import.meta.url), "utf8");
let env;

before(async () => {
  env = await initializeTestEnvironment({ projectId: "demo-lbp", firestore: { rules: aturan } });
});
after(async () => { await env?.cleanup(); });
beforeEach(async () => { await env.clearFirestore(); });

const db = (uid) => env.authenticatedContext(uid, { email: `${uid}@contoh.go.id`, email_verified: true }).firestore();
async function akun(uid, peran, status = "aktif", halaman = null) {
  await env.withSecurityRulesDisabled(async (c) => {
    await setDoc(doc(c.firestore(), "lbp_pengguna", uid), { email: `${uid}@contoh.go.id`, nama: uid, status, peran, halaman });
  });
}
async function isiLangsung(jalur, id, data) {
  await env.withSecurityRulesDisabled(async (c) => { await setDoc(doc(c.firestore(), jalur, id), data); });
}

const harga = (uid, id, tambahan = {}) => ({
  tanggal: "2026-10-01", kode_pasar: "PSR01", kode_varian: "CMR01", harga: 55000, satuan: "kg", kode_sumber: "PSR-ENUM",
  petugas: "PTG01", responden: "R1", id_klien: id, waktu_input: "2026-10-01T08:00:00+07:00", catatan: "",
  oleh_uid: uid, oleh_email: `${uid}@contoh.go.id`, diterima: serverTimestamp(), diperbarui: serverTimestamp(), ...tambahan,
});

test("petugas aktif bisa mengirim harga, dan hanya melihat kirimannya sendiri", async () => {
  await akun("ptg", "petugas");
  await akun("ptg2", "petugas");
  const d = db("ptg");
  await assertSucceeds(setDoc(doc(d, "lbp_harga", "k1"), harga("ptg", "k1")));
  await assertSucceeds(getDocs(query(collection(d, "lbp_harga"), where("oleh_uid", "==", "ptg"))));
  await assertFails(getDocs(collection(d, "lbp_harga")));
  await assertFails(getDoc(doc(db("ptg2"), "lbp_harga", "k1")));
  // Tidak bisa diubah atau dihapus setelah terkirim.
  await assertFails(updateDoc(doc(d, "lbp_harga", "k1"), { harga: 1 }));
  await assertFails(deleteDoc(doc(d, "lbp_harga", "k1")));
});

test("kiriman harga ditolak bila isinya tidak wajar atau memalsukan pengirim", async () => {
  await akun("ptg", "petugas");
  const d = db("ptg");
  const coba = (id, tambahan) => assertFails(setDoc(doc(d, "lbp_harga", id), harga("ptg", id, tambahan)));
  await coba("a1", { harga: -5 });
  await coba("a2", { harga: "55000" });
  await coba("a3", { tanggal: "01/10/2026" });
  await coba("a4", { oleh_uid: "orang-lain" });
  await coba("a5", { oleh_email: "palsu@contoh.go.id" });
  await coba("a6", { id_klien: "lain" });
  await coba("a7", { nik: "1234" });
  await coba("a8", { catatan: "x".repeat(301) });
  await coba("a9", { kode_varian: "" });
});

test("akun menunggu, nonaktif, masyarakat, atau TPID tidak bisa mengirim harga", async () => {
  await akun("m", "petugas", "menunggu");
  await akun("n", "petugas", "nonaktif");
  await akun("pub", "masyarakat");
  await akun("tp", "tpid");
  for (const uid of ["m", "n", "pub", "tp"]) {
    await assertFails(setDoc(doc(db(uid), "lbp_harga", `x-${uid}`), harga(uid, `x-${uid}`)));
  }
  await assertFails(setDoc(doc(env.unauthenticatedContext().firestore(), "lbp_harga", "t"), harga("t", "t")));
});

test("izin halaman yang diatur admin menggantikan bawaan peran", async () => {
  await akun("tp", "tpid", "aktif", ["index.html", "input.html"]);
  await akun("ptg", "petugas", "aktif", ["index.html", "harga.html"]);
  await assertSucceeds(setDoc(doc(db("tp"), "lbp_harga", "a"), harga("tp", "a")));
  await assertFails(setDoc(doc(db("ptg"), "lbp_harga", "b"), harga("ptg", "b")));
});

test("operator bisa mengunggah banyak harga sekaligus dan membaca semua kiriman", async () => {
  await akun("op", "operator");
  const d = db("op");
  const b = writeBatch(d);
  for (let i = 0; i < 120; i++) b.set(doc(d, "lbp_harga", `u${i}`), harga("op", `u${i}`, { berkas: "harga_oktober.csv" }));
  await assertSucceeds(b.commit());
  const semua = await assertSucceeds(getDocs(collection(d, "lbp_harga")));
  assert.equal(semua.size, 120);
});

test("keputusan cek data hanya untuk operator dan analis, dengan isi yang sah", async () => {
  await akun("op", "operator");
  await akun("ptg", "petugas");
  const kep = (uid, tambahan = {}) => ({ id_observasi: "OBS1", keputusan: "terima", alasan: "sudah dicek", validator: "Op",
    tanggal_validasi: "2026-10-02", oleh_uid: uid, diperbarui: serverTimestamp(), ...tambahan });
  await assertSucceeds(setDoc(doc(db("op"), "lbp_validasi", "OBS1"), kep("op")));
  await assertSucceeds(setDoc(doc(db("op"), "lbp_validasi", "OBS1"), kep("op", { keputusan: "tolak" })));
  await assertFails(setDoc(doc(db("op"), "lbp_validasi", "OBS1"), kep("op", { keputusan: "mungkin" })));
  await assertFails(setDoc(doc(db("op"), "lbp_validasi", "OBS2"), kep("op")));
  await assertFails(setDoc(doc(db("ptg"), "lbp_validasi", "OBS1"), kep("ptg")));
});

test("tindak lanjut peringatan untuk analis dan TPID, riwayat tidak bisa diubah", async () => {
  await akun("tp", "tpid");
  await akun("op", "operator");
  const tl = (uid, tambahan = {}) => ({ id_sinyal: "SIG-1", status: "terverifikasi", catatan: "cek pasar", petugas: "TPID",
    tanggal: "2026-10-02", kode_varian: "", tanggal_kejadian: "", oleh_uid: uid, diperbarui: serverTimestamp(), ...tambahan });
  const ref = await assertSucceeds(addDoc(collection(db("tp"), "lbp_tindak_lanjut"), tl("tp")));
  await assertFails(updateDoc(doc(db("tp"), "lbp_tindak_lanjut", ref.id), { status: "selesai" }));
  await assertFails(addDoc(collection(db("tp"), "lbp_tindak_lanjut"), tl("tp", { status: "anomali_terlewat" })));
  await assertSucceeds(addDoc(collection(db("tp"), "lbp_tindak_lanjut"), tl("tp", { status: "anomali_terlewat", id_sinyal: "", kode_varian: "CMR01" })));
  await assertFails(addDoc(collection(db("op"), "lbp_tindak_lanjut"), tl("op")));
});

test("persetujuan model hanya untuk analis dan admin", async () => {
  await akun("an", "analis");
  await akun("tp", "tpid");
  const s = (uid) => ({ kode_varian: "CMR01", model: "ets", keputusan: "setuju", penyetuju: "Analis", tanggal: "2026-10-02",
    catatan: "", oleh_uid: uid, diperbarui: serverTimestamp() });
  await assertSucceeds(addDoc(collection(db("an"), "lbp_persetujuan_model"), s("an")));
  await assertFails(addDoc(collection(db("tp"), "lbp_persetujuan_model"), s("tp")));
});

test("pengaturan: semua akun aktif boleh membaca, hanya admin yang menyimpan dengan versi berurutan", async () => {
  await akun("adm", "admin");
  await akun("an", "analis");
  const isi = (versi, email = "adm@contoh.go.id") => ({ isi: { ai: { penyedia: "gemini" } }, versi, diubah_oleh: email,
    diubah_pada: serverTimestamp(), ringkasan: "uji" });
  const ref = doc(db("adm"), "lbp_pengaturan", "utama");
  await assertFails(setDoc(ref, isi(2)));
  await assertSucceeds(setDoc(ref, isi(1)));
  await assertFails(setDoc(ref, isi(1)));
  await assertSucceeds(setDoc(ref, isi(2)));
  await assertFails(setDoc(ref, isi(3, "orang@contoh.go.id")));
  await assertFails(setDoc(doc(db("an"), "lbp_pengaturan", "utama"), isi(3, "an@contoh.go.id")));
  await assertSucceeds(getDoc(doc(db("an"), "lbp_pengaturan", "utama")));
  await assertFails(setDoc(doc(db("adm"), "lbp_pengaturan", "lain"), isi(1)));
});

test("kunci rahasia: admin menulis, tidak ada yang bisa membaca nilainya", async () => {
  await akun("adm", "admin");
  await akun("an", "analis");
  const d = db("adm");
  const b = writeBatch(d);
  b.set(doc(d, "lbp_rahasia", "GEMINI_API_KEY"), { nilai: "rahasia-123", diperbarui: serverTimestamp(), oleh_uid: "adm" });
  b.set(doc(d, "lbp_rahasia_status", "GEMINI_API_KEY"), { diperbarui: serverTimestamp(), oleh_uid: "adm", oleh_email: "adm@contoh.go.id" });
  await assertSucceeds(b.commit());
  // Kunci AI boleh dibaca Administrator (AI jalan di browser admin); kunci lain dan pengguna lain tetap tidak.
  await assertSucceeds(getDoc(doc(d, "lbp_rahasia", "GEMINI_API_KEY")));
  await assertFails(getDoc(doc(db("an"), "lbp_rahasia", "GEMINI_API_KEY")));
  await isiLangsung("lbp_rahasia", "SMTP_PASSWORD", { nilai: "sandi" });
  await assertFails(getDoc(doc(d, "lbp_rahasia", "SMTP_PASSWORD")));
  await assertFails(getDocs(collection(d, "lbp_rahasia")));
  await assertSucceeds(getDocs(collection(d, "lbp_rahasia_status")));
  await assertFails(getDocs(collection(db("an"), "lbp_rahasia_status")));
  await assertFails(setDoc(doc(db("an"), "lbp_rahasia", "GEMINI_API_KEY"), { nilai: "x", diperbarui: serverTimestamp(), oleh_uid: "an" }));
  // Kunci Firebase dan nama asing tidak bisa diisi dari situs.
  await assertFails(setDoc(doc(d, "lbp_rahasia", "FIREBASE_SERVICE_ACCOUNT"), { nilai: "x", diperbarui: serverTimestamp(), oleh_uid: "adm" }));
  await assertFails(setDoc(doc(d, "lbp_rahasia", "GITHUB_TOKEN"), { nilai: "x", diperbarui: serverTimestamp(), oleh_uid: "adm" }));
  await assertSucceeds(deleteDoc(doc(d, "lbp_rahasia", "GEMINI_API_KEY")));
});

test("daftar kunci di aturan sama dengan skema pengaturan (selain kunci Firebase)", () => {
  const skema = JSON.parse(readFileSync(new URL("../config/skema_pengaturan.json", import.meta.url), "utf8"));
  const harap = skema.rahasia.map((r) => r.nama).filter((n) => !n.startsWith("FIREBASE_")).sort();
  const blok = aturan.match(/function namaRahasiaSah\(n\) \{([\s\S]*?)\}/)[1];
  const diAturan = [...blok.matchAll(/'([A-Z_]+)'/g)].map((m) => m[1]).sort();
  assert.deepEqual(diAturan, harap);
});

test("permintaan jalankan hanya dari admin, selalu berstatus menunggu, dan status bisa dibaca akun aktif", async () => {
  await akun("adm", "admin");
  await akun("an", "analis");
  const p = (tambahan = {}) => ({ jenis: "perbarui", masukan: { demo: "otomatis" }, status: "menunggu",
    diminta_oleh: "adm@contoh.go.id", diminta_pada: serverTimestamp(), ...tambahan });
  await assertSucceeds(setDoc(doc(db("adm"), "lbp_perintah", "perbarui"), p()));
  await assertFails(setDoc(doc(db("adm"), "lbp_perintah", "perbarui"), p({ status: "selesai" })));
  await assertFails(setDoc(doc(db("adm"), "lbp_perintah", "hapus_semua"), p({ jenis: "hapus_semua" })));
  await assertFails(setDoc(doc(db("an"), "lbp_perintah", "perbarui"), p({ diminta_oleh: "an@contoh.go.id" })));
  await isiLangsung("lbp_status", "pipeline", { hasil: "success" });
  await assertSucceeds(getDoc(doc(db("an"), "lbp_status", "pipeline")));
  await assertFails(setDoc(doc(db("adm"), "lbp_status", "pipeline"), { hasil: "palsu" }));
  await assertFails(getDoc(doc(env.unauthenticatedContext().firestore(), "lbp_status", "pipeline")));
});

test("data dashboard di lbp_data hanya bisa dibaca akun yang sudah disetujui, dan tidak bisa ditulis dari situs", async () => {
  await akun("adm", "admin");
  await akun("ptg", "petugas");
  await akun("m", "petugas", "menunggu");
  await isiLangsung("lbp_data", "ringkasan.json", { nama: "ringkasan.json", isi: "{}", bagian: 1 });
  await assertSucceeds(getDoc(doc(db("ptg"), "lbp_data", "ringkasan.json")));
  await assertSucceeds(getDocs(collection(db("ptg"), "lbp_data")));
  await assertFails(getDoc(doc(db("m"), "lbp_data", "ringkasan.json")));
  await assertFails(getDoc(doc(env.unauthenticatedContext().firestore(), "lbp_data", "ringkasan.json")));
  await assertFails(setDoc(doc(db("adm"), "lbp_data", "ringkasan.json"), { isi: "palsu" }));
});


test("hasil dan log AI dari browser: hanya pengelola sistem yang menulis, sesuai bentuknya", async () => {
  await akun("adm", "admin");
  await akun("an", "analis");
  await akun("ptg", "petugas");
  const k = (uid, tambahan = {}) => ({ permintaan: { komoditas: "cabai" }, penyedia: "gemini", model: "m", pencarian_web: "Tavily, 3 hasil",
    punya_pencarian_web: true, penyedia_dilewati: [], url_pencarian: [], hasil: "{}", oleh_uid: uid, oleh_email: `${uid}@contoh.go.id`,
    diperbarui: serverTimestamp(), ...tambahan });
  await assertSucceeds(addDoc(collection(db("adm"), "lbp_kandidat_ai"), k("adm")));
  await assertFails(addDoc(collection(db("an"), "lbp_kandidat_ai"), k("an")));
  await assertFails(addDoc(collection(db("adm"), "lbp_kandidat_ai"), k("adm", { lain: 1 })));
  const l = (uid, tambahan = {}) => ({ sumber: "situs", komoditas: "cabai", periode: "Okt", langkah: [{ teks: "a", jenis: "info" }],
    hasil: "berhasil", penyedia: "gemini", model: "m", jumlah_kandidat: 3, pencarian_web: "", oleh_uid: uid,
    oleh_email: `${uid}@contoh.go.id`, diperbarui: serverTimestamp(), ...tambahan });
  await assertSucceeds(addDoc(collection(db("adm"), "lbp_log_ai"), l("adm")));
  await assertFails(addDoc(collection(db("adm"), "lbp_log_ai"), l("adm", { sumber: "harian" })));
  await assertFails(addDoc(collection(db("an"), "lbp_log_ai"), l("an")));
  await assertSucceeds(getDocs(collection(db("an"), "lbp_log_ai")));
  await assertFails(getDocs(collection(db("ptg"), "lbp_log_ai")));
});

test("analis dan operator bisa menerima atau menolak kandidat sumber AI; tolak wajib beralasan", async () => {
  await akun("an", "analis");
  await akun("op", "operator");
  await akun("ptg", "petugas");
  await akun("tp", "tpid");
  const id = "0123456789ab";
  const k = (uid, tambahan = {}) => ({ id_kandidat: id, keputusan: "terima", alasan: "", penilai: "Analis", tanggal: "2026-10-03",
    url: "https://contoh.go.id/harga", nama_sumber: "Disperindag", pencarian: "2026-10-02T09:00:00+07:00",
    oleh_uid: uid, diperbarui: serverTimestamp(), ...tambahan });
  await assertSucceeds(setDoc(doc(db("an"), "lbp_keputusan_sumber", id), k("an")));
  // keputusan bisa diubah (terbaru yang berlaku), tetapi menolak tanpa alasan ditolak aturan
  await assertFails(setDoc(doc(db("op"), "lbp_keputusan_sumber", id), k("op", { keputusan: "tolak" })));
  await assertSucceeds(setDoc(doc(db("op"), "lbp_keputusan_sumber", id), k("op", { keputusan: "tolak", alasan: "salah wilayah" })));
  await assertFails(setDoc(doc(db("an"), "lbp_keputusan_sumber", id), k("an", { keputusan: "mungkin" })));
  await assertFails(setDoc(doc(db("an"), "lbp_keputusan_sumber", "id-asal"), k("an", { id_kandidat: "id-asal" })));
  await assertFails(setDoc(doc(db("an"), "lbp_keputusan_sumber", id), k("an", { lain: 1 })));
  await assertFails(setDoc(doc(db("an"), "lbp_keputusan_sumber", id), k("op")));  // memalsukan penilai
  await assertFails(setDoc(doc(db("ptg"), "lbp_keputusan_sumber", id), k("ptg")));
  await assertFails(setDoc(doc(db("tp"), "lbp_keputusan_sumber", id), k("tp")));
  await assertSucceeds(getDocs(collection(db("an"), "lbp_keputusan_sumber")));
  await assertFails(getDocs(collection(db("ptg"), "lbp_keputusan_sumber")));
});

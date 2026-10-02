// Uji aturan Firestore untuk kebijakan TPID, rapat, keputusan rekomendasi, kunjungan pedagang, dan catatan pemakaian.
import { readFileSync } from "node:fs";
import { after, before, beforeEach, test } from "node:test";
import { assertFails, assertSucceeds, initializeTestEnvironment } from "@firebase/rules-unit-testing";
import { addDoc, collection, doc, getDocs, query, serverTimestamp, setDoc, updateDoc, where } from "firebase/firestore";

const aturan = readFileSync(new URL("../firestore.rules", import.meta.url), "utf8");
let env;
before(async () => { env = await initializeTestEnvironment({ projectId: "demo-lbp", firestore: { rules: aturan } }); });
after(async () => { await env?.cleanup(); });
beforeEach(async () => { await env.clearFirestore(); });

const db = (uid) => env.authenticatedContext(uid, { email: `${uid}@contoh.go.id`, email_verified: true }).firestore();
const akun = (uid, peran, status = "aktif", halaman = null) => env.withSecurityRulesDisabled(async (c) => {
  await setDoc(doc(c.firestore(), "lbp_pengguna", uid), { email: `${uid}@contoh.go.id`, nama: uid, status, peran, halaman });
});
const kebijakan = (uid, lain = {}) => ({ tanggal_mulai: "2026-10-01", tanggal_selesai: "", jenis: "operasi_pasar", kode_varian: ["CRW02"],
  tujuan: "menurunkan_harga", uraian: "Pasar murah", id_rekomendasi: "", pencatat: "TPID", oleh_uid: uid, diperbarui: serverTimestamp(), ...lain });
const rapat = (uid, lain = {}) => ({ tanggal: "2026-10-01", jenis: "rapat_koordinasi", agenda: "Cabai", keputusan: "Pasar murah",
  jumlah_sinyal: 2, peserta: "BPS, Disdag", tautan_notulen: "", pencatat: "TPID", oleh_uid: uid, diperbarui: serverTimestamp(), ...lain });
const kunjungan = (uid, lain = {}) => ({ tanggal: "2026-10-01", kode_pasar: "PSR01", responden: "R9", status: "menolak",
  alasan: "takut_pajak", petugas: "PTG01", waktu_input: "", oleh_uid: uid, diperbarui: serverTimestamp(), ...lain });

test("TPID dan analis mencatat kebijakan dan rapat; peran lain tidak", async () => {
  await akun("tp", "tpid");
  await akun("an", "analis");
  await akun("ptg", "petugas");
  await akun("pub", "masyarakat");
  await assertSucceeds(addDoc(collection(db("tp"), "lbp_kebijakan"), kebijakan("tp")));
  await assertSucceeds(addDoc(collection(db("an"), "lbp_rapat"), rapat("an")));
  await assertSucceeds(getDocs(collection(db("tp"), "lbp_kebijakan")));
  await assertFails(addDoc(collection(db("ptg"), "lbp_kebijakan"), kebijakan("ptg")));
  await assertFails(addDoc(collection(db("pub"), "lbp_rapat"), rapat("pub")));
  await assertFails(getDocs(collection(db("ptg"), "lbp_rapat")));
});

test("isian kebijakan dan rapat diperiksa", async () => {
  await akun("tp", "tpid");
  const k = (lain) => assertFails(addDoc(collection(db("tp"), "lbp_kebijakan"), kebijakan("tp", lain)));
  await k({ jenis: "bagi_bagi" });
  await k({ tujuan: "naikkan" });
  await k({ kode_varian: [] });
  await k({ kode_varian: "CRW02" });
  await k({ tanggal_mulai: "1/10/2026" });
  await k({ oleh_uid: "lain" });
  const r = (lain) => assertFails(addDoc(collection(db("tp"), "lbp_rapat"), rapat("tp", lain)));
  await r({ jumlah_sinyal: "2" });
  await r({ tautan_notulen: "javascript:alert(1)" });
  await r({ jenis: "arisan" });
  await assertSucceeds(addDoc(collection(db("tp"), "lbp_rapat"), rapat("tp", { tautan_notulen: "https://drive.google.com/x" })));
});

test("keputusan rekomendasi: ID sesuai, keputusan setuju/tolak, bisa diubah", async () => {
  await akun("tp", "tpid");
  await akun("op", "operator");
  const isi = (lain = {}) => ({ id_rekomendasi: "R-abc", keputusan: "setuju", catatan: "", penyetuju: "Kepala", tanggal: "2026-10-01",
    oleh_uid: "tp", diperbarui: serverTimestamp(), ...lain });
  await assertSucceeds(setDoc(doc(db("tp"), "lbp_keputusan_rekomendasi", "R-abc"), isi()));
  await assertSucceeds(setDoc(doc(db("tp"), "lbp_keputusan_rekomendasi", "R-abc"), isi({ keputusan: "tolak" })));
  await assertFails(setDoc(doc(db("tp"), "lbp_keputusan_rekomendasi", "R-lain"), isi()));
  await assertFails(setDoc(doc(db("tp"), "lbp_keputusan_rekomendasi", "R-abc"), isi({ keputusan: "mungkin" })));
  await assertFails(setDoc(doc(db("op"), "lbp_keputusan_rekomendasi", "R-abc"), isi({ oleh_uid: "op" })));
});

test("petugas mencatat kunjungan yang gagal dan hanya melihat miliknya", async () => {
  await akun("ptg", "petugas");
  await akun("ptg2", "petugas");
  await akun("op", "operator");
  await assertSucceeds(setDoc(doc(db("ptg"), "lbp_kunjungan", "v1"), kunjungan("ptg")));
  await assertFails(setDoc(doc(db("ptg"), "lbp_kunjungan", "v2"), kunjungan("ptg", { status: "berhasil" })));
  await assertFails(setDoc(doc(db("ptg"), "lbp_kunjungan", "v3"), kunjungan("ptg", { nama_pedagang: "Budi" })));
  await assertFails(updateDoc(doc(db("ptg"), "lbp_kunjungan", "v1"), { status: "tutup" }));
  await assertSucceeds(getDocs(query(collection(db("ptg"), "lbp_kunjungan"), where("oleh_uid", "==", "ptg"))));
  await assertFails(getDocs(collection(db("ptg2"), "lbp_kunjungan")));
  await assertSucceeds(getDocs(collection(db("op"), "lbp_kunjungan")));
});

test("pemilik akun boleh mencatat waktu terakhir memakai sistem, dengan waktu server", async () => {
  await akun("u1", "petugas");
  const ref = doc(db("u1"), "lbp_pengguna", "u1");
  await assertSucceeds(updateDoc(ref, { terakhir_aktif: serverTimestamp() }));
  await assertFails(updateDoc(ref, { terakhir_aktif: new Date("2030-01-01") }));
  await assertFails(updateDoc(ref, { terakhir_aktif: serverTimestamp(), peran: "admin" }));
});

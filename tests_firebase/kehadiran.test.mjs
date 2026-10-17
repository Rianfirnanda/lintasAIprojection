// Kehadiran dan log aktivitas: hanya pemilik yang menulis, hanya pengelola akun yang membaca, lokasi hanya bila diizinkan.
import { readFileSync } from "node:fs";
import { after, before, beforeEach, test } from "node:test";
import { assertFails, assertSucceeds, initializeTestEnvironment } from "@firebase/rules-unit-testing";
import { addDoc, collection, deleteDoc, doc, getDoc, getDocs, serverTimestamp, setDoc, Timestamp, updateDoc } from "firebase/firestore";

const aturan = readFileSync(new URL("../firestore.rules", import.meta.url), "utf8");
let env;
before(async () => { env = await initializeTestEnvironment({ projectId: "demo-lbp", firestore: { rules: aturan } }); });
after(async () => { await env?.cleanup(); });
beforeEach(async () => { await env.clearFirestore(); });

const db = (uid) => env.authenticatedContext(uid, { email: `${uid}@contoh.go.id`, email_verified: true }).firestore();
const akun = (uid, peran, status = "aktif") => env.withSecurityRulesDisabled(async (c) => {
  await setDoc(doc(c.firestore(), "lbp_pengguna", uid), { email: `${uid}@contoh.go.id`, nama: uid, status, peran, halaman: null });
});
const hadir = (ekstra = {}) => ({ status: "aktif", halaman: "index.html", judul: "Beranda", perangkat: "ponsel", terakhir_aktif: serverTimestamp(),
  izin_lokasi: "belum", lokasi: null, lokasi_waktu: null, ...ekstra });
const LOKASI = { lat: -3.72, lon: 102.45, akurasi: 1100, perkiraan: true };
const hari = (n) => Timestamp.fromMillis(Date.now() + n * 864e5);
const kegiatan = (uid, peran, ekstra = {}) => ({ uid, nama: uid, peran, aksi: "buka", halaman: "index.html", rincian: "", lokasi: null,
  waktu: serverTimestamp(), hapus_pada: hari(90), ...ekstra });

test("pemilik mencatat kehadirannya; lokasi hanya bila izin 'ya'", async () => {
  await akun("p1", "petugas");
  const d = db("p1");
  await assertSucceeds(setDoc(doc(d, "lbp_kehadiran", "p1"), hadir()));
  await assertSucceeds(getDoc(doc(d, "lbp_kehadiran", "p1")));
  await assertFails(setDoc(doc(d, "lbp_kehadiran", "p1"), hadir({ lokasi: LOKASI })));
  await assertSucceeds(setDoc(doc(d, "lbp_kehadiran", "p1"), hadir({ izin_lokasi: "ya", lokasi: LOKASI, lokasi_waktu: Timestamp.now() })));
  await assertFails(setDoc(doc(d, "lbp_kehadiran", "p1"), hadir({ izin_lokasi: "ya", lokasi: { ...LOKASI, lat: 120 } })));
  await assertFails(setDoc(doc(d, "lbp_kehadiran", "p1"), hadir({ status: "hilang" })));
  await assertFails(setDoc(doc(d, "lbp_kehadiran", "p1"), hadir({ terakhir_aktif: Timestamp.fromMillis(0) })));
  await assertFails(setDoc(doc(d, "lbp_kehadiran", "p1"), hadir({ peran: "admin" })));
});

test("orang lain tidak bisa menulis atau membaca kehadiran; akun menunggu tidak tercatat; admin membaca semua", async () => {
  await akun("adm", "admin");
  await akun("p1", "petugas");
  await akun("m1", "masyarakat");
  await akun("baru", null, "menunggu");
  await assertSucceeds(setDoc(doc(db("p1"), "lbp_kehadiran", "p1"), hadir()));
  await assertFails(setDoc(doc(db("m1"), "lbp_kehadiran", "p1"), hadir()));
  await assertFails(getDoc(doc(db("m1"), "lbp_kehadiran", "p1")));
  await assertFails(getDocs(collection(db("m1"), "lbp_kehadiran")));
  await assertFails(setDoc(doc(db("baru"), "lbp_kehadiran", "baru"), hadir()));
  await assertSucceeds(getDocs(collection(db("adm"), "lbp_kehadiran")));
  await assertSucceeds(deleteDoc(doc(db("adm"), "lbp_kehadiran", "p1")));
});

test("log aktivitas: hanya untuk diri sendiri dengan peran yang benar, tidak bisa diubah atau dihapus", async () => {
  await akun("adm", "admin");
  await akun("m1", "masyarakat");
  const d = db("m1");
  const ref = await assertSucceeds(addDoc(collection(d, "lbp_aktivitas"), kegiatan("m1", "masyarakat")));
  await assertSucceeds(addDoc(collection(d, "lbp_aktivitas"), kegiatan("m1", "masyarakat", { aksi: "masuk", lokasi: LOKASI })));
  await assertFails(addDoc(collection(d, "lbp_aktivitas"), kegiatan("adm", "admin")));
  await assertFails(addDoc(collection(d, "lbp_aktivitas"), kegiatan("m1", "petugas")));
  await assertFails(addDoc(collection(d, "lbp_aktivitas"), kegiatan("m1", "masyarakat", { aksi: "hapus_semua" })));
  await assertFails(addDoc(collection(d, "lbp_aktivitas"), kegiatan("m1", "masyarakat", { hapus_pada: hari(5000) })));
  await assertFails(addDoc(collection(d, "lbp_aktivitas"), kegiatan("m1", "masyarakat", { waktu: Timestamp.fromMillis(0) })));
  await assertFails(getDocs(collection(d, "lbp_aktivitas")));
  await assertFails(updateDoc(ref, { aksi: "keluar" }));
  await assertSucceeds(getDocs(collection(db("adm"), "lbp_aktivitas")));
  await assertFails(deleteDoc(doc(db("adm"), "lbp_aktivitas", ref.id)));
});

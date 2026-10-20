// Galat di perangkat pengguna: pemilik akun aktif menambah catatan pendek, hanya pengelola pengguna yang membaca dan menghapus.
import { readFileSync } from "node:fs";
import { after, before, beforeEach, test } from "node:test";
import { assertFails, assertSucceeds, initializeTestEnvironment } from "@firebase/rules-unit-testing";
import { addDoc, collection, deleteDoc, doc, getDocs, serverTimestamp, setDoc, Timestamp, updateDoc } from "firebase/firestore";

const aturan = readFileSync(new URL("../firestore.rules", import.meta.url), "utf8");
let env;
before(async () => { env = await initializeTestEnvironment({ projectId: "demo-lbp", firestore: { rules: aturan } }); });
after(async () => { await env?.cleanup(); });
beforeEach(async () => { await env.clearFirestore(); });

const db = (uid) => env.authenticatedContext(uid, { email: `${uid}@contoh.go.id`, email_verified: true }).firestore();
const akun = (uid, peran, status = "aktif") => env.withSecurityRulesDisabled(async (c) => {
  await setDoc(doc(c.firestore(), "lbp_pengguna", uid), { email: `${uid}@contoh.go.id`, nama: uid, status, peran, halaman: null });
});
const hari = (n) => Timestamp.fromMillis(Date.now() + n * 864e5);
const galat = (uid, peran, ekstra = {}) => ({ uid, peran, halaman: "harga.html", pesan: "x is not a function",
  sumber: "/assets/app.js:10:5", tumpukan: "TypeError: x is not a function\n at /assets/app.js:10:5", jenis: "galat",
  peramban: "Mozilla/5.0", layar: "390x844", daring: true, waktu: serverTimestamp(), hapus_pada: hari(30), ...ekstra });

test("pemilik akun aktif mencatat galatnya sendiri dengan isi yang dibatasi", async () => {
  await akun("m1", "masyarakat");
  const d = db("m1");
  await assertSucceeds(addDoc(collection(d, "lbp_galat"), galat("m1", "masyarakat")));
  await assertSucceeds(addDoc(collection(d, "lbp_galat"), galat("m1", "masyarakat", { jenis: "janji", daring: false })));
  await assertFails(addDoc(collection(d, "lbp_galat"), galat("adm", "masyarakat")));
  await assertFails(addDoc(collection(d, "lbp_galat"), galat("m1", "admin")));
  await assertFails(addDoc(collection(d, "lbp_galat"), galat("m1", "masyarakat", { pesan: "" })));
  await assertFails(addDoc(collection(d, "lbp_galat"), galat("m1", "masyarakat", { pesan: "a".repeat(301) })));
  await assertFails(addDoc(collection(d, "lbp_galat"), galat("m1", "masyarakat", { tumpukan: "a".repeat(1201) })));
  await assertFails(addDoc(collection(d, "lbp_galat"), galat("m1", "masyarakat", { jenis: "lain" })));
  await assertFails(addDoc(collection(d, "lbp_galat"), galat("m1", "masyarakat", { email: "m1@contoh.go.id" })));
  await assertFails(addDoc(collection(d, "lbp_galat"), galat("m1", "masyarakat", { hapus_pada: hari(60) })));
  await assertFails(addDoc(collection(d, "lbp_galat"), galat("m1", "masyarakat", { waktu: Timestamp.fromMillis(0) })));
});

test("akun menunggu tidak bisa mencatat; hanya pengelola pengguna yang membaca dan menghapus; tidak bisa diubah", async () => {
  await akun("adm", "admin");
  await akun("m1", "masyarakat");
  await akun("baru", null, "menunggu");
  await assertFails(addDoc(collection(db("baru"), "lbp_galat"), galat("baru", null)));
  const ref = await addDoc(collection(db("m1"), "lbp_galat"), galat("m1", "masyarakat"));
  await assertFails(getDocs(collection(db("m1"), "lbp_galat")));
  await assertFails(updateDoc(doc(db("m1"), "lbp_galat", ref.id), { pesan: "lain" }));
  await assertFails(deleteDoc(doc(db("m1"), "lbp_galat", ref.id)));
  await assertSucceeds(getDocs(collection(db("adm"), "lbp_galat")));
  await assertFails(updateDoc(doc(db("adm"), "lbp_galat", ref.id), { pesan: "lain" }));
  await assertSucceeds(deleteDoc(doc(db("adm"), "lbp_galat", ref.id)));
});

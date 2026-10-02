// Uji hak akses yang bisa diatur dari situs: tabel hak akses per peran, dan hak admin yang diberikan per orang.
import { readFileSync } from "node:fs";
import { after, before, beforeEach, test } from "node:test";
import { assertFails, assertSucceeds, initializeTestEnvironment } from "@firebase/rules-unit-testing";
import { addDoc, collection, deleteDoc, doc, getDoc, getDocs, serverTimestamp, setDoc, updateDoc } from "firebase/firestore";

const aturan = readFileSync(new URL("../firestore.rules", import.meta.url), "utf8");
let env;
before(async () => { env = await initializeTestEnvironment({ projectId: "demo-lbp", firestore: { rules: aturan } }); });
after(async () => { await env?.cleanup(); });
beforeEach(async () => { await env.clearFirestore(); });

const db = (uid) => env.authenticatedContext(uid, { email: `${uid}@contoh.go.id`, email_verified: true }).firestore();
const akun = (uid, peran, status = "aktif", halaman = null) => env.withSecurityRulesDisabled(async (c) => {
  await setDoc(doc(c.firestore(), "lbp_pengguna", uid), { email: `${uid}@contoh.go.id`, nama: uid, status, peran, halaman });
});
const tabel = (halaman) => env.withSecurityRulesDisabled(async (c) => {
  await setDoc(doc(c.firestore(), "lbp_akses", "peran"), { halaman, diubah_oleh: "adm@contoh.go.id" });
});
const harga = (uid, id) => ({ tanggal: "2026-10-01", kode_pasar: "PSR01", kode_varian: "CMR01", harga: 1000, petugas: "P", id_klien: id,
  oleh_uid: uid, diterima: serverTimestamp(), diperbarui: serverTimestamp() });
const jejak = (uid) => ({ aksi: "setujui", oleh: uid, oleh_email: `${uid}@contoh.go.id`, sasaran: "baru", sasaran_email: "baru@contoh.go.id",
  rincian: "", waktu: serverTimestamp() });

test("orang biasa yang diberi halaman Pengguna bisa mengelola akun biasa seperti admin", async () => {
  await akun("adm", "admin");
  await akun("wakil", "analis", "aktif", ["index.html", "pengguna.html"]);
  await akun("baru", null, "menunggu");
  const d = db("wakil");
  await assertSucceeds(getDocs(collection(d, "lbp_pengguna")));
  await assertSucceeds(updateDoc(doc(d, "lbp_pengguna", "baru"), { status: "aktif", peran: "petugas", halaman: null }));
  await assertSucceeds(addDoc(collection(d, "lbp_jejak"), jejak("wakil")));
  await assertSucceeds(getDocs(collection(d, "lbp_jejak")));
  await assertSucceeds(updateDoc(doc(d, "lbp_pengguna", "baru"), { status: "nonaktif" }));
});

test("pengelola titipan tidak bisa mengangkat, mengubah, atau menghapus admin, dan tidak bisa menaikkan haknya sendiri", async () => {
  await akun("adm", "admin");
  await akun("wakil", "analis", "aktif", ["index.html", "pengguna.html"]);
  await akun("adm2", "tpid", "aktif", ["index.html", "pengaturan.html"]);
  await akun("baru", null, "menunggu");
  const d = db("wakil");
  await assertFails(updateDoc(doc(d, "lbp_pengguna", "baru"), { status: "aktif", peran: "admin" }));
  await assertFails(updateDoc(doc(d, "lbp_pengguna", "baru"), { status: "aktif", peran: "petugas", halaman: ["index.html", "pengaturan.html"] }));
  await assertFails(updateDoc(doc(d, "lbp_pengguna", "adm"), { status: "nonaktif" }));
  await assertFails(updateDoc(doc(d, "lbp_pengguna", "adm2"), { halaman: null }));
  await assertFails(deleteDoc(doc(d, "lbp_pengguna", "adm")));
  await assertFails(updateDoc(doc(d, "lbp_pengguna", "wakil"), { peran: "admin" }));
  await assertFails(updateDoc(doc(d, "lbp_pengguna", "wakil"), { halaman: ["index.html", "pengguna.html", "pengaturan.html"] }));
  await assertFails(setDoc(doc(d, "lbp_akses", "peran"), { halaman: { tpid: ["index.html"] }, diubah_oleh: "wakil@contoh.go.id", diubah_pada: serverTimestamp() }));
});

test("peran Administrator bisa memberi atau mencabut hak admin per orang", async () => {
  await akun("adm", "admin");
  await akun("baru", null, "menunggu");
  const d = db("adm");
  await assertSucceeds(updateDoc(doc(d, "lbp_pengguna", "baru"), { status: "aktif", peran: "analis", halaman: ["index.html", "pengaturan.html"] }));
  await assertSucceeds(updateDoc(doc(d, "lbp_pengguna", "baru"), { halaman: null }));
  await assertFails(updateDoc(doc(d, "lbp_pengguna", "adm"), { peran: "analis" }));
});

test("orang biasa yang diberi halaman Pengaturan bisa mengubah pengaturan, kunci, dan menjalankan proses", async () => {
  await akun("wakil", "tpid", "aktif", ["index.html", "pengaturan.html"]);
  await akun("an", "analis");
  const d = db("wakil");
  await assertSucceeds(setDoc(doc(d, "lbp_pengaturan", "utama"), { isi: {}, versi: 1, diubah_oleh: "wakil@contoh.go.id", diubah_pada: serverTimestamp(), ringkasan: "" }));
  await assertSucceeds(setDoc(doc(d, "lbp_rahasia", "GEMINI_API_KEY"), { nilai: "x", diperbarui: serverTimestamp(), oleh_uid: "wakil" }));
  await assertSucceeds(getDocs(collection(d, "lbp_rahasia_status")));
  await assertSucceeds(setDoc(doc(d, "lbp_perintah", "perbarui"), { jenis: "perbarui", masukan: {}, status: "menunggu", diminta_oleh: "wakil@contoh.go.id", diminta_pada: serverTimestamp() }));
  await assertFails(getDocs(collection(d, "lbp_pengguna")));
  await assertFails(setDoc(doc(db("an"), "lbp_perintah", "perbarui"), { jenis: "perbarui", masukan: {}, status: "menunggu", diminta_oleh: "an@contoh.go.id", diminta_pada: serverTimestamp() }));
});

test("tabel hak akses dari admin menggantikan bawaan peran; izin pribadi tetap paling utama", async () => {
  await akun("adm", "admin");
  await akun("tp", "tpid");
  await akun("ptg", "petugas");
  await akun("ptg2", "petugas", "aktif", ["index.html", "input.html"]);
  await assertFails(setDoc(doc(db("tp"), "lbp_harga", "a"), harga("tp", "a")));
  await assertSucceeds(setDoc(doc(db("adm"), "lbp_akses", "peran"), {
    halaman: { tpid: ["index.html", "input.html"], petugas: ["index.html", "harga.html"] }, diubah_oleh: "adm@contoh.go.id", diubah_pada: serverTimestamp() }));
  await assertSucceeds(getDoc(doc(db("tp"), "lbp_akses", "peran")));
  await assertSucceeds(setDoc(doc(db("tp"), "lbp_harga", "b"), harga("tp", "b")));
  await assertFails(setDoc(doc(db("ptg"), "lbp_harga", "c"), harga("ptg", "c")));
  await assertSucceeds(setDoc(doc(db("ptg2"), "lbp_harga", "d"), harga("ptg2", "d")));
  // Peran yang tidak disebut di tabel tetap memakai bawaan.
  await tabel({ tpid: ["index.html"] });
  await assertSucceeds(setDoc(doc(db("ptg"), "lbp_harga", "e"), harga("ptg", "e")));
});

test("tabel hak akses menolak isian asing, termasuk mengatur peran Administrator", async () => {
  await akun("adm", "admin");
  const d = db("adm");
  const isi = (halaman, tambahan = {}) => ({ halaman, diubah_oleh: "adm@contoh.go.id", diubah_pada: serverTimestamp(), ...tambahan });
  await assertFails(setDoc(doc(d, "lbp_akses", "peran"), isi({ admin: ["index.html"] })));
  await assertFails(setDoc(doc(d, "lbp_akses", "lain"), isi({ tpid: [] })));
  await assertFails(setDoc(doc(d, "lbp_akses", "peran"), isi({ tpid: [] }, { kolom: 1 })));
  await assertFails(getDoc(doc(env.unauthenticatedContext().firestore(), "lbp_akses", "peran")));
});

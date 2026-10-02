// Uji aturan Firestore (firestore.rules) di emulator Firebase.
// Jalankan: npx firebase emulators:exec --only firestore --project demo-lbp "node --test tests_firebase/"
import { readFileSync } from "node:fs";
import { after, before, beforeEach, test } from "node:test";
import { assertFails, assertSucceeds, initializeTestEnvironment } from "@firebase/rules-unit-testing";
import { deleteDoc, doc, getDoc, setDoc, updateDoc, collection, getDocs, addDoc, serverTimestamp } from "firebase/firestore";

const ADMIN_AWAL = "admin.awal@contoh.go.id";
const aturan = readFileSync(new URL("../firestore.rules", import.meta.url), "utf8")
  .replace("/*ADMIN_AWAL*/[]", `['${ADMIN_AWAL}']`);
let env;

before(async () => {
  env = await initializeTestEnvironment({ projectId: "demo-lbp", firestore: { rules: aturan } });
});
after(async () => { await env?.cleanup(); });
beforeEach(async () => { await env.clearFirestore(); });

const db = (uid, email, terverifikasi = true) => env.authenticatedContext(uid, { email, email_verified: terverifikasi }).firestore();
const tamu = () => env.unauthenticatedContext().firestore();
const pendaftaran = (email, tambahan = {}) => ({
  email, nama: "Nama Uji", foto: null, status: "menunggu", peran: null, halaman: null,
  dibuat: serverTimestamp(), diperbarui: serverTimestamp(), ...tambahan,
});
async function isi(uid, data) {
  await env.withSecurityRulesDisabled(async (c) => { await setDoc(doc(c.firestore(), "lbp_pengguna", uid), data); });
}
const adminAktif = () => isi("adm", { email: "adm@contoh.go.id", nama: "Admin", status: "aktif", peran: "admin", halaman: null });

test("pengguna baru hanya bisa mendaftar untuk dirinya sendiri dengan status menunggu", async () => {
  const d = db("u1", "u1@contoh.go.id");
  await assertSucceeds(setDoc(doc(d, "lbp_pengguna", "u1"), pendaftaran("u1@contoh.go.id")));
  await assertFails(setDoc(doc(d, "lbp_pengguna", "u2"), pendaftaran("u1@contoh.go.id")));
});

test("pendaftar tidak bisa langsung aktif, memberi diri peran, izin, atau memalsukan email", async () => {
  const d = db("u1", "u1@contoh.go.id");
  const ref = doc(d, "lbp_pengguna", "u1");
  await assertFails(setDoc(ref, pendaftaran("u1@contoh.go.id", { status: "aktif", peran: "admin" })));
  await assertFails(setDoc(ref, pendaftaran("u1@contoh.go.id", { status: "aktif" })));
  await assertFails(setDoc(ref, pendaftaran("u1@contoh.go.id", { status: "nonaktif" })));
  await assertFails(setDoc(ref, pendaftaran("u1@contoh.go.id", { peran: "analis" })));
  await assertFails(setDoc(ref, pendaftaran("u1@contoh.go.id", { halaman: ["pengguna.html"] })));
  await assertFails(setDoc(ref, pendaftaran("orang.lain@contoh.go.id")));
  await assertFails(setDoc(ref, pendaftaran("u1@contoh.go.id", { kolom_aneh: 1 })));
});

test("tamu tanpa login tidak bisa membaca atau menulis apa pun", async () => {
  await adminAktif();
  await assertFails(getDoc(doc(tamu(), "lbp_pengguna", "adm")));
  await assertFails(setDoc(doc(tamu(), "lbp_pengguna", "x"), pendaftaran("x@contoh.go.id")));
});

test("pengguna yang menunggu tidak bisa menyetujui dirinya sendiri, tapi boleh ganti nama", async () => {
  await isi("u1", { email: "u1@contoh.go.id", nama: "A", status: "menunggu", peran: null, halaman: null });
  const ref = doc(db("u1", "u1@contoh.go.id"), "lbp_pengguna", "u1");
  await assertFails(updateDoc(ref, { status: "aktif", peran: "admin" }));
  await assertFails(updateDoc(ref, { halaman: ["index.html"] }));
  await assertSucceeds(updateDoc(ref, { nama: "Nama Baru" }));
  await assertSucceeds(getDoc(ref));
});

test("pengguna biasa tidak bisa membaca akun orang lain atau mendaftar semua akun", async () => {
  await isi("u1", { email: "u1@contoh.go.id", nama: "A", status: "aktif", peran: "analis", halaman: null });
  await isi("u2", { email: "u2@contoh.go.id", nama: "B", status: "menunggu", peran: null, halaman: null });
  const d = db("u1", "u1@contoh.go.id");
  await assertFails(getDoc(doc(d, "lbp_pengguna", "u2")));
  await assertFails(getDocs(collection(d, "lbp_pengguna")));
  await assertFails(updateDoc(doc(d, "lbp_pengguna", "u2"), { status: "aktif", peran: "admin" }));
});

test("admin aktif bisa melihat semua akun, menyetujui, mengatur peran dan izin, menolak, dan menghapus", async () => {
  await adminAktif();
  await isi("u2", { email: "u2@contoh.go.id", nama: "B", status: "menunggu", peran: null, halaman: null });
  const d = db("adm", "adm@contoh.go.id");
  await assertSucceeds(getDocs(collection(d, "lbp_pengguna")));
  const ref = doc(d, "lbp_pengguna", "u2");
  await assertSucceeds(updateDoc(ref, { status: "aktif", peran: "tpid", halaman: ["index.html", "sinyal.html"] }));
  await assertSucceeds(updateDoc(ref, { peran: "analis", halaman: null }));
  await assertSucceeds(updateDoc(ref, { status: "nonaktif" }));
  await assertSucceeds(updateDoc(ref, { status: "ditolak", peran: null }));
  await assertSucceeds(deleteDoc(ref));
});

test("admin tidak bisa membuat isian yang tidak sah", async () => {
  await adminAktif();
  await isi("u2", { email: "u2@contoh.go.id", nama: "B", status: "menunggu", peran: null, halaman: null });
  const ref = doc(db("adm", "adm@contoh.go.id"), "lbp_pengguna", "u2");
  await assertFails(updateDoc(ref, { status: "aktif", peran: null }));          // aktif wajib punya peran
  await assertFails(updateDoc(ref, { status: "aktif", peran: "raja" }));        // peran tidak dikenal
  await assertFails(updateDoc(ref, { status: "dibekukan" }));                   // status tidak dikenal
  await assertFails(updateDoc(ref, { email: "ganti@contoh.go.id" }));           // email tidak boleh diganti
  await assertFails(updateDoc(ref, { halaman: "semua" }));                      // izin harus daftar
});

test("admin tidak bisa mencabut hak adminnya sendiri atau menghapus dirinya", async () => {
  await adminAktif();
  const ref = doc(db("adm", "adm@contoh.go.id"), "lbp_pengguna", "adm");
  await assertFails(updateDoc(ref, { peran: "analis" }));
  await assertFails(updateDoc(ref, { status: "nonaktif" }));
  await assertFails(deleteDoc(ref));
});

test("akun admin yang dinonaktifkan kehilangan semua hak admin", async () => {
  await isi("adm", { email: "adm@contoh.go.id", nama: "Admin", status: "nonaktif", peran: "admin", halaman: null });
  await isi("u2", { email: "u2@contoh.go.id", nama: "B", status: "menunggu", peran: null, halaman: null });
  const d = db("adm", "adm@contoh.go.id");
  await assertFails(getDocs(collection(d, "lbp_pengguna")));
  await assertFails(updateDoc(doc(d, "lbp_pengguna", "u2"), { status: "aktif", peran: "admin" }));
});

test("admin pertama dari daftar bisa mengangkat dirinya, email lain atau yang belum terverifikasi tidak bisa", async () => {
  const data = pendaftaran(ADMIN_AWAL, { status: "aktif", peran: "admin" });
  await assertFails(setDoc(doc(db("x", ADMIN_AWAL, false), "lbp_pengguna", "x"), data));
  await assertFails(setDoc(doc(db("y", "bukan.admin@contoh.go.id"), "lbp_pengguna", "y"),
    pendaftaran("bukan.admin@contoh.go.id", { status: "aktif", peran: "admin" })));
  await assertSucceeds(setDoc(doc(db("a1", ADMIN_AWAL), "lbp_pengguna", "a1"), data));
});

test("admin pertama yang sudah terdaftar sebagai menunggu bisa naik menjadi admin", async () => {
  await isi("a1", { email: ADMIN_AWAL, nama: "A", status: "menunggu", peran: null, halaman: null });
  const ref = doc(db("a1", ADMIN_AWAL), "lbp_pengguna", "a1");
  await assertFails(updateDoc(ref, { status: "aktif", peran: "analis" }));
  await assertSucceeds(updateDoc(ref, { status: "aktif", peran: "admin" }));
});

test("jejak admin hanya bisa ditulis admin atas namanya sendiri dan tidak bisa diubah", async () => {
  await adminAktif();
  await isi("u1", { email: "u1@contoh.go.id", nama: "A", status: "aktif", peran: "analis", halaman: null });
  const jejak = (uid) => ({ aksi: "setujui", oleh: uid, oleh_email: "adm@contoh.go.id", sasaran: "u2", sasaran_email: "u2@contoh.go.id", rincian: "tpid", waktu: serverTimestamp() });
  const dAdm = db("adm", "adm@contoh.go.id");
  const ref = await assertSucceeds(addDoc(collection(dAdm, "lbp_jejak"), jejak("adm")));
  await assertFails(addDoc(collection(dAdm, "lbp_jejak"), jejak("orang-lain")));
  await assertFails(updateDoc(ref, { aksi: "hapus" }));
  await assertFails(deleteDoc(ref));
  await assertFails(addDoc(collection(db("u1", "u1@contoh.go.id"), "lbp_jejak"), jejak("u1")));
  await assertFails(getDocs(collection(db("u1", "u1@contoh.go.id"), "lbp_jejak")));
});

test("koleksi lain di luar lbp_ tidak dibuka oleh aturan ini", async () => {
  await adminAktif();
  await assertFails(getDoc(doc(db("adm", "adm@contoh.go.id"), "koleksi_aplikasi_lain", "x")));
});

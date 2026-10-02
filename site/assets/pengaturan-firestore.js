// Penyimpan panel Pengaturan lewat Firestore (dipakai bila situs memakai login Google/Firebase). Antarmukanya sama
// dengan KlienGitHub, jadi panel tidak perlu tahu bedanya, tapi admin tidak perlu token GitHub sama sekali:
//   pengaturan       -> lbp_pengaturan/utama   (versi naik satu tiap simpan; aturan Firestore menolak simpanan basi)
//   kunci rahasia    -> lbp_rahasia/{NAMA}     (hanya bisa ditulis; dibaca mesin pengolah saja)
//                       lbp_rahasia_status/{NAMA} (tanda "sudah diisi" untuk panel)
//   tombol Jalankan  -> lbp_perintah/{jenis}   (diambil pemeriksa otomatis, lalu statusnya diisi mesin)
import { firebaseSiap, penggunaKini } from "./firebase-klien.js";
import { GalatGitHub } from "./github.js";

export const JENIS_PERINTAH = { "pipeline.yml": "perbarui", "ai-data-finder.yml": "cari_sumber" };
const NAMA_RAHASIA = /^[A-Z][A-Z0-9_]{1,79}$/;
const iso = (t) => (t?.toDate ? t.toDate().toISOString() : t || null);
const objek = (x) => x && typeof x === "object" && !Array.isArray(x);
/** Isian yang belum ada di simpanan lama (isian baru setelah pembaruan sistem) diambil dari pengaturan yang terbit. */
/** Pilihan AI yang layanannya sudah ditutup (GitHub Models, 30 Juli 2026) dibuang dari simpanan lama. */
function bersihkanLama(isi) {
  const ai = isi?.ai;
  if (ai && typeof ai === "object") {
    if (Array.isArray(ai.urutan_otomatis)) {
      ai.urutan_otomatis = ai.urutan_otomatis.filter((p) => p !== "github_models");
      if (!ai.urutan_otomatis.length) ai.urutan_otomatis = ["gemini"];
    }
    if (ai.penyedia === "github_models") ai.penyedia = "otomatis";
    delete ai.model_github;
  }
  return isi;
}
const lengkapi = (acuan, data) => (objek(acuan) && objek(data)
  ? { ...acuan, ...Object.fromEntries(Object.entries(data).map(([k, v]) => [k, lengkapi(acuan[k], v)])) } : data);

function galat(e) {
  if (e instanceof GalatGitHub) return e;
  const k = e?.code || "";
  if (k === "permission-denied") {
    return new GalatGitHub("Ditolak oleh aturan keamanan. Hanya administrator aktif yang bisa mengubah ini. Bila Anda baru saja menyimpan dari tab lain, muat ulang halaman ini dulu.", { kode: "izin" });
  }
  if (k === "unavailable" || k === "deadline-exceeded") return new GalatGitHub("Tidak ada sambungan internet. Coba lagi.", { kode: "jaringan" });
  return new GalatGitHub(`Terjadi galat: ${e?.message || e}`, { kode: "lain" });
}

export class KlienFirestore {
  /** `terbit`: pengaturan yang sedang berlaku di situs; `versiTerbit`: versi pengaturan situs yang sudah dipakai mesin. */
  constructor({ fb, db, user, terbit, versiTerbit = 0 }) {
    Object.assign(this, { fb, db, user, terbit, versiTerbit });
    this.namaRepo = "Firestore";
    this.alamatRepo = "";
    this.modeFirestore = true;
  }

  static async sambung(opsi) {
    try {
      const { fb, db } = await firebaseSiap();
      const user = await penggunaKini();
      if (!user) throw new GalatGitHub("Anda belum masuk. Buka halaman Masuk, lalu masuk dengan Google.", { kode: "token" });
      return new KlienFirestore({ fb, db, user, ...opsi });
    } catch (e) { throw galat(e); }
  }

  async _coba(fn) {
    try { return await fn(); } catch (e) { throw galat(e); }
  }

  pengguna() { return Promise.resolve({ login: this.user.email }); }
  info() { return Promise.resolve({ default_branch: "main", permissions: { push: true } }); }

  /**
   * Pengaturan terbaru. Bila simpanan di Firestore sudah dipakai mesin (versinya tidak lebih baru dari yang terbit),
   * isi yang terbit di situs yang dipakai, karena bisa saja ada perubahan lain sesudahnya.
   */
  bacaBerkas() {
    return this._coba(async () => {
      const d = await this.fb.getDoc(this.fb.doc(this.db, "lbp_pengaturan", "utama"));
      const data = d.exists() ? d.data() : null;
      const versi = data?.versi || 0;
      const menunggu = !!data && versi > this.versiTerbit;
      return { teks: JSON.stringify(menunggu ? bersihkanLama(lengkapi(this.terbit, data.isi)) : this.terbit), sha: versi, menunggu,
        diubahOleh: data?.diubah_oleh || "", diubahPada: iso(data?.diubah_pada) };
    });
  }

  simpanBerkas({ teks, sha, pesan }) {
    return this._coba(async () => {
      const versi = (sha || 0) + 1;
      await this.fb.setDoc(this.fb.doc(this.db, "lbp_pengaturan", "utama"), {
        isi: JSON.parse(teks), versi, diubah_oleh: this.user.email, diubah_pada: this.fb.serverTimestamp(),
        ringkasan: String(pesan || "").slice(0, 2000),
      });
      return { sha: versi, urlCommit: null };
    });
  }

  daftarRahasia() {
    return this._coba(async () => {
      const snap = await this.fb.getDocs(this.fb.collection(this.db, "lbp_rahasia_status"));
      return new Map(snap.docs.map((d) => [d.id, { diperbarui: iso(d.data().diperbarui), oleh: d.data().oleh_email || "" }]));
    });
  }

  simpanRahasia(nama, nilai) {
    if (!NAMA_RAHASIA.test(nama) || nama.startsWith("FIREBASE_")) return Promise.reject(new Error(`Nama kunci tidak sah: ${nama}`));
    if (!nilai) return Promise.reject(new Error("Nilai kunci kosong"));
    return this._coba(async () => {
      const { fb, db, user } = this;
      const b = fb.writeBatch(db);
      b.set(fb.doc(db, "lbp_rahasia", nama), { nilai, diperbarui: fb.serverTimestamp(), oleh_uid: user.uid });
      b.set(fb.doc(db, "lbp_rahasia_status", nama), { diperbarui: fb.serverTimestamp(), oleh_uid: user.uid, oleh_email: user.email });
      await b.commit();
    });
  }

  hapusRahasia(nama) {
    return this._coba(async () => {
      const { fb, db } = this;
      const b = fb.writeBatch(db);
      b.delete(fb.doc(db, "lbp_rahasia", nama));
      b.delete(fb.doc(db, "lbp_rahasia_status", nama));
      await b.commit();
    });
  }

  jalankanAlur(berkas, _cabang, masukan = {}) {
    const jenis = JENIS_PERINTAH[berkas];
    if (!jenis) return Promise.reject(new Error(`Proses tidak dikenal: ${berkas}`));
    return this._coba(() => this.fb.setDoc(this.fb.doc(this.db, "lbp_perintah", jenis), {
      jenis, masukan, status: "menunggu", diminta_oleh: this.user.email, diminta_pada: this.fb.serverTimestamp(),
    }));
  }

  /** Bentuk sama dengan KlienGitHub.prosesTerakhir, ditambah `pesan` dan `oleh`. */
  static keProses(data) {
    if (!data) return null;
    const status = data.status === "menunggu" ? "queued" : data.status === "berjalan" ? "in_progress" : "completed";
    return { status, hasil: data.hasil || (data.status === "gagal" ? "failure" : data.status === "selesai" ? "success" : null),
      url: data.url || "", dibuat: iso(data.diminta_pada) || new Date().toISOString(), pesan: data.pesan || "", oleh: data.diminta_oleh || "" };
  }

  prosesTerakhir(berkas) {
    return this._coba(async () => {
      const d = await this.fb.getDoc(this.fb.doc(this.db, "lbp_perintah", JENIS_PERINTAH[berkas]));
      return KlienFirestore.keProses(d.exists() ? d.data() : null);
    });
  }

  /** Pantau permintaan "jalankan" secara langsung. Mengembalikan fungsi berhenti. */
  pantauProses(berkas, saatBerubah) {
    return this.fb.onSnapshot(this.fb.doc(this.db, "lbp_perintah", JENIS_PERINTAH[berkas]),
      { includeMetadataChanges: false },
      (d) => saatBerubah(KlienFirestore.keProses(d.exists() ? d.data() : null)), () => {});
  }
}

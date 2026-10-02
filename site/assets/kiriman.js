// Kiriman dari situs ke Firestore: harga, keputusan cek data, tindak lanjut peringatan, dan persetujuan model.
// Dipakai bila situs memakai login Firebase. Mesin pengolah mengambil kiriman ini (pipeline/firestore_sinkron.py),
// memeriksanya, lalu memperbarui dashboard. Aturan Firestore memastikan hanya akun yang berhak yang bisa mengirim.
import { firebaseSiap, penggunaKini, pesanGalat } from "./firebase-klien.js";

export const pakaiFirestore = (meta) => meta?.login === "firebase";

const BATAS_WAKTU = 25000;
const teks = (x, maks) => String(x ?? "").trim().slice(0, maks);
const izinDitolak = (e) => e?.code === "permission-denied" || /permission/i.test(e?.message || "");

async function siap() {
  const f = await firebaseSiap();
  const user = await penggunaKini();
  if (!user) throw Object.assign(new Error("Anda belum masuk. Buka halaman Masuk, lalu masuk dengan Google."), { code: "belum-masuk" });
  return { ...f, user };
}

function denganBatasWaktu(janji) {
  let jam;
  const habis = new Promise((_, tolak) => {
    jam = setTimeout(() => tolak(Object.assign(new Error("Sambungan terlalu lambat."), { code: "batas-waktu" })), BATAS_WAKTU);
  });
  return Promise.race([janji, habis]).finally(() => clearTimeout(jam));
}

/** Pesan galat untuk orang awam. */
export function pesanKiriman(e) {
  if (e?.code === "belum-masuk") return e.message;
  if (e?.code === "batas-waktu" || e?.code === "unavailable") return "Sambungan internet lemah. Data tetap tersimpan di perangkat dan bisa dikirim lagi.";
  if (izinDitolak(e)) return "Ditolak: akun Anda belum diberi izin untuk ini, atau isiannya tidak sah. Hubungi admin bila perlu.";
  return pesanGalat(e);
}

/** Kirim banyak dokumen sekaligus (bertahap supaya HP dengan sinyal lemah tidak kewalahan). */
async function kirimBertahap(daftar, kirimSatu, ukuran = 20) {
  const terkirim = [];
  const gagal = [];
  for (let i = 0; i < daftar.length; i += ukuran) {
    const potong = daftar.slice(i, i + ukuran);
    const hasil = await Promise.allSettled(potong.map(kirimSatu));
    hasil.forEach((h, j) => {
      if (h.status === "fulfilled") terkirim.push(potong[j]);
      else gagal.push({ item: potong[j], galat: h.reason, pesan: pesanKiriman(h.reason) });
    });
    if (gagal.some((g) => g.galat?.code === "batas-waktu" || g.galat?.code === "belum-masuk")) {
      daftar.slice(i + ukuran).forEach((item) => gagal.push({ item, galat: null, pesan: "Belum dicoba karena sambungan bermasalah." }));
      break;
    }
  }
  return { terkirim, gagal };
}

/**
 * Kirim baris harga (bentuk antrean Catat Harga atau hasil petakanHarga). ID dokumen = id_klien, jadi aman dikirim
 * ulang: bila ternyata sudah sampai sebelumnya, dianggap terkirim.
 */
export async function kirimHarga(daftar, { berkas = "" } = {}) {
  const { fb, db, user } = await siap();
  return kirimBertahap(daftar, async (b) => {
    const ref = fb.doc(db, "lbp_harga", b.id_klien);
    const data = {
      tanggal: b.tanggal, kode_pasar: teks(b.kode_pasar, 30).toUpperCase(), kode_varian: teks(b.kode_varian, 30).toUpperCase(),
      harga: Number(b.harga), satuan: teks(b.satuan, 20), kode_sumber: teks(b.kode_sumber, 30), petugas: teks(b.petugas, 60),
      responden: teks(b.responden, 60), id_klien: b.id_klien, waktu_input: teks(b.waktu_input, 40), catatan: teks(b.catatan, 300),
      oleh_uid: user.uid, oleh_email: user.email, diterima: fb.serverTimestamp(), diperbarui: fb.serverTimestamp(),
    };
    if (berkas) data.berkas = teks(berkas, 160);
    try {
      await denganBatasWaktu(fb.setDoc(ref, data));
    } catch (e) {
      // Kiriman ulang dari dokumen yang sudah ada ditolak aturan (harga tidak bisa diubah). Cek apakah memang sudah ada.
      if (!izinDitolak(e)) throw e;
      const ada = await denganBatasWaktu(fb.getDoc(ref)).catch(() => null);
      if (!ada?.exists()) throw e;
    }
  });
}

/** Simpan keputusan cek data (terima/tolak). Satu dokumen per observasi; keputusan terbaru yang berlaku. */
export async function simpanKeputusan(daftar) {
  const { fb, db, user } = await siap();
  return kirimBertahap(daftar, (k) => denganBatasWaktu(fb.setDoc(fb.doc(db, "lbp_validasi", k.id_observasi), {
    id_observasi: k.id_observasi, keputusan: k.keputusan, alasan: teks(k.alasan, 300), validator: teks(k.validator, 120),
    tanggal_validasi: teks(k.tanggal_validasi, 40), oleh_uid: user.uid, diperbarui: fb.serverTimestamp(),
  })));
}

/** Catat satu tindak lanjut peringatan. */
export async function kirimTindakLanjut(b) {
  const { fb, db, user } = await siap();
  await denganBatasWaktu(fb.addDoc(fb.collection(db, "lbp_tindak_lanjut"), {
    id_sinyal: teks(b.id_sinyal, 160), status: b.status, catatan: teks(b.catatan, 500), petugas: teks(b.petugas, 120),
    tanggal: teks(b.tanggal, 40), kode_varian: teks(b.kode_varian, 30), tanggal_kejadian: teks(b.tanggal_kejadian, 20),
    oleh_uid: user.uid, diperbarui: fb.serverTimestamp(),
  }));
}

/** Simpan persetujuan cara prakiraan untuk beberapa varian. */
export async function kirimPersetujuan(daftar) {
  const { fb, db, user } = await siap();
  return kirimBertahap(daftar, (s) => denganBatasWaktu(fb.addDoc(fb.collection(db, "lbp_persetujuan_model"), {
    kode_varian: teks(s.kode_varian, 30), model: teks(s.model, 60), keputusan: s.keputusan, penyetuju: teks(s.penyetuju, 120),
    tanggal: teks(s.tanggal, 40), catatan: teks(s.catatan, 300), oleh_uid: user.uid, diperbarui: fb.serverTimestamp(),
  })));
}

/**
 * Kunjungan ke pedagang yang tidak menghasilkan harga (menolak, tidak ada, kios tutup). ID = id_klien, jadi aman
 * dikirim ulang dari HP yang sempat luring.
 */
export async function kirimKunjungan(daftar) {
  const { fb, db, user } = await siap();
  return kirimBertahap(daftar, async (k) => {
    const ref = fb.doc(db, "lbp_kunjungan", k.id_klien);
    try {
      await denganBatasWaktu(fb.setDoc(ref, {
        tanggal: k.tanggal, kode_pasar: teks(k.kode_pasar, 30), responden: teks(k.responden, 60), status: k.status,
        alasan: teks(k.alasan, 60), petugas: teks(k.petugas, 60), waktu_input: teks(k.waktu_input, 40),
        oleh_uid: user.uid, diperbarui: fb.serverTimestamp(),
      }));
    } catch (e) {
      if (!izinDitolak(e)) throw e;
      const ada = await denganBatasWaktu(fb.getDoc(ref)).catch(() => null);
      if (!ada?.exists()) throw e;
    }
  });
}

/** Catat kebijakan atau intervensi TPID. `id` diisi bila mengubah catatan yang sudah ada. */
export async function simpanKebijakan(k, id = null) {
  const { fb, db, user } = await siap();
  const data = {
    tanggal_mulai: k.tanggal_mulai, tanggal_selesai: k.tanggal_selesai || "", jenis: k.jenis, tujuan: k.tujuan,
    kode_varian: k.kode_varian.map((x) => teks(x, 30).toUpperCase()).slice(0, 30), uraian: teks(k.uraian, 500),
    id_rekomendasi: teks(k.id_rekomendasi, 80), pencatat: teks(k.pencatat, 120), oleh_uid: user.uid, diperbarui: fb.serverTimestamp(),
  };
  if (id) await denganBatasWaktu(fb.setDoc(fb.doc(db, "lbp_kebijakan", id), data));
  else await denganBatasWaktu(fb.addDoc(fb.collection(db, "lbp_kebijakan"), data));
}

/** Catat rapat atau forum TPID. */
export async function simpanRapat(r) {
  const { fb, db, user } = await siap();
  await denganBatasWaktu(fb.addDoc(fb.collection(db, "lbp_rapat"), {
    tanggal: r.tanggal, jenis: r.jenis, agenda: teks(r.agenda, 300), keputusan: teks(r.keputusan, 1000),
    jumlah_sinyal: Math.max(0, Math.min(500, Math.round(Number(r.jumlah_sinyal) || 0))), peserta: teks(r.peserta, 300),
    tautan_notulen: /^https:\/\//.test(r.tautan_notulen || "") ? teks(r.tautan_notulen, 300) : "",
    pencatat: teks(r.pencatat, 120), oleh_uid: user.uid, diperbarui: fb.serverTimestamp(),
  }));
}

/** Setujui atau tolak rekomendasi langkah. Keputusan terbaru yang berlaku. */
export async function putuskanRekomendasi(id, keputusan, { catatan = "", penyetuju = "" } = {}) {
  const { fb, db, user } = await siap();
  await denganBatasWaktu(fb.setDoc(fb.doc(db, "lbp_keputusan_rekomendasi", id), {
    id_rekomendasi: id, keputusan, catatan: teks(catatan, 300), penyetuju: teks(penyetuju, 120),
    tanggal: new Date().toISOString().slice(0, 10), oleh_uid: user.uid, diperbarui: fb.serverTimestamp(),
  }));
}

/** Pantau status proses pembaruan terakhir (lbp_status/pipeline). Mengembalikan fungsi berhenti. */
export async function pantauProses(saatBerubah) {
  const { fb, db } = await siap();
  return fb.onSnapshot(fb.doc(db, "lbp_status", "pipeline"), (d) => saatBerubah(d.exists() ? d.data() : null), () => saatBerubah(null));
}

const jam = (t) => (t?.toDate ? t.toDate() : t ? new Date(t) : null);

/**
 * Kalimat singkat tentang kapan kiriman muncul di dashboard. Pemeriksa otomatis (antrean.yml) melihat kiriman baru
 * tiap 15 menit pada jam kerja; harga baru dikumpulkan dulu paling lama sekitar satu jam.
 */
export function teksProses(st, { harga = false } = {}) {
  const fmt = (d) => d.toLocaleString("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const dasar = harga
    ? "Harga yang terkirim masuk dashboard otomatis, paling lambat sekitar 1 jam pada jam kerja (Senin sampai Jumat, 07.00 sampai 18.00 WIB)."
    : "Kiriman diproses otomatis, biasanya dalam 15 sampai 30 menit pada jam kerja (Senin sampai Jumat, 07.00 sampai 18.00 WIB).";
  if (!st) return dasar;
  if (st.status === "berjalan") return `Pembaruan sedang berjalan sejak ${fmt(jam(st.mulai))}. ${dasar}`;
  const selesai = jam(st.selesai);
  if (!selesai) return dasar;
  return `Pembaruan terakhir ${st.hasil === "success" ? "selesai" : "gagal"} ${fmt(selesai)}. ${dasar}`;
}

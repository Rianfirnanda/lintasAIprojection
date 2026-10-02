// AI Data Finder yang berjalan langsung di browser admin: cari di web (Tavily), lalu AI gratis (Gemini dan cadangannya)
// menyusun kandidat sumber dari hasil pencarian itu. Hasilnya keluar dalam hitungan detik, lalu disimpan ke Firestore
// (lbp_kandidat_ai) dan dicatat di Log proses AI (lbp_log_ai). Mesin pengolah nanti mengecek apakah alamatnya bisa
// dibuka dan menggabungkannya ke halaman Sumber Data.
//
// Prompt dan alamat layanan diambil dari data/ai_prompt.json yang dibuat mesin dari pipeline/pencari_data.py, jadi
// browser dan mesin memakai aturan yang sama. Kunci AI hanya bisa dibaca peran Administrator (aturan Firestore).
import { firebaseSiap, penggunaKini } from "./firebase-klien.js";
import { muatJSON } from "./app.js";

const KUNCI = ["GEMINI_API_KEY", "TAVILY_API_KEY", "GROQ_API_KEY", "CEREBRAS_API_KEY", "OPENROUTER_API_KEY", "MISTRAL_API_KEY"];
const BATAS_WAKTU = 60000;
const KOLOM_TEKS = 400;

class Lewati extends Error {}

const isi = (templat, nilai) => templat.replace(/\{(komoditas|periode|kebutuhan|wilayah)\}/g, (_, k) => nilai[k]);
const host = (url) => { try { return new URL(url.includes("://") ? url : `https://${url}`).host.toLowerCase().replace(/^www\./, ""); } catch { return ""; } };

/** Sama dengan pencari_data._cocok: URL ada di hasil pencarian bila sama persis atau host-nya sama/subdomain. */
export function cocok(url, daftar) {
  if (!url) return false;
  if (daftar.includes(url)) return true;
  const h = host(url);
  return daftar.some((u) => { const x = host(u); return x && (h === x || h.endsWith(`.${x}`) || x.endsWith(`.${h}`)); });
}

/** Sama dengan pencari_data.ambil_json_dari_teks. */
export function ambilJson(teks) {
  const t = String(teks || "").trim();
  const pagar = t.match(/```(?:json)?\s*(\{[\s\S]*\})\s*```/);
  let s = pagar ? pagar[1] : t;
  if (!pagar) {
    const a = t.indexOf("{"), b = t.lastIndexOf("}");
    if (a < 0 || b <= a) throw new Lewati("AI tidak mengembalikan JSON");
    s = t.slice(a, b + 1);
  }
  try { return JSON.parse(s); } catch { throw new Lewati("JSON dari AI tidak valid"); }
}

/** Sama dengan pencari_data.normalisasi_hasil. */
export function normalisasi(hasil, kolom) {
  const kandidat = [];
  for (const k of hasil?.kandidat || []) {
    if (!k || typeof k !== "object") continue;
    const baru = Object.fromEntries(kolom.map((c) => [c, k[c] ?? "tidak diketahui"]));
    for (const c of kolom) if (c !== "perlu_izin" && baru[c] !== null) baru[c] = String(baru[c]);
    baru.perlu_izin = Boolean(k.perlu_izin ?? true);
    if (baru.nama_sumber && baru.nama_sumber !== "tidak diketahui") kandidat.push(baru);
  }
  const tidak = hasil?.tidak_ditemukan || [];
  return { kandidat, tidak_ditemukan: Array.isArray(tidak) ? tidak.map(String) : [String(tidak)], catatan: String(hasil?.catatan || "") };
}

async function kirim(url, header, badan) {
  let r;
  try {
    r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", ...header }, body: JSON.stringify(badan),
      signal: AbortSignal.timeout(BATAS_WAKTU) });
  } catch (e) {
    throw new Lewati(e?.name === "TimeoutError" ? "waktu habis" : "tidak bisa dihubungi dari browser (diblokir atau jaringan)");
  }
  const teks = await r.text();
  if (!r.ok) {
    const arti = { 400: "permintaan ditolak", 401: "kunci ditolak", 403: "akses ditolak", 404: "model tidak ditemukan", 429: "batas pemakaian gratis tercapai", 432: "kuota habis" }[r.status]
      || (r.status >= 500 ? "layanan sedang bermasalah" : "");
    throw new Lewati(`HTTP ${r.status}${arti ? ` (${arti})` : ""}: ${teks.replace(/\s+/g, " ").slice(0, 200)}`);
  }
  try { return JSON.parse(teks); } catch { throw new Lewati(`jawaban bukan JSON: ${teks.slice(0, 120)}`); }
}

const tunggu = (ms) => new Promise((r) => setTimeout(r, ms));

async function tanyaGemini(b, kunci, cfg, sistem, teks) {
  let galat;
  for (const model of [...new Set([cfg.model_gemini || "gemini-flash-latest", b.model_gemini_cadangan])]) {
    for (let coba = 0; coba < 2; coba++) {
      try {
        const data = await kirim(b.url_gemini.replace("{model}", model), { "x-goog-api-key": kunci }, {
          system_instruction: { parts: [{ text: sistem }] },
          contents: [{ role: "user", parts: [{ text: teks + b.format_json }] }],
          generationConfig: { temperature: 0.2 },
        });
        const c = data.candidates?.[0];
        const keluaran = (c?.content?.parts || []).map((p) => p.text || "").join("");
        if (!keluaran.trim()) throw new Lewati("Gemini tidak mengembalikan jawaban");
        return { hasil: ambilJson(keluaran), model: data.modelVersion || model };
      } catch (e) {
        galat = e;
        if (!/HTTP 50[03]/.test(e.message)) throw e;
        if (coba === 0) await tunggu(5000);
      }
    }
  }
  throw galat;
}

async function tanyaSejenisOpenai(p, kunci, model, sistem, teks, formatJson) {
  const data = await kirim(p.url, { Authorization: `Bearer ${kunci}` }, {
    model, temperature: 0.2, messages: [{ role: "system", content: sistem }, { role: "user", content: teks + formatJson }],
  });
  if (data.error) throw new Lewati(`${p.nama}: ${data.error.message || data.error}`.slice(0, 300));
  const isiPesan = data.choices?.[0]?.message?.content;
  const keluaran = Array.isArray(isiPesan) ? isiPesan.map((x) => x?.text || "").join("") : String(isiPesan || "");
  if (!keluaran.trim()) throw new Lewati(`${p.nama} tidak mengembalikan jawaban`);
  return { hasil: ambilJson(keluaran), model: data.model || model };
}

async function bacaKunci(fb, db) {
  const kunci = {};
  const hasil = await Promise.allSettled(KUNCI.map((n) => fb.getDoc(fb.doc(db, "lbp_rahasia", n))));
  hasil.forEach((h, i) => { if (h.status === "fulfilled" && h.value.exists()) kunci[KUNCI[i]] = String(h.value.data().nilai || "").trim(); });
  if (hasil.every((h) => h.status === "rejected")) throw new Error("Akun ini tidak boleh membaca kunci AI (hanya peran Administrator).");
  return kunci;
}

/**
 * Jalankan pencarian di browser. `catat(teks, jenis)` dipanggil di setiap langkah (untuk log langsung di layar).
 * Mengembalikan { ok, langkah, catatan?, alasan?, pindahKeMesin }.
 */
export async function cariDiBrowser(masukan, catat = () => {}) {
  const langkah = [];
  const tulis = (teks, jenis = "info") => {
    const entri = { waktu: new Date().toLocaleTimeString("id-ID", { hour12: false, timeZone: "Asia/Jakarta" }) + " WIB", teks: String(teks).slice(0, KOLOM_TEKS), jenis };
    langkah.push(entri);
    catat(entri);
  };
  const nilai = { komoditas: masukan.komoditas, periode: masukan.periode, kebutuhan: masukan.kebutuhan || "harga eceran harian",
    wilayah: masukan.wilayah || "Kabupaten Bengkulu Tengah, Provinsi Bengkulu" };
  const { fb, db } = await firebaseSiap();
  const user = await penggunaKini();
  tulis(`Mulai mencari sumber data ${nilai.kebutuhan} untuk ${nilai.komoditas} (${nilai.periode}), langsung di browser.`);

  let b, cfg, kunci;
  try {
    [b, cfg] = await Promise.all([muatJSON("ai_prompt.json"), muatJSON("pengaturan.json").then((p) => p.ai || {})]);
    kunci = await bacaKunci(fb, db);
  } catch (e) {
    tulis(`Tidak bisa disiapkan di browser: ${e.message || e}`, "peringatan");
    return { ok: false, langkah, alasan: e.message || String(e), pindahKeMesin: true };
  }

  // 1. Pencarian web
  const web = new Map();
  if (kunci.TAVILY_API_KEY) {
    for (const [q, domain] of b.templat_kueri_web) {
      try {
        const data = await kirim(b.url_tavily, { Authorization: `Bearer ${kunci.TAVILY_API_KEY}` },
          { query: isi(q, nilai), search_depth: "basic", max_results: 6, include_answer: false, ...(domain ? { include_domains: domain } : {}) });
        for (const r of data.results || []) {
          const url = String(r.url || "").trim();
          if (url.startsWith("http") && !web.has(url)) web.set(url, { judul: String(r.title || "").slice(0, 200), url, isi: String(r.content || "").replace(/\s+/g, " ").slice(0, 600) });
        }
      } catch (e) {
        tulis(`Pencarian web Tavily gagal: ${e.message}`, "peringatan");
        if (/HTTP 4(01|32|33)/.test(e.message) || /diblokir/.test(e.message)) break;
      }
    }
  }
  const hasilWeb = [...web.values()].slice(0, b.maks_hasil_web || 15);
  if (hasilWeb.length) tulis(`Pencarian web Tavily: ${hasilWeb.length} halaman ditemukan.`);
  else if (!kunci.TAVILY_API_KEY) tulis("Pencarian web dilewati: kunci Tavily belum diisi. AI menjawab dari pengetahuannya saja.", "peringatan");

  let teks = isi(b.templat_permintaan, nilai);
  if (hasilWeb.length) {
    teks += "\n\nHASIL PENCARIAN WEB (diambil hari ini):\n" + hasilWeb.map((h, i) => `[${i + 1}] ${h.judul}\nURL: ${h.url}\nCuplikan: ${h.isi}`).join("\n\n");
  }
  const sistem = b.sistem + (hasilWeb.length ? b.tambahan_hasil_web : b.tambahan_tanpa_pencarian);

  // 2. AI, bergantian
  const pilihan = (masukan.penyedia || cfg.penyedia || "otomatis").toLowerCase();
  const dikenal = ["gemini", ...Object.keys(b.sejenis_openai)];
  const urutan = pilihan === "otomatis" || !dikenal.includes(pilihan)
    ? [...new Set([...(cfg.urutan_otomatis || []).filter((x) => dikenal.includes(x)), ...b.gratis])]
    : [pilihan];
  const dilewati = [];
  let jawab, dipakai, semuaDiblokir = true;
  for (const nama of urutan) {
    try {
      if (nama === "gemini") {
        if (!kunci.GEMINI_API_KEY) throw new Lewati("kunci GEMINI_API_KEY belum diisi");
        jawab = await tanyaGemini(b, kunci.GEMINI_API_KEY, cfg, sistem, teks);
      } else {
        const p = b.sejenis_openai[nama];
        if (!kunci[p.kunci]) throw new Lewati(`kunci ${p.kunci} belum diisi`);
        jawab = await tanyaSejenisOpenai(p, kunci[p.kunci], cfg[p.model], sistem, teks, b.format_json);
      }
      dipakai = nama;
      break;
    } catch (e) {
      const pesan = e.message || String(e);
      if (!/diblokir|belum diisi/.test(pesan)) semuaDiblokir = false;
      dilewati.push(`${nama}: ${pesan}`.slice(0, 400));
      tulis(`${nama} dilewati: ${pesan}`, "peringatan");
    }
  }
  if (!jawab) {
    tulis("Tidak ada AI yang bisa dipakai dari browser.", "galat");
    return { ok: false, langkah, alasan: dilewati.join("; "), pindahKeMesin: semuaDiblokir };
  }

  const hasil = normalisasi(jawab.hasil, b.kolom_kandidat);
  const urlCari = hasilWeb.map((h) => h.url);
  for (const k of hasil.kandidat) {
    k.url_ada_di_hasil_pencarian = hasilWeb.length ? cocok(k.url, urlCari) : null;
    k.url_dapat_diakses = null;
    k.keterangan_url = "dicek mesin pada pengolahan berikutnya";
    k.status_verifikasi = "kandidat";
  }
  tulis(`${dipakai} (${jawab.model}) menjawab: ${hasil.kandidat.length} kandidat sumber.`);

  // 3. Simpan
  const pencarianWeb = hasilWeb.length ? `Tavily, ${hasilWeb.length} hasil` : "";
  const catatan = { penyedia: dipakai, model: jawab.model, hasil, pencarian_web: pencarianWeb, penyedia_dilewati: dilewati,
    punya_pencarian_web: hasilWeb.length > 0, url_hasil_pencarian: urlCari, permintaan: { ...nilai, prompt: teks.slice(0, 4000) } };
  try {
    await fb.addDoc(fb.collection(db, "lbp_kandidat_ai"), {
      permintaan: catatan.permintaan, penyedia: dipakai, model: String(jawab.model), pencarian_web: pencarianWeb,
      punya_pencarian_web: hasilWeb.length > 0, penyedia_dilewati: dilewati, url_pencarian: urlCari,
      hasil: JSON.stringify(hasil), oleh_uid: user.uid, oleh_email: user.email, diperbarui: fb.serverTimestamp(),
    });
    tulis("Hasil tersimpan. Alamatnya dicek mesin, lalu tampil di halaman Sumber Data dalam beberapa menit.");
  } catch (e) {
    tulis(`Hasil belum tersimpan: ${e.message || e}`, "peringatan");
  }
  return { ok: true, langkah, catatan };
}

/** Simpan satu proses (berhasil, gagal, atau dialihkan ke mesin) ke Log proses AI. */
export async function simpanLog(masukan, hasil) {
  const { fb, db } = await firebaseSiap();
  const user = await penggunaKini();
  const c = hasil.catatan || {};
  await fb.addDoc(fb.collection(db, "lbp_log_ai"), {
    sumber: "situs", komoditas: String(masukan.komoditas || "").slice(0, 120), periode: String(masukan.periode || "").slice(0, 60),
    langkah: hasil.langkah.slice(0, 80), hasil: hasil.ok ? "berhasil" : hasil.pindahKeMesin ? "dialihkan" : "gagal",
    penyedia: c.penyedia || "", model: String(c.model || ""), jumlah_kandidat: c.hasil?.kandidat?.length || 0,
    pencarian_web: c.pencarian_web || "", oleh_uid: user.uid, oleh_email: user.email, diperbarui: fb.serverTimestamp(),
  });
}

/** Pantau Log proses AI terbaru (dari situs, mesin, dan jadwal harian). Mengembalikan fungsi berhenti. */
export async function pantauLog(saatBerubah, saatGagal = () => {}, batas = 30) {
  const { fb, db } = await firebaseSiap();
  const q = fb.query(fb.collection(db, "lbp_log_ai"), fb.orderBy("diperbarui", "desc"), fb.limit(batas));
  return fb.onSnapshot(q, (snap) => saatBerubah(snap.docs.map((d) => ({ id: d.id, ...d.data(), diperbarui: d.data().diperbarui?.toDate?.() || null }))), saatGagal);
}

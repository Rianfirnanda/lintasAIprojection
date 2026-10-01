// Klien GitHub untuk panel admin. Semua permintaan langsung dari browser ke api.github.com memakai token admin.
// Token tidak pernah disimpan di repositori atau dikirim ke tempat lain. Nilai GitHub Secrets dienkripsi di browser
// (sealed box, sama dengan libsodium) sebelum dikirim, dan GitHub tidak pernah mengembalikannya lagi.
import { segel } from "../vendor/sealedbox/sealedbox.js";

export const API = "https://api.github.com";

export class GalatGitHub extends Error {
  constructor(pesan, { status = 0, kode = "", detail = "" } = {}) {
    super(pesan);
    this.name = "GalatGitHub";
    this.status = status;
    this.kode = kode; // "jaringan" | "token" | "izin" | "tidak_ada" | "bentrok" | "batas" | "ditolak" | "lain"
    this.detail = detail;
  }
}

/** "pemilik/repo" atau alamat GitHub (boleh berakhiran .git atau sub-halaman) menjadi { pemilik, repo }; null bila tak dikenali. */
export function bacaRepo(teks) {
  const t = String(teks || "").trim().replace(/^https?:\/\/(www\.)?github\.com\//i, "").replace(/\.git$/i, "");
  const m = t.match(/^([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))\/([A-Za-z0-9._-]{1,100})(?:[/?#].*)?$/);
  return m ? { pemilik: m[1], repo: m[2].replace(/\.git$/i, "") } : null;
}

export function keBase64(bytes) {
  let biner = "";
  for (let i = 0; i < bytes.length; i += 0x8000) biner += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(biner);
}

export function dariBase64(b64) {
  const biner = atob(String(b64).replace(/\s/g, ""));
  return Uint8Array.from(biner, (c) => c.charCodeAt(0));
}

export const keBase64Teks = (teks) => keBase64(new TextEncoder().encode(teks));
export const dariBase64Teks = (b64) => new TextDecoder().decode(dariBase64(b64));

const NAMA_RAHASIA = /^[A-Z][A-Z0-9_]{1,79}$/;

const IZIN = {
  contents: "Contents: Read and write",
  secrets: "Secrets: Read and write",
  actions: "Actions: Read and write",
};

export class KlienGitHub {
  /** ambil: fungsi fetch (bisa diganti saat pengujian). */
  constructor({ token, pemilik, repo, ambil = (...a) => globalThis.fetch(...a) }) {
    if (!token || !pemilik || !repo) throw new Error("Token dan repositori wajib diisi");
    this._token = token;
    this.pemilik = pemilik;
    this.repo = repo;
    this._ambil = ambil;
  }

  get namaRepo() {
    return `${this.pemilik}/${this.repo}`;
  }

  get alamatRepo() {
    return `https://github.com/${this.pemilik}/${this.repo}`;
  }

  async _minta(metode, jalur, { badan, izin = "", diharapkan = [200, 201, 204] } = {}) {
    const headers = { Accept: "application/vnd.github+json", Authorization: `Bearer ${this._token}` };
    const opsi = { method: metode, headers };
    if (badan !== undefined) {
      headers["Content-Type"] = "application/json";
      opsi.body = JSON.stringify(badan);
    }
    let res;
    try {
      res = await this._ambil(`${API}${jalur}`, opsi);
    } catch {
      throw new GalatGitHub("Tidak bisa menghubungi GitHub. Periksa internet Anda, atau matikan pemblokir iklan atau VPN lalu coba lagi.", { kode: "jaringan" });
    }
    if (diharapkan.includes(res.status)) {
      // 201 dan 204 bisa tanpa isi (mis. saat GitHub Secret dibuat atau diganti), jadi jangan paksa dibaca sebagai JSON.
      const isi = res.status === 204 ? "" : await res.text();
      return isi.trim() ? JSON.parse(isi) : null;
    }
    let detail = "";
    try {
      detail = (await res.json()).message || "";
    } catch { /* badan bukan JSON */ }
    throw this._galat(res, detail, izin);
  }

  _galat(res, detail, izin) {
    const status = res.status;
    const sisa = res.headers?.get?.("x-ratelimit-remaining");
    const ket = { status, detail };
    if (status === 401) return new GalatGitHub("Token ditolak. Mungkin salah salin, sudah kedaluwarsa, atau sudah dicabut.", { ...ket, kode: "token" });
    if (status === 403 && (sisa === "0" || /rate limit/i.test(detail))) {
      return new GalatGitHub("Batas permintaan GitHub sedang habis. Tunggu beberapa menit lalu coba lagi.", { ...ket, kode: "batas" });
    }
    if (status === 403) {
      const perlu = izin ? ` Token perlu izin "${IZIN[izin] || izin}".` : "";
      return new GalatGitHub(`Token ini belum punya izin untuk langkah tersebut.${perlu} Ubah izin token di GitHub, lalu sambungkan lagi.`, { ...ket, kode: "izin" });
    }
    if (status === 404) return new GalatGitHub("Tidak ditemukan. Periksa nama repositori, atau token belum diberi akses ke repositori ini.", { ...ket, kode: "tidak_ada" });
    if (status === 409) return new GalatGitHub("Berkasnya baru saja berubah di GitHub. Muat ulang lalu coba lagi.", { ...ket, kode: "bentrok" });
    if (status === 422) {
      const dilindungi = /protected branch|required status|review/i.test(detail);
      return new GalatGitHub(dilindungi ? "Cabang ini dilindungi, jadi perubahan langsung ditolak GitHub. Izinkan akun Anda mengubah langsung, atau ubah lewat pull request."
        : `GitHub menolak isiannya${detail ? `: ${detail}` : "."}`, { ...ket, kode: "ditolak" });
    }
    return new GalatGitHub(`GitHub membalas dengan kode ${status}${detail ? `: ${detail}` : "."}`, { ...ket, kode: "lain" });
  }

  _rute(sisa = "") {
    return `/repos/${encodeURIComponent(this.pemilik)}/${encodeURIComponent(this.repo)}${sisa}`;
  }

  /** Pemilik token. Sekaligus menguji bahwa token berlaku. */
  pengguna() {
    return this._minta("GET", "/user");
  }

  /** Keterangan repositori: cabang bawaan dan hak akses akun. */
  info() {
    return this._minta("GET", this._rute());
  }

  /** Isi berkas teks beserta sha-nya (dibutuhkan untuk menyimpan perubahan). */
  async bacaBerkas(path, cabang) {
    const q = cabang ? `?ref=${encodeURIComponent(cabang)}` : "";
    const d = await this._minta("GET", this._rute(`/contents/${path.split("/").map(encodeURIComponent).join("/")}${q}`), { izin: "contents" });
    if (d.encoding !== "base64") throw new GalatGitHub("Berkas terlalu besar atau bukan teks biasa.", { kode: "lain" });
    return { teks: dariBase64Teks(d.content), sha: d.sha };
  }

  /** Menyimpan berkas lewat satu commit. `sha` adalah sha berkas yang sedang diganti. */
  async simpanBerkas({ path, teks, sha, pesan, cabang }) {
    const badan = { message: pesan, content: keBase64Teks(teks), sha };
    if (cabang) badan.branch = cabang;
    const d = await this._minta("PUT", this._rute(`/contents/${path.split("/").map(encodeURIComponent).join("/")}`), { badan, izin: "contents" });
    return { sha: d.content.sha, urlCommit: d.commit.html_url, shaCommit: d.commit.sha };
  }

  /** Daftar nama GitHub Secrets beserta waktu diperbarui. Nilainya tidak pernah dikembalikan GitHub. */
  async daftarRahasia() {
    const d = await this._minta("GET", this._rute("/actions/secrets?per_page=100"), { izin: "secrets" });
    return new Map((d.secrets || []).map((s) => [s.name, { diperbarui: s.updated_at, dibuat: s.created_at }]));
  }

  /** Mengenkripsi `nilai` di browser dengan kunci publik repositori, lalu menyimpannya sebagai GitHub Secret. */
  async simpanRahasia(nama, nilai) {
    if (!NAMA_RAHASIA.test(nama) || nama.startsWith("GITHUB_")) throw new Error(`Nama kunci tidak sah: ${nama}`);
    if (!nilai) throw new Error("Nilai kunci kosong");
    const kunci = await this._minta("GET", this._rute("/actions/secrets/public-key"), { izin: "secrets" });
    const terenkripsi = segel(new TextEncoder().encode(nilai), dariBase64(kunci.key));
    await this._minta("PUT", this._rute(`/actions/secrets/${nama}`), {
      badan: { encrypted_value: keBase64(terenkripsi), key_id: kunci.key_id }, izin: "secrets",
    });
  }

  async hapusRahasia(nama) {
    if (!NAMA_RAHASIA.test(nama) || nama.startsWith("GITHUB_")) throw new Error(`Nama kunci tidak sah: ${nama}`);
    await this._minta("DELETE", this._rute(`/actions/secrets/${nama}`), { izin: "secrets" });
  }

  /** Menjalankan alur kerja (workflow_dispatch). GitHub membalas tanpa isi, jadi tidak ada ID proses yang dikembalikan. */
  async jalankanAlur(berkas, cabang, masukan = {}) {
    await this._minta("POST", this._rute(`/actions/workflows/${encodeURIComponent(berkas)}/dispatches`), {
      badan: { ref: cabang, inputs: masukan }, izin: "actions",
    });
  }

  /** Proses terakhir sebuah alur kerja (atau null bila belum pernah jalan). */
  async prosesTerakhir(berkas, cabang) {
    const q = cabang ? `&branch=${encodeURIComponent(cabang)}` : "";
    const d = await this._minta("GET", this._rute(`/actions/workflows/${encodeURIComponent(berkas)}/runs?per_page=1${q}`), { izin: "actions" });
    const p = (d.workflow_runs || [])[0];
    return p ? { id: p.id, status: p.status, hasil: p.conclusion, url: p.html_url, dibuat: p.created_at, diperbarui: p.updated_at, pemicu: p.event } : null;
  }
}

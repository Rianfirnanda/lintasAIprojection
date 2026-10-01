import assert from "node:assert/strict";
import test from "node:test";
import { GalatGitHub, KlienGitHub, bacaRepo, dariBase64Teks, keBase64Teks } from "../site/assets/github.js";
import { bukaSegel, buatPasangan } from "../site/vendor/sealedbox/sealedbox.js";

const TOKEN = "github_pat_CONTOH_TOKEN_RAHASIA";

/** fetch palsu: `penangan(url, opsi)` mengembalikan { status, badan, headers }. */
function fetchPalsu(penangan) {
  const f = async (url, opsi) => {
    f.panggilan.push({ url, metode: opsi.method, headers: opsi.headers, badan: opsi.body ? JSON.parse(opsi.body) : undefined });
    const r = await penangan(url, opsi);
    return new Response(r.badan === undefined ? null : JSON.stringify(r.badan), { status: r.status ?? 200, headers: r.headers });
  };
  f.panggilan = [];
  return f;
}
const klien = (ambil) => new KlienGitHub({ token: TOKEN, pemilik: "Rianfirnanda", repo: "lintasAIprojection", ambil });

test("bacaRepo mengenali nama dan alamat GitHub", () => {
  assert.deepEqual(bacaRepo("Rianfirnanda/lintasAIprojection"), { pemilik: "Rianfirnanda", repo: "lintasAIprojection" });
  assert.deepEqual(bacaRepo("https://github.com/Rianfirnanda/lintasAIprojection"), { pemilik: "Rianfirnanda", repo: "lintasAIprojection" });
  assert.deepEqual(bacaRepo("https://github.com/Rianfirnanda/lintasAIprojection.git"), { pemilik: "Rianfirnanda", repo: "lintasAIprojection" });
  assert.deepEqual(bacaRepo("https://github.com/Rianfirnanda/lintasAIprojection/actions"), { pemilik: "Rianfirnanda", repo: "lintasAIprojection" });
  assert.equal(bacaRepo(""), null);
  assert.equal(bacaRepo("hanya-satu-kata"), null);
  assert.equal(bacaRepo("a b/c"), null);
});

test("base64 UTF-8, termasuk yang berisi baris baru seperti balasan GitHub", () => {
  const teks = "Kabupaten Bengkulu Tengah — harga é 日本\n";
  assert.equal(dariBase64Teks(keBase64Teks(teks)), teks);
  const b64 = keBase64Teks(teks).replace(/(.{20})/g, "$1\n");
  assert.equal(dariBase64Teks(b64), teks);
});

test("bacaBerkas: alamat, header, dan hasilnya", async () => {
  const f = fetchPalsu(() => ({ badan: { encoding: "base64", content: `${keBase64Teks('{"a": 1}').replace(/(.{4})/g, "$1\n")}`, sha: "abc123" } }));
  const hasil = await klien(f).bacaBerkas("config/pengaturan.json", "main");
  assert.deepEqual(hasil, { teks: '{"a": 1}', sha: "abc123" });
  const [p] = f.panggilan;
  assert.equal(p.url, "https://api.github.com/repos/Rianfirnanda/lintasAIprojection/contents/config/pengaturan.json?ref=main");
  assert.equal(p.metode, "GET");
  assert.equal(p.headers.Authorization, `Bearer ${TOKEN}`);
  assert.equal(p.headers["Content-Type"], undefined);
});

test("simpanBerkas mengirim isi base64, sha, pesan, dan cabang", async () => {
  const f = fetchPalsu(() => ({ status: 200, badan: { content: { sha: "baru456" }, commit: { html_url: "https://github.com/x/y/commit/c1", sha: "c1" } } }));
  const hasil = await klien(f).simpanBerkas({ path: "config/pengaturan.json", teks: '{"b": "é"}\n', sha: "abc123", pesan: "Ubah pengaturan", cabang: "main" });
  assert.deepEqual(hasil, { sha: "baru456", urlCommit: "https://github.com/x/y/commit/c1", shaCommit: "c1" });
  const p = f.panggilan[0];
  assert.equal(p.metode, "PUT");
  assert.equal(p.headers["Content-Type"], "application/json");
  assert.equal(dariBase64Teks(p.badan.content), '{"b": "é"}\n');
  assert.deepEqual({ ...p.badan, content: "…" }, { message: "Ubah pengaturan", content: "…", sha: "abc123", branch: "main" });
});

test("simpanRahasia mengenkripsi nilai dengan kunci publik repositori sebelum dikirim", async () => {
  const pasangan = buatPasangan();
  const nilai = "AIzaSyContohKunciRahasia_1234567890";
  const f = fetchPalsu((url, opsi) => (opsi.method === "GET"
    ? { badan: { key_id: "kunci-7", key: Buffer.from(pasangan.publicKey).toString("base64") } }
    : { status: 201 }));
  await klien(f).simpanRahasia("GEMINI_API_KEY", nilai);
  assert.equal(f.panggilan.length, 2);
  assert.match(f.panggilan[0].url, /\/actions\/secrets\/public-key$/);
  const put = f.panggilan[1];
  assert.equal(put.metode, "PUT");
  assert.match(put.url, /\/actions\/secrets\/GEMINI_API_KEY$/);
  assert.equal(put.badan.key_id, "kunci-7");
  assert.deepEqual(Object.keys(put.badan).sort(), ["encrypted_value", "key_id"]);
  const dibuka = bukaSegel(Uint8Array.from(Buffer.from(put.badan.encrypted_value, "base64")), pasangan.publicKey, pasangan.secretKey);
  assert.equal(new TextDecoder().decode(dibuka), nilai);
  // nilai asli tidak boleh muncul di mana pun selain dalam bentuk terenkripsi
  assert.ok(!JSON.stringify(f.panggilan).includes(nilai));
});

test("nama kunci dibatasi dan tidak boleh berawalan GITHUB_", async () => {
  const k = klien(fetchPalsu(() => ({ status: 204 })));
  await assert.rejects(() => k.simpanRahasia("gemini", "x"), /tidak sah/);
  await assert.rejects(() => k.simpanRahasia("GITHUB_TOKEN", "x"), /tidak sah/);
  await assert.rejects(() => k.simpanRahasia("A/../B", "x"), /tidak sah/);
  await assert.rejects(() => k.hapusRahasia("../x"), /tidak sah/);
  await assert.rejects(() => k.simpanRahasia("GEMINI_API_KEY", ""), /kosong/);
});

test("daftarRahasia, hapusRahasia, jalankanAlur, dan prosesTerakhir", async () => {
  const f = fetchPalsu((url, opsi) => {
    if (url.includes("/actions/secrets?")) return { badan: { total_count: 1, secrets: [{ name: "GEMINI_API_KEY", created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-02T00:00:00Z" }] } };
    if (url.includes("/runs?")) return { badan: { workflow_runs: [{ id: 9, status: "completed", conclusion: "success", html_url: "https://github.com/x/y/actions/runs/9", created_at: "t1", updated_at: "t2", event: "push" }] } };
    return { status: 204 };
  });
  const k = klien(f);
  assert.deepEqual([...(await k.daftarRahasia())], [["GEMINI_API_KEY", { diperbarui: "2026-09-02T00:00:00Z", dibuat: "2026-09-01T00:00:00Z" }]]);
  await k.hapusRahasia("GEMINI_API_KEY");
  await k.jalankanAlur("ai-data-finder.yml", "main", { komoditas: "cabai", periode: "Oktober 2026" });
  assert.deepEqual(await k.prosesTerakhir("pipeline.yml", "main"),
    { id: 9, status: "completed", hasil: "success", url: "https://github.com/x/y/actions/runs/9", dibuat: "t1", diperbarui: "t2", pemicu: "push" });
  const [, hapus, jalan, runs] = f.panggilan;
  assert.equal(hapus.metode, "DELETE");
  assert.equal(jalan.metode, "POST");
  assert.match(jalan.url, /\/actions\/workflows\/ai-data-finder\.yml\/dispatches$/);
  assert.deepEqual(jalan.badan, { ref: "main", inputs: { komoditas: "cabai", periode: "Oktober 2026" } });
  assert.match(runs.url, /\/actions\/workflows\/pipeline\.yml\/runs\?per_page=1&branch=main$/);
});

test("galat GitHub diubah menjadi pesan yang mudah dipahami", async () => {
  const coba = async (respons, izin = "secrets") => {
    const k = klien(fetchPalsu(() => respons));
    try {
      await k._minta("GET", "/x", { izin });
    } catch (e) {
      return e;
    }
    return null;
  };
  let e = await coba({ status: 401, badan: { message: "Bad credentials" } });
  assert.ok(e instanceof GalatGitHub && e.kode === "token" && /ditolak/.test(e.message));
  e = await coba({ status: 403, badan: { message: "Resource not accessible by personal access token" } });
  assert.equal(e.kode, "izin");
  assert.match(e.message, /Secrets: Read and write/);
  e = await coba({ status: 403, badan: { message: "API rate limit exceeded" }, headers: { "x-ratelimit-remaining": "0" } });
  assert.equal(e.kode, "batas");
  e = await coba({ status: 404, badan: { message: "Not Found" } });
  assert.equal(e.kode, "tidak_ada");
  e = await coba({ status: 409, badan: { message: "sha does not match" } });
  assert.equal(e.kode, "bentrok");
  e = await coba({ status: 422, badan: { message: "Changes must be made through a pull request. Protected branch update failed" } });
  assert.equal(e.kode, "ditolak");
  assert.match(e.message, /dilindungi/);
  e = await coba({ status: 500, badan: { message: "boom" } });
  assert.equal(e.kode, "lain");
  const mati = klien(async () => { throw new TypeError("Failed to fetch"); });
  await assert.rejects(() => mati.pengguna(), (err) => err.kode === "jaringan" && /internet/.test(err.message));
});

test("token tidak pernah muncul di alamat, isi permintaan, atau pesan galat", async () => {
  const f = fetchPalsu((url) => (url.endsWith("/user") ? { badan: { login: "admin" } } : { status: 404, badan: { message: "Not Found" } }));
  const k = klien(f);
  await k.pengguna();
  await assert.rejects(() => k.info(), (err) => !err.message.includes(TOKEN) && !JSON.stringify(err).includes(TOKEN));
  for (const p of f.panggilan) {
    assert.ok(!p.url.includes(TOKEN));
    assert.ok(!JSON.stringify(p.badan ?? "").includes(TOKEN));
  }
});

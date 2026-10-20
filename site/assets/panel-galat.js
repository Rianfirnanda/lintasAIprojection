// Panel "Galat di perangkat pengguna" di Ringkasan Administrator: galat yang muncul di ponsel atau komputer pengguna
// (dicatat galat-klien.js), dikelompokkan per pesan. Dibaca sekali saat beranda dibuka, bukan langsung, supaya hemat kuota.
import { esc } from "./app.js";
import { PERAN } from "./akses.js";
import { kelompokkanGalat } from "./galat-klien.js";

const BATAS_BACA = 50;
const waktuPendek = (n) => (n ? new Date(n).toLocaleString("id-ID", { timeZone: "Asia/Jakarta", day: "numeric", month: "short",
  hour: "2-digit", minute: "2-digit" }).replace(".", ":") : "–");

export async function pasangPanelGalat(el, meta) {
  if (meta?.login !== "firebase") { el.hidden = true; return; }
  const fk = await import("./firebase-klien.js");
  const { fb, db } = await fk.firebaseSiap();

  async function muat() {
    el.innerHTML = `<div class="kartu-kepala"><div><h2>Galat di perangkat pengguna</h2><p>Memuat…</p></div></div>`;
    let daftar = [];
    try {
      const snap = await fb.getDocs(fb.query(fb.collection(db, "lbp_galat"), fb.orderBy("waktu", "desc"), fb.limit(BATAS_BACA)));
      daftar = snap.docs.map((d) => ({ id: d.id, ...d.data() }));
    } catch (e) {
      el.innerHTML = `<div class="kartu-kepala"><div><h2>Galat di perangkat pengguna</h2>
        <p class="kosong">Belum bisa dibaca: ${esc(e.message || e)}</p></div></div>`;
      return;
    }
    const grup = kelompokkanGalat(daftar);
    el.innerHTML = `<div class="kartu-kepala"><div><h2>Galat di perangkat pengguna</h2>
        <p>Masalah tampilan atau tombol yang terjadi di ponsel atau komputer pengguna, dicatat otomatis (paling lama 30 hari).
        ${grup.length ? `${grup.length} jenis masalah dari ${daftar.length} catatan terbaru.` : ""}</p></div>
        <button type="button" class="tombol kecil" data-muat>Muat ulang</button></div>
      ${grup.length ? `<div class="daftar-galat">${grup.map((g, i) => `
        <details class="galat-baris"><summary><b>${esc(g.pesan)}</b>
          <span class="meta-kecil">${g.jumlah} kali · ${g.pengguna.size} pengguna · ${esc([...g.halaman].join(", "))} ·
          ${esc([...g.peramban].join("; "))} · terakhir ${esc(waktuPendek(g.terakhir))}</span></summary>
          <p class="meta-kecil">Peran: ${esc([...g.peran].map((p) => PERAN[p]?.nama || p).join(", "))}${g.sumber ? ` · letak <code>${esc(g.sumber)}</code>` : ""}</p>
          ${g.tumpukan ? `<pre class="galat-tumpukan">${esc(g.tumpukan)}</pre>` : ""}
          <button type="button" class="tombol kecil" data-selesai="${i}">Tandai sudah ditangani (hapus ${g.jumlah} catatan)</button>
        </details>`).join("")}</div>`
      : `<p class="kosong">Tidak ada galat yang tercatat. Semua halaman berjalan normal di perangkat pengguna.</p>`}`;
    el.querySelector("[data-muat]").addEventListener("click", muat);
    el.querySelectorAll("[data-selesai]").forEach((b) => b.addEventListener("click", async () => {
      const g = grup[Number(b.dataset.selesai)];
      b.disabled = true;
      try {
        const batch = fb.writeBatch(db);
        for (const id of g.id) batch.delete(fb.doc(db, "lbp_galat", id));
        await batch.commit();
        muat();
      } catch (e) {
        b.disabled = false;
        b.textContent = `Gagal menghapus: ${e.message || e}`;
      }
    }));
  }
  muat();
}

// Kartu "Harga masuk, sedang diolah" di Beranda: harga yang baru dikirim petugas langsung terlihat (real-time dari
// Firestore), sebelum mesin selesai memeriksa dan memasukkannya ke grafik dan prakiraan.
import { muatJSON, esc, rp } from "./app.js";
import { pantauHargaMasuk } from "./kiriman.js";

export async function pasangHargaMasuk(meta, wadah) {
  const kartu = document.createElement("section");
  kartu.className = "kartu harga-masuk";
  kartu.hidden = true;
  kartu.setAttribute("aria-labelledby", "j-harga-masuk");
  const kpi = wadah.querySelector("#kpi");
  if (kpi) kpi.after(kartu); else wadah.prepend(kartu);

  let master = { varian: [], pasar: [] };
  try { master = await muatJSON("master.json"); } catch { /* nama kode tetap tampil */ }
  const namaVarian = new Map(master.varian.map((v) => [v.kode, v.nama]));
  const namaPasar = new Map((master.pasar || []).map((p) => [p.kode, p.nama]));
  const jamTeks = (d) => (d ? d.toLocaleString("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "–");

  await pantauHargaMasuk(meta.dibuat, (daftar) => {
    kartu.hidden = daftar.length === 0;
    if (!daftar.length) return;
    const pasar = new Set(daftar.map((h) => h.kode_pasar));
    kartu.innerHTML = `<div class="kartu-kepala"><div><h2 id="j-harga-masuk"><span class="titik-langsung" aria-hidden="true"></span>Harga masuk, sedang diolah</h2>
      <p>${daftar.length}${daftar.length >= 200 ? "+" : ""} harga dari ${pasar.size} pasar baru dikirim petugas. Angka ini belum diperiksa;
      grafik, prakiraan, dan peringatan ikut diperbarui otomatis dalam 4 sampai 7 menit.</p></div></div>
      <div class="gulir-tabel"><table><thead><tr><th>Dikirim</th><th>Pasar</th><th>Varian</th><th class="angka">Harga</th><th>Petugas</th></tr></thead>
      <tbody>${daftar.slice(0, 15).map((h) => `<tr><td>${esc(jamTeks(h.diterima))}</td><td>${esc(namaPasar.get(h.kode_pasar) || h.kode_pasar)}</td>
        <td>${esc(namaVarian.get(h.kode_varian) || h.kode_varian)}</td><td class="angka">${rp(h.harga)}${h.satuan && h.satuan !== "kg" ? ` <small>/${esc(h.satuan)}</small>` : ""}</td>
        <td>${esc(h.petugas || "–")}</td></tr>`).join("")}</tbody></table></div>
      ${daftar.length > 15 ? `<p class="meta-kecil" style="margin-top:8px">Menampilkan 15 kiriman terbaru dari ${daftar.length}.</p>` : ""}`;
  }, () => { kartu.remove(); });
}

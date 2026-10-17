// Mode Rapat TPID: layar penuh untuk proyektor atau TV. Lima tampilan berganti otomatis tiap 12 detik dengan huruf besar:
// ringkasan hari ini, kenaikan terbesar, peringatan penting, perkiraan 7 hari, dan menjelang hari raya.
// Tombol: panah kiri/kanan atau spasi untuk pindah, P untuk jeda, Esc untuk keluar. Semua angka dari data situs.
import { muatJSON, esc, rp, persen, angka, tgl } from "./app.js";
import { ikon, gambarKomoditas, selisihHarga, teksSelisih, ringkasHariIni } from "./dashboard.js";

const LAMA_MS = 12000;
let layar = null, jam = null, urutan = 0, jeda = false, tampilan = [], mulai = 0, rafId = 0;

const tandaArah = (x) => (x > 0.5 ? "naik" : x < -0.5 ? "turun" : "datar");

function susunTampilan(ringkasan, sinyal) {
  const v = ringkasan.varian || [];
  const bulanan = (x) => x.perubahan?.bulanan;
  const naik = v.filter((x) => tandaArah(bulanan(x) ?? 0) === "naik"), turun = v.filter((x) => tandaArah(bulanan(x) ?? 0) === "turun");
  const daftar = [];

  daftar.push({ judul: "Ringkasan hari ini", isi: `
    <p class="rp-kalimat">${esc(ringkasHariIni(v, "bulanan").kalimat)}</p>
    <div class="rp-angka-besar">
      <div class="merah"><b class="ringkas-angka">${naik.length}</b><span>harga naik</span></div>
      <div class="hijau"><b class="ringkas-angka">${turun.length}</b><span>harga turun</span></div>
      <div><b class="ringkas-angka">${v.length - naik.length - turun.length}</b><span>stabil</span></div>
      <div class="oranye"><b class="ringkas-angka">${v.filter((x) => x.sinyal).length}</b><span>perlu diwaspadai</span></div>
    </div>
    <p class="rp-catatan">Dibanding sebulan lalu · ${v.length} barang dipantau</p>` });

  const teratas = [...v].filter((x) => (bulanan(x) ?? 0) > 0.5).sort((a, b) => bulanan(b) - bulanan(a)).slice(0, 5);
  if (teratas.length) {
    const maks = Math.max(...teratas.map(bulanan));
    daftar.push({ judul: "Naik paling tinggi dalam sebulan", isi: `<ul class="rp-batang">${teratas.map((x) => {
      const s = selisihHarga(x);
      return `<li>${gambarKomoditas(x.kode)}<span class="rp-nama">${esc(x.nama)}<small>${rp(x.harga_terakhir)}/${esc(x.satuan)}</small></span>
        <span class="rp-isi"><i style="--lebar:${(bulanan(x) / maks) * 100}%"></i></span>
        <b class="merah">${s ? esc(teksSelisih(s.selisih)) : ""}<small>${persen(bulanan(x), 1, true)}</small></b></li>`;
    }).join("")}</ul>` });
  }

  const penting = (sinyal?.sinyal || []).filter((s) => s.aktif && s.keparahan === "tinggi").slice(0, 4);
  daftar.push({ judul: "Peringatan yang perlu ditangani", isi: penting.length ? `<div class="rp-peringatan">${penting.map((s) => `
      <div class="rp-p">${ikon("peringatan", 28)}<div><b>${esc(s.judul)}</b>
        ${s.nilai_aktual != null ? `<span>Harga sekarang ${rp(s.nilai_aktual)}${s.baseline ? ` · normal ${rp(s.baseline)}` : ""}</span>` : `<span>${esc(s.narasi || "")}</span>`}</div></div>`).join("")}</div>`
    : `<p class="rp-kalimat">Tidak ada peringatan penting yang aktif. Semua harga masih dalam pola biasa.</p>` });

  const bergerak = [...v].filter((x) => x.proyeksi_h7).sort((a, b) => Math.abs(bulanan(b) ?? 0) - Math.abs(bulanan(a) ?? 0)).slice(0, 6);
  if (bergerak.length) {
    daftar.push({ judul: "Perkiraan 7 hari ke depan", isi: `<table class="rp-tabel"><thead><tr><th>Barang</th><th>Sekarang</th><th>7 hari lagi</th><th>Kisaran</th></tr></thead>
      <tbody>${bergerak.map((x) => {
        const h = x.proyeksi_h7, beda = h.prediksi - x.harga_terakhir;
        return `<tr><td>${esc(x.nama)}</td><td>${rp(x.harga_terakhir)}</td>
          <td class="${beda > 0 ? "merah" : beda < 0 ? "hijau" : ""}">${rp(h.prediksi)}${beda ? ` ${beda > 0 ? "▲" : "▼"}` : ""}</td>
          <td class="rp-redup">${rp(h.bawah)} sampai ${rp(h.atas)}</td></tr>`;
      }).join("")}</tbody></table>
      <p class="rp-catatan">Perkiraan bukan angka resmi. Kisaran: harga sebenarnya biasanya jatuh di antara dua angka ini.</p>` });
  }

  const h = ringkasan.hari_raya || {}, b = h.berikutnya;
  if (b) {
    daftar.push({ judul: "Menjelang hari raya", isi: `<div class="rp-hariraya"><div class="rp-h"><b class="ringkas-angka">${b.hari_menuju}</b><span>hari lagi</span></div>
      <div><p class="rp-kalimat">${esc(b.nama)}, ${esc(tgl(b.tanggal, true))}${b.status !== "pasti" ? " (perkiraan)" : ""}</p>
      ${(h.profil_top || []).length ? `<p class="rp-catatan">Kenaikan tertinggi pada hari raya sebelumnya:</p><ul class="rp-daftar">${h.profil_top.slice(0, 5)
        .map((p) => `<li>${esc(p.nama)} <b class="merah">${persen(p.kenaikan_puncak_persen, 0, true)}</b></li>`).join("")}</ul>` : ""}</div></div>` });
  }
  return daftar;
}

function gambar() {
  const t = tampilan[urutan];
  layar.querySelector(".rp-judul").textContent = t.judul;
  const isi = layar.querySelector(".rp-isi-utama");
  isi.classList.remove("rp-masuk");
  void isi.offsetWidth;
  isi.innerHTML = t.isi;
  isi.classList.add("rp-masuk");
  layar.querySelectorAll(".rp-titik button").forEach((b, i) => b.setAttribute("aria-current", String(i === urutan)));
  mulai = performance.now();
}

function pindah(arah) {
  urutan = (urutan + arah + tampilan.length) % tampilan.length;
  gambar();
}

function putar(kini) {
  const bar = layar?.querySelector(".rp-kemajuan i");
  if (!layar) return;
  if (jeda) { mulai = kini - (Number(bar?.dataset.t) || 0); } else {
    const t = kini - mulai;
    if (bar) { bar.style.width = `${Math.min(100, (t / LAMA_MS) * 100)}%`; bar.dataset.t = t; }
    if (t >= LAMA_MS) pindah(1);
  }
  rafId = requestAnimationFrame(putar);
}

function tutup() {
  cancelAnimationFrame(rafId);
  clearInterval(jam);
  document.removeEventListener("keydown", tombol);
  if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
  layar?.remove();
  layar = null;
  document.documentElement.classList.remove("rincian-terbuka");
}

function tombol(e) {
  if (!layar) return;
  if (e.key === "Escape") { e.preventDefault(); tutup(); }
  else if (e.key === "ArrowRight" || e.key === " " || e.key === "PageDown") { e.preventDefault(); pindah(1); }
  else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); pindah(-1); }
  else if (e.key.toLowerCase() === "p") { e.preventDefault(); aturJeda(!jeda); }
}

function aturJeda(nilai) {
  jeda = nilai;
  const b = layar.querySelector("[data-jeda]");
  b.innerHTML = jeda ? "▶ Lanjut" : "❚❚ Jeda";
  b.setAttribute("aria-pressed", String(jeda));
}

export async function bukaModeRapat() {
  if (layar) return;
  const [ringkasan, sinyal] = await Promise.all([muatJSON("ringkasan.json"), muatJSON("sinyal.json").catch(() => null)]);
  tampilan = susunTampilan(ringkasan, sinyal);
  urutan = 0; jeda = false;
  layar = document.createElement("div");
  layar.className = "rapat";
  layar.setAttribute("role", "dialog");
  layar.setAttribute("aria-modal", "true");
  layar.setAttribute("aria-label", "Mode Rapat TPID");
  layar.innerHTML = `
    <header class="rp-kepala"><span class="rp-merek">Takar Pangan 10•21 · Kabupaten Bengkulu Tengah</span><h1 class="rp-judul"></h1>
      <span class="rp-jam"></span></header>
    <main class="rp-isi-utama" aria-live="polite"></main>
    <footer class="rp-kaki">
      <div class="rp-titik">${tampilan.map((t, i) => `<button type="button" data-ke="${i}" aria-label="${esc(t.judul)}"></button>`).join("")}</div>
      <div class="rp-kemajuan"><i></i></div>
      <div class="rp-alat"><button type="button" data-mundur aria-label="Sebelumnya">◀</button><button type="button" data-jeda aria-pressed="false">❚❚ Jeda</button>
        <button type="button" data-maju aria-label="Berikutnya">▶</button><button type="button" data-keluar>Keluar (Esc)</button></div>
    </footer>`;
  document.body.append(layar);
  document.documentElement.classList.add("rincian-terbuka");
  layar.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.hasAttribute("data-keluar")) tutup();
    else if (b.hasAttribute("data-maju")) pindah(1);
    else if (b.hasAttribute("data-mundur")) pindah(-1);
    else if (b.hasAttribute("data-jeda")) aturJeda(!jeda);
    else if (b.dataset.ke) { urutan = Number(b.dataset.ke); gambar(); }
  });
  document.addEventListener("keydown", tombol);
  const tulisJam = () => {
    const s = new Date().toLocaleString("id-ID", { timeZone: "Asia/Jakarta", weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
    layar.querySelector(".rp-jam").textContent = `${s} WIB`;
  };
  tulisJam();
  jam = setInterval(tulisJam, 30000);
  layar.requestFullscreen?.().catch(() => {});
  document.addEventListener("fullscreenchange", function keluarLayarPenuh() {
    if (!document.fullscreenElement) { document.removeEventListener("fullscreenchange", keluarLayarPenuh); }
  });
  gambar();
  rafId = requestAnimationFrame(putar);
  layar.querySelector("[data-maju]").focus();
}

export const _uji = { susunTampilan, angka };

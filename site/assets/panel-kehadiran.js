// Panel "Pengguna aktif dan lokasi" di Ringkasan Administrator: siapa yang sedang memakai aplikasi, dari mana (bila
// pengguna membagikan lokasi), dan log aktivitas (masuk, membuka halaman, keluar). Diperbarui langsung dari Firestore.
import { esc } from "./app.js";
import { PERAN } from "./akses.js";
import { ind } from "./peran.js";
import { susunBaris, hitung, berapaLama, MENIT_AKTIF, MENIT_DIAM, SIMPAN_HARI } from "./kehadiran.js";

const AKSI = { masuk: "Masuk", buka: "Membuka halaman", keluar: "Keluar", lokasi_dibagikan: "Mulai berbagi lokasi", lokasi_dihentikan: "Tidak membagikan lokasi" };
const WARNA = { aktif: "hijau", diam: "oranye", tidak: "abu" };
const PUSAT = [-3.72, 102.45];

const waktuLengkap = (t) => {
  const d = t?.toDate ? t.toDate() : t ? new Date(t) : null;
  return d ? d.toLocaleString("id-ID", { timeZone: "Asia/Jakarta", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).replace(".", ":") : "–";
};
const teksLokasi = (l) => (l ? `${l.lat.toLocaleString("id-ID", { maximumFractionDigits: 5 })}, ${l.lon.toLocaleString("id-ID", { maximumFractionDigits: 5 })}` : "");
const namaPeran = (p) => PERAN[p]?.nama || p || "–";

const keteranganIzin = { ya: "", tidak: "tidak dibagikan", ditolak: "diblokir browser", belum: "belum memilih" };

export async function pasangPanelKehadiran(el, meta) {
  if (meta?.login !== "firebase") {
    el.innerHTML = `<div class="kartu-kepala"><div><h2>Pengguna aktif dan lokasi</h2>
      <p>Tersedia setelah situs memakai login Google (Firebase). Dengan akun contoh, aktivitas tidak dicatat.</p></div></div>`;
    return;
  }
  let akun = [], kehadiran = [], aktivitas = [], saring = "semua", tampil = "peta", peta = null, lapisan = null, galat = "", pasPeta = "", kunciPeta = "", titikPeta = [];
  el.innerHTML = `<div class="kartu-kepala"><div><h2>Pengguna aktif dan lokasi</h2>
      <p>Diperbarui langsung. Aktif: dipakai dalam ${MENIT_AKTIF} menit terakhir. Diam: terbuka tetapi tidak dipakai. Lokasi hanya dari pengguna yang memilih membagikannya.</p></div>
      <div class="segmen" role="group" aria-label="Tampilan">
        <button type="button" data-tampil="peta" aria-pressed="true">Peta</button>
        <button type="button" data-tampil="daftar" aria-pressed="false">Daftar</button>
        <button type="button" data-tampil="log" aria-pressed="false">Log aktivitas</button></div></div>
    <div class="ind-baris hadir-angka"></div>
    <div class="chip-baris hadir-saring" role="group" aria-label="Saring peran"></div>
    <div class="hadir-isi">
      <div class="hadir-peta" id="peta-hadir" role="region" aria-label="Peta posisi pengguna"></div>
      <div class="hadir-daftar" hidden></div>
      <div class="hadir-log" hidden></div>
    </div>`;
  const angkaEl = el.querySelector(".hadir-angka"), saringEl = el.querySelector(".hadir-saring");
  const petaEl = el.querySelector(".hadir-peta"), daftarEl = el.querySelector(".hadir-daftar"), logEl = el.querySelector(".hadir-log");

  const lolos = (peran) => saring === "semua" || peran === saring;

  function gambarAngka(baris) {
    const n = hitung(baris);
    angkaEl.innerHTML = ind({ i: "orang", warna: "hijau", label: "Aktif sekarang", nilai: n.aktif, kecil: "orang", sub: `dipakai dalam ${MENIT_AKTIF} menit terakhir`, warnaNilai: "hijau" }) +
      ind({ i: "jam", warna: "oranye", label: "Diam", nilai: n.diam, kecil: "orang", sub: `terbuka tapi tidak dipakai (sampai ${MENIT_DIAM} menit)` }) +
      ind({ i: "orang", label: "Tidak aktif", nilai: n.tidak, kecil: "orang", sub: "keluar atau lama tidak membuka" }) +
      ind({ i: "pin", label: "Berbagi lokasi", nilai: n.lokasi, kecil: `dari ${baris.length}`, sub: "akun aktif", meter: baris.length ? (n.lokasi / baris.length) * 100 : 0 });
  }

  function gambarSaring(baris) {
    const peranAda = [...new Set(baris.map((b) => b.peran))].filter(Boolean);
    saringEl.innerHTML = [["semua", "Semua"], ...peranAda.map((p) => [p, namaPeran(p)])].map(([k, nama]) => {
      const jml = k === "semua" ? baris.length : baris.filter((b) => b.peran === k).length;
      return `<button type="button" class="chip-saring" data-saring="${esc(k)}" aria-pressed="${k === saring}">${esc(nama)} <small>${jml}</small></button>`;
    }).join("");
  }

  function gambarPeta(baris) {
    if (!window.L) {
      import("./app.js").then((m) => m.muatLeaflet()).then(() => gambarPeta(baris)).catch(() => { petaEl.innerHTML = `<p class="kosong">Peta belum bisa dimuat.</p>`; });
      return;
    }
    if (!peta) {
      peta = L.map(petaEl, { scrollWheelZoom: false }).setView(PUSAT, 9);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "© kontributor OpenStreetMap" }).addTo(peta);
      lapisan = L.layerGroup().addTo(peta);
    }
    lapisan.clearLayers();
    const titik = baris.filter((b) => b.lokasi && lolos(b.peran));
    for (const b of titik) {
      const { lat, lon, akurasi, perkiraan } = b.lokasi;
      if (perkiraan || akurasi > 150) L.circle([lat, lon], { radius: akurasi, weight: 1, opacity: 0.4, fillOpacity: 0.06, className: `lingkar-hadir ${WARNA[b.s.kode]}` }).addTo(lapisan);
      const m = L.marker([lat, lon], {
        icon: L.divIcon({ className: "titik-hadir-bungkus", html: `<span class="titik-hadir ${WARNA[b.s.kode]}">${esc((namaPeran(b.peran) || "?").charAt(0))}</span>`, iconSize: [26, 26] }),
        title: `${b.nama} · ${namaPeran(b.peran)} · ${b.s.label}`, keyboard: true,
      }).addTo(lapisan);
      const isi = document.createElement("div");
      isi.className = "popup-hadir";
      isi.innerHTML = `<strong>${esc(b.nama)}</strong><div>${esc(namaPeran(b.peran))} · <span class="${WARNA[b.s.kode]}">${b.s.label}</span> · ${esc(berapaLama(b.s.menit))}</div>
        <div>Membuka: ${esc(b.k?.judul || b.k?.halaman || "–")}</div>
        <div>${perkiraan ? "Perkiraan, sekitar 1 km" : `Tepat, selisih sekitar ${akurasi} m`} · lokasi ${esc(waktuLengkap(b.k?.lokasi_waktu))}</div>
        <a href="https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=16/${lat}/${lon}" target="_blank" rel="noopener">Buka di peta besar →</a>`;
      m.bindPopup(isi);
    }
    // peta hanya menyesuaikan diri saat isinya berganti (saring lain atau orang baru), supaya zoom admin tidak direset tiap menit
    titikPeta = titik.map((b) => [b.lokasi.lat, b.lokasi.lon]);
    kunciPeta = `${saring}|${titik.map((b) => b.uid).sort().join(",")}`;
    petaEl.dataset.kosong = titik.length ? "" : "Belum ada pengguna yang membagikan lokasi.";
    requestAnimationFrame(pasKanPeta);
  }

  // Peta yang dibuat saat tab beranda lain sedang tampil berukuran nol; arahkan ulang begitu terlihat.
  function pasKanPeta() {
    if (!peta || !petaEl.clientWidth) return;
    peta.invalidateSize();
    if (titikPeta.length && kunciPeta !== pasPeta) {
      peta.fitBounds(titikPeta, { padding: [40, 40], maxZoom: 14 });
      pasPeta = kunciPeta;
    }
  }

  function gambarDaftar(baris) {
    const isi = baris.filter((b) => lolos(b.peran));
    daftarEl.innerHTML = isi.length ? `<div class="gulir-tabel tabel-menempel" style="max-height:440px"><table>
      <thead><tr><th>Nama</th><th>Peran</th><th>Status</th><th>Sedang membuka</th><th>Lokasi</th><th>Perangkat</th><th>Terakhir aktif</th></tr></thead>
      <tbody>${isi.map((b) => `<tr>
        <td><b>${esc(b.nama)}</b><br><small>${esc(b.email || "")}</small></td>
        <td>${esc(namaPeran(b.peran))}</td>
        <td><span class="titik-status ${WARNA[b.s.kode]}"></span> ${b.s.label}</td>
        <td>${b.s.kode === "tidak" ? "–" : esc(b.k?.judul || b.k?.halaman || "–")}</td>
        <td>${b.lokasi ? `<button type="button" class="tautan-tombol" data-ke="${esc(b.uid)}">${esc(teksLokasi(b.lokasi))}</button><br><small>${b.lokasi.perkiraan ? "perkiraan ±1 km" : `±${b.lokasi.akurasi} m`}${b.s.kode === "tidak" ? " · lokasi terakhir" : ""}</small>`
          : `<small>${esc(keteranganIzin[b.izin] || "–")}</small>`}</td>
        <td>${esc(b.k?.perangkat || "–")}</td>
        <td>${esc(berapaLama(b.s.menit))}<br><small>${esc(waktuLengkap(b.k?.terakhir_aktif))}</small></td></tr>`).join("")}</tbody></table></div>`
      : `<p class="kosong">Belum ada akun aktif untuk peran ini.</p>`;
  }

  function gambarLog() {
    const isi = aktivitas.filter((a) => lolos(a.peran));
    logEl.innerHTML = `<div class="hadir-log-kepala"><p class="sub">${isi.length} catatan terbaru. Catatan lebih dari ${SIMPAN_HARI} hari terhapus otomatis.</p>
        <button type="button" class="tombol" data-unduh ${isi.length ? "" : "disabled"}>Unduh CSV</button></div>` +
      (isi.length ? `<div class="gulir-tabel tabel-menempel" style="max-height:440px"><table>
      <thead><tr><th>Waktu</th><th>Nama</th><th>Peran</th><th>Kegiatan</th><th>Halaman</th><th>Lokasi</th></tr></thead>
      <tbody>${isi.map((a) => `<tr><td>${esc(waktuLengkap(a.waktu))}</td><td>${esc(a.nama)}</td><td>${esc(namaPeran(a.peran))}</td>
        <td>${esc(AKSI[a.aksi] || a.aksi)}${a.rincian && a.aksi !== "buka" ? `<br><small>${esc(a.rincian)}</small>` : ""}</td>
        <td>${esc(a.aksi === "buka" && a.rincian ? a.rincian : a.halaman)}</td>
        <td>${a.lokasi ? `${esc(teksLokasi(a.lokasi))}${a.lokasi.perkiraan ? " <small>(±1 km)</small>" : ""}` : "–"}</td></tr>`).join("")}</tbody></table></div>`
        : `<p class="kosong">Belum ada aktivitas tercatat.</p>`);
  }

  function gambar() {
    if (galat) { el.querySelector(".hadir-isi").innerHTML = `<p class="pesan peringatan">${esc(galat)}</p>`; return; }
    const baris = susunBaris(akun, kehadiran);
    gambarAngka(baris);
    gambarSaring(baris);
    petaEl.hidden = tampil !== "peta";
    daftarEl.hidden = tampil !== "daftar";
    logEl.hidden = tampil !== "log";
    if (tampil === "peta") gambarPeta(baris);
    if (tampil === "daftar") gambarDaftar(baris);
    if (tampil === "log") gambarLog();
  }

  function unduhCsv() {
    const sel = (x) => `"${String(x ?? "").replace(/"/g, '""')}"`;
    const baris = [["waktu", "nama", "peran", "kegiatan", "halaman", "lat", "lon", "perkiraan"].join(","),
      ...aktivitas.filter((a) => lolos(a.peran)).map((a) => [waktuLengkap(a.waktu), a.nama, namaPeran(a.peran), AKSI[a.aksi] || a.aksi,
        a.aksi === "buka" && a.rincian ? a.rincian : a.halaman, a.lokasi?.lat, a.lokasi?.lon, a.lokasi ? (a.lokasi.perkiraan ? "ya" : "tidak") : ""].map(sel).join(","))];
    const url = URL.createObjectURL(new Blob(["﻿" + baris.join("\n")], { type: "text/csv;charset=utf-8" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `log-aktivitas-${new Date().toISOString().slice(0, 10)}.csv` });
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  el.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.tampil) {
      tampil = b.dataset.tampil;
      el.querySelectorAll("[data-tampil]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      gambar();
    } else if (b.dataset.saring) { saring = b.dataset.saring; gambar(); }
    else if (b.hasAttribute("data-unduh")) unduhCsv();
    else if (b.dataset.ke) {
      const t = susunBaris(akun, kehadiran).find((x) => x.uid === b.dataset.ke);
      if (!t?.lokasi) return;
      tampil = "peta";
      el.querySelectorAll("[data-tampil]").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.tampil === "peta")));
      gambar();
      peta?.setView([t.lokasi.lat, t.lokasi.lon], t.lokasi.perkiraan ? 13 : 16);
      lapisan?.eachLayer((l) => { if (l.getLatLng && l.options.title?.startsWith(`${t.nama} ·`)) l.openPopup(); });
      petaEl.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });

  new ResizeObserver(() => pasKanPeta()).observe(petaEl);
  const salah = (e) => { galat = e?.code === "permission-denied" ? "Akun ini tidak punya izin melihat aktivitas pengguna." : `Data aktivitas belum bisa dimuat: ${e?.message || e}`; gambar(); };
  gambar();
  try {
    const fk = await import("./firebase-klien.js");
    const k = await import("./kehadiran.js");
    await fk.pantauSemuaAkun((d) => { akun = d; gambar(); }, salah);
    await k.pantauKehadiran((d) => { kehadiran = d; gambar(); }, salah);
    await k.pantauAktivitas((d) => { aktivitas = d; if (tampil === "log") gambar(); }, salah);
  } catch (e) { salah(e); }
  // status (aktif, diam, tidak aktif) bergeser seiring waktu walau tidak ada data baru
  setInterval(() => { if (!document.hidden && tampil !== "log") gambar(); }, 60e3);
}

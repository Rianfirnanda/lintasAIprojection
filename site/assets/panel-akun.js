// Panel akun Firebase (halaman Pengguna): setujui atau tolak pendaftar, atur peran dan izin halaman, nonaktifkan,
// aktifkan lagi, hapus, dan lihat jejak tindakan. Daftar diperbarui langsung (real-time).
// Bisa dipakai peran Administrator dan orang yang diberi halaman Pengguna. Hanya peran Administrator yang bisa
// memberi atau mencabut hak admin (peran Administrator, halaman Pengaturan/Pengguna). Semua perubahan tetap
// diperiksa aturan Firestore di server.
import { esc } from "./app.js";
import { ikon } from "./dashboard.js";
import { PERAN, URUT_PERAN, DAFTAR_HALAMAN, HALAMAN_ADMIN, menuPeran, sesi } from "./akses.js";
import { ind } from "./peran.js";

const fk = await import("./firebase-klien.js");

const TAB = [
  ["menunggu", "Menunggu persetujuan"],
  ["aktif", "Aktif"],
  ["lain", "Ditolak dan nonaktif"],
];
const LABEL_STATUS = { menunggu: ["Menunggu", "sedang"], aktif: ["Aktif", "baik"], ditolak: ["Ditolak", "tinggi"], nonaktif: ["Nonaktif", "polos"] };
const LABEL_AKSI = { setujui: "menyetujui", tolak: "menolak", ubah: "mengubah", nonaktifkan: "menonaktifkan", aktifkan: "mengaktifkan lagi", hapus: "menghapus",
  hak_akses: "mengubah tabel hak akses" };
const adminSaya = sesi()?.peran === "admin";
const PERAN_PILIHAN = URUT_PERAN.filter((k) => adminSaya || k !== "admin");
/** Akun yang memegang hak admin (sama dengan hakAdmin() di aturan Firestore). */
const hakAdmin = (a) => a.peran === "admin" || (Array.isArray(a.halaman) && a.halaman.some((h) => HALAMAN_ADMIN.includes(h)));

const FORMAT_WAKTU = new Intl.DateTimeFormat("id-ID", { timeZone: "Asia/Jakarta", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
const tanggal = (t) => {
  const d = t?.toDate?.();
  return d ? `${FORMAT_WAKTU.format(d)} WIB` : "baru saja";
};
/** Tabel hak akses per peran dari Firestore (null = bawaan). Diisi oleh pasangPanelAkun. */
let tabelAkses = null;
const bawaanPeran = (peran) => {
  const m = menuPeran(peran, peran !== "admin" ? tabelAkses?.[peran] ?? null : null);
  return [...m.utama, ...m.lainnya].map((x) => x.href);
};
/** Halaman yang bisa dicentang. Halaman admin hanya bisa diberikan oleh peran Administrator. */
const halamanUntuk = () => DAFTAR_HALAMAN.filter((h) => adminSaya || !HALAMAN_ADMIN.includes(h.href));

export async function pasangPanelAkun({ wadah, ket, ringkas, jejak, kartuJejak }) {
  const uidSaya = (await fk.penggunaKini())?.uid || sesi()?.uid;
  let akun = [];
  let tab = "menunggu";
  let tabDipilih = false; // tab sudah ditentukan (otomatis sekali, atau dipilih admin)
  const draf = {}; // perubahan yang belum disimpan per akun: { peran, mode: "bawaan"|"atur", halaman: Set }

  ket.textContent = "Akun Google yang mendaftar. Setujui dan beri peran sebelum mereka bisa masuk.";
  wadah.innerHTML = `<div class="segmen tab-akun" role="group" aria-label="Kelompok akun" id="tab-akun"></div>
    <div id="daftar-akun" class="daftar-akun"><p class="kosong">Memuat akun…</p></div>`;
  const elTab = wadah.querySelector("#tab-akun");
  const elDaftar = wadah.querySelector("#daftar-akun");

  const kelompok = (a) => (a.status === "menunggu" ? "menunggu" : a.status === "aktif" ? "aktif" : "lain");
  const hitung = (k) => akun.filter((a) => kelompok(a) === k).length;

  function renderRingkas() {
    const n = hitung("menunggu");
    ringkas.innerHTML = [
      ind({ i: "jam", warna: n ? "oranye" : "hijau", label: "Menunggu persetujuan", nilai: n, kecil: "akun", sub: n ? "perlu ditinjau" : "tidak ada antrean", warnaNilai: n ? "oranye" : "" }),
      ind({ i: "orang", warna: "hijau", label: "Akun aktif", nilai: hitung("aktif"), kecil: "akun", sub: `${akun.filter((a) => a.status === "aktif" && a.peran === "admin").length} admin` }),
      ind({ i: "kurang", label: "Ditolak atau nonaktif", nilai: hitung("lain"), kecil: "akun", sub: "tidak bisa masuk" }),
      ind({ i: "gembokPerisai", warna: "hijau", label: "Cara masuk", nilai: "Google", sub: "lewat Firebase, disetujui admin" }),
    ].join("");
  }

  function renderTab() {
    elTab.innerHTML = TAB.map(([k, label]) => `<button type="button" data-tab="${k}" aria-pressed="${k === tab}">${label} <span class="hitung-tab">${hitung(k)}</span></button>`).join("");
  }

  function drafUntuk(a) {
    if (!draf[a.uid]) {
      const halaman = Array.isArray(a.halaman) ? a.halaman : null;
      draf[a.uid] = { peran: a.peran || "", mode: halaman ? "atur" : "bawaan", halaman: new Set(halaman || bawaanPeran(a.peran || "masyarakat")) };
    }
    return draf[a.uid];
  }

  function berubah(a) {
    const d = draf[a.uid];
    if (!d) return false;
    const halamanBaru = d.mode === "atur" ? [...d.halaman].sort() : null;
    const halamanLama = Array.isArray(a.halaman) ? [...a.halaman].sort() : null;
    return d.peran !== (a.peran || "") || JSON.stringify(halamanBaru) !== JSON.stringify(halamanLama);
  }

  function htmlIzin(a, d) {
    const peran = d.peran || "masyarakat";
    const bawaan = new Set(bawaanPeran(peran));
    const daftar = halamanUntuk();
    const atur = d.mode === "atur";
    return `<fieldset class="izin-akun">
      <legend>Izin halaman</legend>
      <div class="pilih-mode">
        <label><input type="radio" name="mode-${esc(a.uid)}" value="bawaan" data-f="mode" ${atur ? "" : "checked"}> Ikuti peran</label>
        <label><input type="radio" name="mode-${esc(a.uid)}" value="atur" data-f="mode" ${atur ? "checked" : ""}> Atur sendiri</label>
      </div>
      <div class="kelompok-centang">${daftar.map((h) => {
        const centang = h.href === "index.html" || (atur ? d.halaman.has(h.href) : bawaan.has(h.href));
        const kunci = h.href === "index.html" || !atur;
        const admin = HALAMAN_ADMIN.includes(h.href);
        return `<label class="chip-centang${admin ? " chip-admin" : ""}" ${admin ? 'title="Memberi hak admin"' : ""}><input type="checkbox" data-f="halaman" value="${esc(h.href)}" ${centang ? "checked" : ""} ${kunci ? "disabled" : ""}><span>${esc(h.label)}${admin ? " (admin)" : ""}</span></label>`;
      }).join("")}</div>
      ${peran !== "admin" && atur && HALAMAN_ADMIN.some((h) => d.halaman.has(h)) ? `<p class="catatan-admin">${ikon("gembokPerisai", 15)} Orang ini akan punya hak admin:
        ${d.halaman.has("pengaturan.html") ? "mengubah pengaturan sistem, kunci, dan menjalankan proses" : ""}${d.halaman.has("pengaturan.html") && d.halaman.has("pengguna.html") ? ", serta " : ""}${d.halaman.has("pengguna.html") ? "menyetujui dan mengatur akun biasa" : ""}.
        Mengangkat atau mencopot admin tetap hanya bisa dilakukan peran Administrator.</p>` : ""}
    </fieldset>`;
  }

  function htmlKartu(a) {
    const saya = a.uid === uidSaya;
    const d = drafUntuk(a);
    const [label, kelas] = LABEL_STATUS[a.status] || [a.status, "polos"];
    const pilihPeran = `<label class="pilih-peran">Peran
      <select data-f="peran"><option value="" ${d.peran ? "" : "selected"} disabled>Pilih peran</option>
        ${PERAN_PILIHAN.map((k) => `<option value="${k}" ${d.peran === k ? "selected" : ""}>${esc(PERAN[k].nama)}</option>`).join("")}</select></label>`;
    let atur = "", aksi = "";
    if (saya) {
      atur = `<p class="meta-kecil">Ini akun Anda. Peran dan status akun sendiri tidak bisa diubah dari sini, supaya admin tidak terkunci.</p>`;
    } else if (!adminSaya && hakAdmin(a)) {
      atur = `<p class="meta-kecil">Akun ini memegang hak admin, jadi hanya peran Administrator yang bisa mengubahnya.</p>`;
    } else if (a.status === "menunggu") {
      atur = pilihPeran + htmlIzin(a, d);
      aksi = `<button class="tombol utama-aksi" type="button" data-aksi="setujui" ${d.peran ? "" : "disabled"}>${ikon("centang", 16)} Setujui</button>
        <button class="tombol" type="button" data-aksi="tolak">Tolak</button>`;
    } else if (a.status === "aktif") {
      atur = pilihPeran + htmlIzin(a, d);
      aksi = `<button class="tombol utama-aksi" type="button" data-aksi="ubah" ${berubah(a) && d.peran ? "" : "disabled"}>Simpan perubahan</button>
        <button class="tombol" type="button" data-aksi="nonaktifkan">Nonaktifkan</button>`;
    } else {
      atur = pilihPeran + htmlIzin(a, d);
      aksi = `<button class="tombol utama-aksi" type="button" data-aksi="aktifkan" ${d.peran ? "" : "disabled"}>Aktifkan</button>
        <button class="tautan-bahaya" type="button" data-aksi="hapus">Hapus akun</button>`;
    }
    const keputusan = a.diputus_oleh ? ` · terakhir diatur ${esc(a.diputus_oleh)}` : "";
    return `<article class="akun-kartu${saya ? " akun-saya" : ""}" data-uid="${esc(a.uid)}">
      <div class="akun-atas">
        ${a.foto ? `<img class="akun-foto" src="${esc(a.foto)}" alt="" width="40" height="40" referrerpolicy="no-referrer" loading="lazy">` : `<span class="akun-foto kosong-foto">${ikon("orang", 20)}</span>`}
        <div class="akun-nama"><b>${esc(a.nama || a.email)}${saya ? " <small>(Anda)</small>" : ""}</b><span>${esc(a.email || "")}</span>
          <span class="meta-kecil">Daftar ${esc(tanggal(a.dibuat))}${a.status === "aktif" && a.peran ? ` · ${esc(PERAN[a.peran]?.nama || a.peran)}` : ""}${keputusan}</span></div>
        <span class="lencana ${kelas}">${esc(label)}</span>
      </div>
      ${atur ? `<div class="akun-atur">${atur}</div>` : ""}
      ${aksi ? `<div class="akun-aksi">${aksi}</div>` : ""}
      <p class="akun-pesan" role="status"></p>
    </article>`;
  }

  function renderDaftar() {
    const isi = akun.filter((a) => kelompok(a) === tab);
    elDaftar.innerHTML = isi.length ? isi.map(htmlKartu).join("") : `<p class="kosong">${
      tab === "menunggu" ? "Tidak ada akun yang menunggu persetujuan." : tab === "aktif" ? "Belum ada akun aktif." : "Tidak ada akun yang ditolak atau nonaktif."}</p>`;
  }

  const renderSemua = () => { renderRingkas(); renderTab(); renderDaftar(); };

  elTab.addEventListener("click", (e) => {
    const b = e.target.closest("[data-tab]");
    if (!b) return;
    tabDipilih = true;
    tab = b.dataset.tab;
    renderTab(); renderDaftar();
  });

  elDaftar.addEventListener("change", (e) => {
    const kartu = e.target.closest(".akun-kartu");
    const a = akun.find((x) => x.uid === kartu?.dataset.uid);
    if (!a) return;
    const d = drafUntuk(a);
    const f = e.target.dataset.f;
    if (f === "peran") {
      d.peran = e.target.value;
      if (d.mode === "bawaan") d.halaman = new Set(bawaanPeran(d.peran));
      if (!adminSaya) HALAMAN_ADMIN.forEach((h) => d.halaman.delete(h));
    } else if (f === "mode") {
      d.mode = e.target.value;
      if (d.mode === "atur") d.halaman = new Set(bawaanPeran(d.peran || "masyarakat"));
      if (!adminSaya) HALAMAN_ADMIN.forEach((h) => d.halaman.delete(h));
    } else if (f === "halaman") {
      if (e.target.checked) d.halaman.add(e.target.value); else d.halaman.delete(e.target.value);
    }
    kartu.outerHTML = htmlKartu(a);
  });

  elDaftar.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-aksi]");
    if (!b) return;
    const kartu = b.closest(".akun-kartu");
    const a = akun.find((x) => x.uid === kartu.dataset.uid);
    if (!a) return;
    const d = drafUntuk(a);
    const halaman = d.mode === "atur" ? [...new Set(["index.html", ...d.halaman])] : null;
    const namaPeran = PERAN[d.peran]?.nama || d.peran;
    const pesan = kartu.querySelector(".akun-pesan");
    const aksi = b.dataset.aksi;
    if (aksi === "tolak" && !confirm(`Tolak pendaftaran ${a.email}?`)) return;
    if (aksi === "nonaktifkan" && !confirm(`Nonaktifkan akun ${a.email}? Orang ini tidak bisa masuk sampai diaktifkan lagi.`)) return;
    if (aksi === "hapus" && !confirm(`Hapus akun ${a.email}? Kalau orang ini masuk lagi, akunnya kembali menunggu persetujuan.`)) return;
    kartu.querySelectorAll("button, select, input").forEach((x) => { x.disabled = true; });
    pesan.textContent = "Menyimpan…";
    try {
      const rincianIzin = halaman ? `, izin ${halaman.length} halaman` : "";
      if (aksi === "setujui") await fk.ubahAkun(a, { status: "aktif", peran: d.peran, halaman }, "setujui", `${namaPeran}${rincianIzin}`);
      else if (aksi === "tolak") await fk.ubahAkun(a, { status: "ditolak", peran: null, halaman: null }, "tolak");
      else if (aksi === "ubah") await fk.ubahAkun(a, { peran: d.peran, halaman }, "ubah", `${namaPeran}${rincianIzin}`);
      else if (aksi === "nonaktifkan") await fk.ubahAkun(a, { status: "nonaktif" }, "nonaktifkan");
      else if (aksi === "aktifkan") await fk.ubahAkun(a, { status: "aktif", peran: d.peran, halaman }, "aktifkan", `${namaPeran}${rincianIzin}`);
      else if (aksi === "hapus") await fk.hapusAkun(a);
      delete draf[a.uid];
      // Daftar diperbarui sendiri lewat pemantauan Firestore.
    } catch (err) {
      console.error(err);
      pesan.textContent = fk.pesanGalat(err);
      pesan.classList.add("galat");
      kartu.querySelectorAll("button, select, input").forEach((x) => { x.disabled = false; });
    }
  });

  tabelAkses = await fk.muatTabelAkses();
  fk.pantauTabelAkses((dok) => {
    tabelAkses = dok?.halaman || null;
    // Draf yang mengikuti peran dihitung ulang dari tabel terbaru.
    for (const [uid, d] of Object.entries(draf)) if (d.mode === "bawaan") draf[uid].halaman = new Set(bawaanPeran(d.peran || "masyarakat"));
    if (akun.length) renderDaftar();
  }).catch(() => {});

  await fk.pantauSemuaAkun((daftar, dariSimpanan) => {
    akun = daftar;
    // Saat pertama dimuat, pindah ke tab Aktif bila tidak ada yang menunggu. Tunggu data dari server,
    // karena data awal dari simpanan lokal bisa belum lengkap.
    if (!tabDipilih && !dariSimpanan) {
      tabDipilih = true;
      if (!hitung("menunggu") && hitung("aktif")) tab = "aktif";
    }
    renderSemua();
  }, (err) => {
    console.error(err);
    elDaftar.innerHTML = `<div class="pesan galat">${esc(fk.pesanGalat(err))}</div>`;
  });

  kartuJejak.hidden = false;
  await fk.pantauJejak((daftar) => {
    jejak.innerHTML = daftar.length
      ? `<ul class="daftar-jejak">${daftar.map((j) => `<li><span class="meta-kecil">${esc(tanggal(j.waktu))}</span>
          <span><b>${esc(j.oleh_email)}</b> ${esc(LABEL_AKSI[j.aksi] || j.aksi)}${j.sasaran_email ? ` <b>${esc(j.sasaran_email)}</b>` : ""}${j.rincian ? ` (${esc(j.rincian)})` : ""}</span></li>`).join("")}</ul>`
      : `<p class="kosong">Belum ada tindakan admin.</p>`;
  }, () => { jejak.innerHTML = `<p class="kosong">Jejak belum bisa dimuat.</p>`; });
}

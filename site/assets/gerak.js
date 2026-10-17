// Gerak dan interaksi halus untuk semua halaman (dipasang oleh pasangKerangka di app.js):
//   - sorot: cahaya lembut di kartu mengikuti kursor (hanya perangkat dengan tetikus)
//   - kartu muncul saat digulir, garis grafik kecil tergambar, tombol mengecil sedikit saat ditekan (lihat app.css)
// Gerak yang berpindah tempat dimatikan bila perangkat meminta gerak dikurangi; sorot tetap ada karena tidak bergerak.

export const KARTU_SOROT = ".kartu:not(.kertas), .ind, .dash-kpi-kartu, .dash-panel, .prio, .komo, .peran-kartu, .dsb-kartu, .dsb-k, .kartu-sinyal";

export function pasangGerak() {
  if (matchMedia("(hover: hover) and (pointer: fine)").matches) pasangSorot();
  pasangTanya();
}

/** Ikon "?" (details.tanya): hanya satu terbuka; tertutup saat mengetuk di luar atau menekan Esc; kotaknya digeser supaya
 *  tidak terpotong tepi layar. */
function pasangTanya() {
  const tutupSemua = (kecuali) => document.querySelectorAll("details.tanya[open]").forEach((d) => { if (d !== kecuali) d.open = false; });
  document.addEventListener("toggle", (e) => {
    const d = e.target;
    if (!(d instanceof HTMLDetailsElement) || !d.classList.contains("tanya") || !d.open) return;
    tutupSemua(d);
    const isi = d.querySelector(".tanya-isi");
    if (!isi) return;
    isi.style.marginLeft = "0px";
    const r = isi.getBoundingClientRect(), tepi = 12;
    const geser = r.left < tepi ? tepi - r.left : r.right > innerWidth - tepi ? innerWidth - tepi - r.right : 0;
    isi.style.marginLeft = `${geser}px`;
  }, true);
  document.addEventListener("click", (e) => { if (!e.target.closest?.("details.tanya")) tutupSemua(null); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") tutupSemua(null); });
}

function pasangSorot() {
  let aktif = null, x = 0, y = 0, antre = false;
  const lepas = () => {
    aktif?.style.removeProperty("--mx");
    aktif?.style.removeProperty("--my");
    aktif = null;
  };
  const gambar = () => {
    antre = false;
    if (!aktif) return;
    const r = aktif.getBoundingClientRect();
    aktif.style.setProperty("--mx", `${Math.round(x - r.left)}px`);
    aktif.style.setProperty("--my", `${Math.round(y - r.top)}px`);
  };
  document.addEventListener("pointermove", (e) => {
    const el = e.target.closest?.(KARTU_SOROT) || null;
    if (el !== aktif) { lepas(); aktif = el; }
    if (!aktif) return;
    x = e.clientX; y = e.clientY;
    if (!antre) { antre = true; requestAnimationFrame(gambar); }
  }, { passive: true });
  document.addEventListener("pointerleave", lepas);
}

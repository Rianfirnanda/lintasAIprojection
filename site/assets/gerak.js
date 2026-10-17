// Gerak dan interaksi halus untuk semua halaman (dipasang oleh pasangKerangka di app.js):
//   - sorot: cahaya lembut di kartu mengikuti kursor (hanya perangkat dengan tetikus)
//   - kartu muncul saat digulir, garis grafik kecil tergambar, tombol mengecil sedikit saat ditekan (lihat app.css)
// Gerak yang berpindah tempat dimatikan bila perangkat meminta gerak dikurangi; sorot tetap ada karena tidak bergerak.

export const KARTU_SOROT = ".kartu:not(.kertas), .ind, .dash-kpi-kartu, .dash-panel, .prio, .komo, .peran-kartu, .dsb-kartu, .dsb-k, .kartu-sinyal";

export function pasangGerak() {
  if (matchMedia("(hover: hover) and (pointer: fine)").matches) pasangSorot();
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

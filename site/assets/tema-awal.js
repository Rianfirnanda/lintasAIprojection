// Tema dipasang sebelum halaman digambar supaya layar tidak sempat berkedip terang. Bawaan: gelap.
// Pilihan pengguna (tombol tema di kaki halaman) disimpan di localStorage "tema-tampilan": "light", "dark", atau "auto".
(function () {
  var t = null;
  try { t = localStorage.getItem("tema-tampilan"); } catch (e) { /* penyimpanan diblokir: pakai bawaan */ }
  var gelap = t === "light" ? false : t === "auto" ? window.matchMedia("(prefers-color-scheme: dark)").matches : true;
  if (gelap) document.documentElement.setAttribute("data-theme", "dark");
})();

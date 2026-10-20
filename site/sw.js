// Service worker: formulir input tetap berfungsi tanpa sinyal (wilayah blank spot).
// Versi cache: diganti otomatis dengan kode commit saat situs terbit (pipeline.yml), jadi tiap terbitan memakai cache baru.
const CACHE = "lintas-benteng-v34";
const ASET = [
  "input.html", "masuk.html", "assets/app.css", "assets/tema-awal.js", "assets/app.js", "assets/gerak.js", "assets/kehadiran.js", "assets/status-layanan.js", "assets/akses.js", "assets/peran.js", "assets/dashboard.js", "assets/gambar-komoditas.js", "assets/selisih.js", "assets/rincian.js", "assets/kiriman.js", "assets/firebase-klien.js", "vendor/firebase/firebase.js", "assets/logo-bps.png", "assets/logo-takar-pangan.webp", "assets/logo-lintas-benteng.webp", "assets/logo-takar-pangan-lengkap.webp", "assets/ikon-64.png", "assets/ikon-192.png", "manifest.webmanifest",
  "data/master.json", "data/meta.json",
  ...["plus-jakarta-sans-latin-400-normal", "plus-jakarta-sans-latin-500-normal", "plus-jakarta-sans-latin-600-normal",
      "plus-jakarta-sans-latin-700-normal", "plus-jakarta-sans-latin-800-normal", "ibm-plex-mono-latin-400-normal",
      "ibm-plex-mono-latin-500-normal"].map((f) => `vendor/font/${f}.woff2`),
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASET)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      // Simpanan data per akun (lbp-data-*) diatur halaman sendiri menurut versi data, jangan ikut dihapus.
      .then((kunci) => Promise.all(kunci.filter((k) => k !== CACHE && !k.startsWith("lbp-data-")).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// Berkas yang jarang berubah (huruf, gambar, pustaka grafik dan peta): langsung dari cache supaya halaman cepat tampil,
// lalu diperbarui diam-diam di belakang. Nama cache diganti tiap kali situs terbit, jadi versi lama tidak tertinggal.
const AWET = /\/(vendor\/(font|leaflet)\/|vendor\/chart\.umd\.js$)|\.(woff2|png|webp|jpg|jpeg|svg|ico)$/;

function cacheDulu(e, req) {
  const url = new URL(req.url);
  url.search = "";
  const segar = fetch(req).then((res) => {
    if (res.ok) { const salinan = res.clone(); caches.open(CACHE).then((c) => c.put(url.toString(), salinan)); }
    return res;
  });
  e.waitUntil(segar.catch(() => null));
  e.respondWith(caches.match(url.toString()).then((r) => r || segar));
}

// Selain itu: jaringan dahulu (agar tampilan dan data selalu terbaru), cadangan dari cache saat luring.
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== self.location.origin) return;
  // Video latar dimuat sepotong-sepotong (Range); biarkan browser yang mengurus, jangan disimpan di cache.
  if (req.headers.has("range") || req.destination === "video") return;
  if (AWET.test(new URL(req.url).pathname)) { cacheDulu(e, req); return; }
  // cache: "no-cache" = selalu tanya server dulu apakah ada versi baru (bukan memakai simpanan browser sampai 10 menit).
  const segar = req.mode === "navigate" ? fetch(req.url, { cache: "no-cache", credentials: "same-origin" }) : fetch(req, { cache: "no-cache" });
  e.respondWith(
    segar
      .then((res) => {
        if (res.ok) {
          const salinan = res.clone();
          const url = new URL(req.url);
          url.search = "";
          caches.open(CACHE).then((c) => c.put(url.toString(), salinan));
        }
        return res;
      })
      .catch(() => caches.match(req, { ignoreSearch: true }).then((r) => r || caches.match("input.html"))),
  );
});

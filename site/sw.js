// Service worker: formulir input tetap berfungsi tanpa sinyal (wilayah blank spot).
const CACHE = "lintas-benteng-v20";
const ASET = [
  "input.html", "masuk.html", "assets/app.css", "assets/app.js", "assets/status-layanan.js", "assets/akses.js", "assets/peran.js", "assets/dashboard.js", "assets/gambar-komoditas.js", "assets/selisih.js", "assets/rincian.js", "assets/kiriman.js", "assets/firebase-klien.js", "vendor/firebase/firebase.js", "assets/logo-bps.png", "assets/ikon-64.png", "assets/ikon-192.png", "manifest.webmanifest",
  "data/master.json", "data/meta.json",
  ...["ibm-plex-sans-latin-400-normal", "ibm-plex-sans-latin-400-italic", "ibm-plex-sans-latin-500-normal",
      "ibm-plex-sans-latin-600-normal", "ibm-plex-mono-latin-400-normal", "ibm-plex-mono-latin-500-normal"].map((f) => `vendor/font/${f}.woff2`),
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASET)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((kunci) => Promise.all(kunci.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// Jaringan dahulu (agar tampilan dan data selalu terbaru), cadangan dari cache saat luring.
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== self.location.origin) return;
  // Video latar dimuat sepotong-sepotong (Range); biarkan browser yang mengurus, jangan disimpan di cache.
  if (req.headers.has("range") || req.destination === "video") return;
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

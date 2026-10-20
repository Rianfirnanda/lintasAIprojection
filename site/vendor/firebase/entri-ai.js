// Bagian Firebase yang hanya dipakai Tanya Takar, dimuat terpisah supaya halaman lain tidak ikut mengunduhnya.
// Kode bersama (inti Firebase) ada di firebase-bersama.js, jadi aplikasi yang dibuat firebase.js tetap dikenali di sini.
// AI Logic (Gemini lewat Firebase): kunci Gemini dikelola Firebase, tidak pernah ada di browser.
export { getAI, getGenerativeModel, GoogleAIBackend } from "firebase/ai";
// App Check (reCAPTCHA v3): memastikan permintaan AI datang dari situs ini, bukan dari skrip orang lain. Opsional.
export { initializeAppCheck, ReCaptchaV3Provider } from "firebase/app-check";

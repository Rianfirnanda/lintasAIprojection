// Sumber bundel Firebase untuk situs ini. Hanya fungsi yang dipakai yang diekspor, supaya berkasnya kecil.
// Bangun ulang: lihat README.md di folder ini.
export { initializeApp, getApps } from "firebase/app";
export {
  getAuth, GoogleAuthProvider, signInWithPopup, signInWithCredential, signInWithRedirect, getRedirectResult, onAuthStateChanged, signOut,
  connectAuthEmulator,
} from "firebase/auth";
export {
  getFirestore, connectFirestoreEmulator, doc, getDoc, setDoc, updateDoc, deleteDoc, collection, query, orderBy, limit,
  onSnapshot, addDoc, serverTimestamp, Timestamp, where, getDocs, writeBatch,
} from "firebase/firestore";
// AI Logic (Gemini lewat Firebase): kunci Gemini dikelola Firebase, tidak pernah ada di browser. Dipakai Tanya Takar.
export { getAI, getGenerativeModel, GoogleAIBackend } from "firebase/ai";
// App Check (reCAPTCHA v3): memastikan permintaan AI datang dari situs ini, bukan dari skrip orang lain. Opsional.
export { initializeAppCheck, ReCaptchaV3Provider } from "firebase/app-check";

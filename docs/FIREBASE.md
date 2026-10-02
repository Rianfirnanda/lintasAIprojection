# Pindah ke Firebase (Hosting, login Google, Firestore)

Sistem ini bisa terbit ke **Firebase Hosting** dan memakai **login Google** dengan persetujuan admin. Pengolahan data,
AI, dan notifikasi tetap berjalan gratis di GitHub Actions. Hasilnya otomatis dikirim ke Firebase setiap kali proses
berjalan.

Setelah Firebase aktif, **pekerjaan sehari-hari cukup lewat situs**. Petugas, operator, analis, TPID, dan admin tidak
perlu membuka GitHub sama sekali (lihat [Kerja harian lewat situs](#kerja-harian-lewat-situs)). GitHub hanya dipakai
sekali di awal untuk menyimpan kunci Firebase.

Selama masa peralihan, situs tetap terbit juga ke GitHub Pages. Setelah alamat Firebase berjalan baik, GitHub Pages
boleh dimatikan.

## Cara kerja akun

1. Orang membuka halaman **Masuk**, lalu menekan **Masuk dengan Google**.
2. Akun barunya tersimpan di Firestore (koleksi `lbp_pengguna`) dengan status **menunggu**, tanpa peran.
3. Admin membuka halaman **Pengguna**, lalu memilih peran dan menekan **Setujui** (atau **Tolak**). Izin halaman bisa
   mengikuti peran, atau diatur sendiri per orang.
4. Begitu disetujui, halaman orang itu langsung lanjut ke berandanya.
5. Admin juga bisa mengubah peran dan izin, menonaktifkan, mengaktifkan lagi, atau menghapus akun. Setiap tindakan
   tercatat di **Jejak tindakan admin**.

Semua ini dijaga **aturan keamanan Firestore** (`firestore.rules`), bukan hanya tampilan. Pendaftar tidak bisa memberi
dirinya peran atau izin, dan hanya admin aktif yang bisa membaca serta mengubah akun orang lain.

**Admin pertama:** email yang diisi di `FIREBASE_ADMIN_AWAL` otomatis menjadi admin saat pertama kali masuk. Admin
berikutnya cukup disetujui lewat halaman Pengguna dengan peran Administrator.

## Langkah awal (sekali saja)

Semua langkah dilakukan di proyek Firebase **lintas benteng** yang sudah ada.

### 1. Aktifkan login Google
Firebase Console → **Authentication** → **Sign-in method** → **Google** → **Enable** → pilih email dukungan →
**Save**.

### 2. Siapkan Firestore
- **Kalau Firestore belum dipakai aplikasi lain:** **Firestore Database** → **Create database** → lokasi
  `asia-southeast2 (Jakarta)` → mode **production**.
- **Kalau Firestore sudah dipakai aplikasi Lintas Benteng:** jangan dibuat ulang. Aturannya perlu digabung (langkah 7).

### 3. Buat situs Hosting khusus
**Hosting** → **Add another site** → beri nama, misalnya `lintas-benteng-proyeksi`. Alamatnya nanti
`https://lintas-benteng-proyeksi.web.app`.

> Jangan memakai situs utama proyek. Setiap kali terbit, isi situs diganti seluruhnya, jadi aplikasi Lintas Benteng
> yang ada di situs utama akan hilang.

### 4. Izinkan alamat situs untuk login
**Authentication** → **Settings** → **Authorized domains** → pastikan alamat situs dari langkah 3 ada
(`lintas-benteng-proyeksi.web.app` dan `lintas-benteng-proyeksi.firebaseapp.com`). Tambahkan bila belum ada.

### 5. Daftarkan aplikasi web
**Project settings** → **General** → **Your apps** → **Add app** → ikon web `</>` → beri nama
"Lintas Benteng Projection" → **Register app**. Salin seluruh isi `firebaseConfig` yang ditampilkan.

Isinya (apiKey, projectId, dan seterusnya) memang dipakai terbuka oleh browser. Pengamannya adalah aturan Firestore
dan daftar Authorized domains, bukan kerahasiaan isinya.

### 6. Buat akun layanan untuk GitHub Actions
Google Cloud Console (proyek yang sama) → **IAM & Admin** → **Service Accounts** → **Create service account** → nama
misalnya `terbit-lbp`. Beri peran:

- **Firebase Hosting Admin**: untuk menerbitkan situs.
- **Service Usage Consumer**: dibutuhkan alat Firebase untuk memeriksa layanan proyek.
- **Firebase Rules Admin**: hanya bila aturan Firestore ikut diterbitkan otomatis (langkah 7).
- **Cloud Datastore User**: supaya mesin pengolah bisa mengambil kiriman dari situs (harga, keputusan, pengaturan,
  kunci) dan menulis status proses.

Lalu buka akun layanan itu → **Keys** → **Add key** → **JSON**. Berkas JSON akan terunduh.

Kalau terbit gagal karena izin, pesan di GitHub Actions menyebut izin yang kurang. Tambahkan peran itu ke akun
layanan yang sama.

> Ada cara yang lebih cepat: Project settings → Service accounts → Generate new private key. Tapi kunci itu punya
> hak hampir penuh atas proyek. Akun layanan khusus di atas lebih aman.

### 7. Isi pengaturan
Buka panel **Pengaturan** di situs → tab **Firebase**, lalu isi:

| Isian | Isi dengan |
|---|---|
| Konfigurasi web Firebase (`FIREBASE_WEB_CONFIG`) | Isi `firebaseConfig` dari langkah 5. Boleh ditempel apa adanya. |
| Nama situs Hosting (`FIREBASE_HOSTING_SITE`) | Nama situs dari langkah 3, misalnya `lintas-benteng-proyeksi` |
| Kunci akun layanan (`FIREBASE_SERVICE_ACCOUNT`) | Seluruh isi berkas JSON dari langkah 6 |
| Email admin pertama (`FIREBASE_ADMIN_AWAL`) | Email Google admin, dipisah koma bila lebih dari satu |
| Terbitkan aturan Firestore (`FIREBASE_TERBITKAN_ATURAN`) | `ya` bila Firestore belum dipakai aplikasi lain, selain itu `tidak` |

Semua isian ini tersimpan sebagai GitHub Secret, jadi tidak pernah masuk ke repositori. Isian yang sama juga bisa
diisi lewat GitHub → **Settings** → **Secrets and variables** → **Actions**.

**Kalau `FIREBASE_TERBITKAN_ATURAN` = `tidak`:** aturan perlu digabung sendiri, sekali saja. Buka Firebase Console →
**Firestore Database** → **Rules**, lalu salin blok `match /lbp_pengguna/...` dan `match /lbp_jejak/...` beserta
fungsi-fungsi di atasnya dari berkas `firestore.rules` ke dalam aturan yang ada. Ganti `/*ADMIN_AWAL*/[]` dengan
daftar email admin pertama, misalnya `['admin@contoh.go.id']`, lalu tekan **Publish**. Tanpa langkah ini, login
berhasil tetapi akun tidak bisa tersimpan.

### 8. Terbitkan
Di panel Pengaturan, tekan **Perbarui data dan dashboard sekarang**, atau tunggu jadwal berikutnya. Setelah selesai:

1. Buka `https://<nama-situs>.web.app/masuk.html`.
2. Masuk dengan email admin pertama. Anda langsung menjadi admin.
3. Minta anggota tim masuk dengan Google. Setujui mereka di halaman **Pengguna**.

### 9. Setelah semua berjalan
- Matikan GitHub Pages: GitHub → Settings → Pages → Source: None.
- Repositori boleh dijadikan **private**. GitHub Actions tetap berjalan, dengan kuota gratis 2.000 menit per bulan.

## Kerja harian lewat situs

| Siapa | Di halaman | Yang dilakukan |
|---|---|---|
| Petugas | Catat Harga | Isi harga, tekan **Simpan dan kirim**. Tanpa sinyal, harga aman di HP dan terkirim sendiri begitu ada sinyal. |
| Operator | Cek Data | **Unggah berkas harga** (CSV dari Excel) dan **Simpan keputusan** terima/tolak. |
| Analis, TPID | Peringatan | Isi formulir tindak lanjut, tekan **Simpan catatan**. |
| Analis | Akurasi | Centang cara prakiraan, tekan **Simpan persetujuan**. |
| Admin | Pengaturan | Ubah isian, isi kunci AI dan notifikasi, tekan **Jalankan sekarang**. Tanpa token GitHub. |
| Admin | Pengguna | Setujui akun, atur peran dan izin. |

Cara kerjanya:

1. Situs menyimpan kiriman langsung ke Firestore (`lbp_harga`, `lbp_validasi`, `lbp_tindak_lanjut`,
   `lbp_persetujuan_model`, `lbp_pengaturan`, `lbp_rahasia`, `lbp_perintah`). Aturan Firestore memeriksa siapa yang
   boleh mengirim apa, dan isinya harus wajar.
2. Pemeriksa otomatis (`.github/workflows/antrean.yml`) melihat Firestore setiap 15 menit, Senin sampai Jumat pukul
   07.00 sampai 18.00 WIB. Bila ada yang baru, pipeline dijalankan.
3. Pipeline menyalin kiriman ke berkas di repositori (`data/masuk/harga/situs/`, `data/validasi/situs.csv`, dan
   seterusnya) sebagai jejak audit, menerapkan pengaturan, memakai kunci dari situs, lalu memperbarui dashboard.
   Kiriman yang sudah diambil dicatat di `data/firestore_tanda.json`, jadi yang dibaca hanya kiriman baru.
4. Status proses tampil langsung di panel Pengaturan.

Waktu tunggu: keputusan, catatan, pengaturan, dan tombol Jalankan biasanya 15 sampai 30 menit. Harga baru dikumpulkan
dulu, paling lama sekitar 1 jam, supaya dashboard tidak dibangun ulang setiap kali seorang petugas mengirim. Di luar jam
kerja, kiriman diproses pada jam kerja berikutnya. Jadwal GitHub kadang terlambat beberapa menit.

**Kunci di situs:** kunci AI dan notifikasi yang diisi lewat panel Pengaturan hanya bisa ditulis, tidak bisa dibaca
dari browser siapa pun, termasuk admin. Bila kunci yang sama juga ada di GitHub Secrets, kunci dari situs yang dipakai.
Kunci Firebase (`FIREBASE_*`) tetap di GitHub Secrets karena mesin membutuhkannya untuk masuk ke Firestore.

**Kuota GitHub Actions:** repositori publik tidak dibatasi. Bila repositori dijadikan private, pemeriksa berkala memakai
sekitar 900 menit per bulan dari kuota gratis 2.000 menit, belum termasuk pipeline. Kurangi frekuensinya di
`antrean.yml` (misalnya `*/30`) bila kuota mepet.

## Yang perlu diketahui

- **Data dashboard masih berupa berkas terbuka di Hosting.** Harga, peringatan, dan laporan bisa dibuka siapa pun
  yang tahu alamat berkasnya. Login dan persetujuan sudah aman, tapi kalau ada data yang harus rahasia, data itu perlu
  dipindah ke Firestore dengan aturannya sendiri. Ini tahap berikutnya.
- **Kuota gratis (paket Spark)** dipakai bersama aplikasi Lintas Benteng di proyek yang sama. Setiap halaman dibuka
  oleh pengguna yang masuk, akunnya dicek sekali di Firestore (1 kali baca).
- **Akun contoh** (sandi `lintas2026`) otomatis tidak dipakai lagi begitu Firebase aktif.

## Menguji di komputer sendiri

```bash
npm install                       # alat Firebase (emulator) untuk uji
npm run uji:aturan                # uji aturan Firestore di emulator, butuh Java 11+
pip install -r requirements-firebase.txt
npm run uji:mesin                 # uji pengambil kiriman situs di emulator
```

Untuk mencoba alur login dengan emulator:
1. Jalankan `npm run emulator`.
2. Bangun data dengan `FIREBASE_WEB_CONFIG` berisi konfigurasi contoh dan `FIREBASE_EMULATOR=1`.
3. Sajikan folder `site/` di `http://localhost`.

Mode emulator hanya aktif bila situs dibuka dari localhost.

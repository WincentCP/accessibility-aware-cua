# Live agent: quick start dan batas aman

## Tujuan integrasi

Integrasi ini membuat extension bukan lagi mock UI. Koordinator suara di latar
belakang mengirim permintaan peserta dan `session_id` ke FastAPI. Backend mengobservasi accessibility tree,
meminta satu keputusan terstruktur dari model, menjalankan primitive keyboard
yang diizinkan, lalu memverifikasi postcondition. Peta tugas hanya menandai
langkah sebagai selesai setelah verifikasi.

Alur data:

```text
koordinator suara -> FastAPI lokal -> LangGraph + structured planner
           -> semantic bridge lokal -> Chromium benchmark
           -> observer/verifier -> progres sesi
```

Browser bridge hanya bind ke `127.0.0.1`, memerlukan bearer token yang sama
dengan `CUA_APP_SECRET`, membatasi payload, menggunakan role/name aksesibel, dan
memblokir navigasi non-lokal. `GEMINI_API_KEY` dibaca backend dari `.env`; key
tidak pernah dikirim ke extension atau browser bridge.

## Menjalankan paling mudah di Windows

Setelah setup satu kali dan `.env` terisi, klik dua kali `Mulai Pengujian.vbs`.
Pilih **Mulai Penelitian**. Launcher memastikan PostgreSQL aktif, membangun
extension, menyalakan API dan bridge browser, lalu membuka browser penelitian
serta Researcher Console secara otomatis.

Di Researcher Console, tekan **Mulai Penelitian** satu kali. Izinkan kamera dan
mikrofon, lalu pada dialog berbagi layar pilih **Seluruh layar** dan **Bagikan**.
AI Guide membacakan petunjuk ini sejak awal. Setelah izin browser selesai, AI
menanyakan nama, ejaan nama, kelas, dan umur satu per satu. Task 1 kemudian
terbuka di area kegiatan pada halaman yang sama, tanpa tab kosong. Peserta tidak
perlu menekan tombol aplikasi lagi. Perekaman, listening, tindakan asisten,
perpindahan empat task, feedback suara, penyimpanan hasil, dan penutupan berjalan
otomatis.

Peserta tidak melihat panel agen. Koordinator suara tetap aktif di latar belakang
dan selalu membacakan semua pilihan halaman tanpa menanyakannya lebih dahulu.
Jawaban pendek seperti "iya", "ulang", "udah", dan "lanjut" ditafsirkan
berdasarkan pertanyaan terakhir. Jika peserta diam, AI menawarkan pengulangan
instruksi secara otomatis. Status visual menunjukkan kapan AI berbicara,
mendengarkan, memahami jawaban, atau sedang bekerja.

Untuk pemeriksaan developer tanpa biaya planner model, jalankan satu perintah
`npm run agent:test`. Mode ini memakai planner deterministik yang hanya diizinkan
ketika `CUA_ENV=test`.

Untuk memeriksa jalur suara Gemini nyata dari TTS ke STT live, jalankan
`npm run voice:test`. Skrip menyalakan dan mematikan API lokal sendiri.

## Konfigurasi `.env`

1. Buka `.env` dengan `notepad .env`. Pastikan nilai berikut terisi:

   ```dotenv
   CUA_APP_SECRET=<random-lokal-minimal-24-karakter>
   CUA_BROWSER_BRIDGE_PORT=8765
   CUA_BROWSER_BRIDGE_URL=http://127.0.0.1:8765
   CUA_LIVE_AGENT_ENABLED=true
   GEMINI_API_KEY=<key-milik-Anda>
   CUA_PLANNER_MODEL=gemini-3.7-flash
   CUA_PLANNER_FALLBACK_MODEL=gemini-3.6-flash
   CUA_STT_MODEL=gemini-3.5-transcribe-live
   CUA_TTS_MODEL=gemini-3.1-flash-tts-preview
   CUA_TTS_VOICE=Sulafat
   ```

Tidak ada OpenAI API key atau provider OpenAI dalam runtime. Kunci Gemini tetap
hanya dibaca backend lokal dan tidak dikirim ke extension.

## Definition of Done smoke test

- Terminal browser menampilkan `Live browser bridge siap`.
- Koordinator suara menerima permintaan tanpa meminta API key.
- Status bergerak dari `QUEUED` ke `RUNNING`.
- Chromium berubah melalui aksi keyboard semantik, bukan koordinat layar.
- Peta tugas tidak mengklaim selesai sebelum postcondition berstatus verified.
- Jika bridge, model, atau verifikasi gagal, status menjadi `FAILED` dan agent
  tidak meneruskan aksi secara diam-diam.

## Hasil sesi

- `.runtime/recordings/<session-id>/screen.webm` berisi layar, audio, dan frame
  wajah peserta.
- `.runtime/recordings/<session-id>/user.webm` adalah rekaman kamera cadangan.
- `.runtime/study-results/<session-id>.json` berisi transkrip, feedback, urutan
  task, state, event sesi, nama, ejaan nama, kelas, dan umur peserta.
- Setelah sesi selesai, tombol **Unduh laporan PDF** muncul di Researcher Console.
  PDF berisi profil peserta, ringkasan, durasi dan hasil task, feedback, serta
  transkrip. Karena memuat data pribadi, simpan PDF secara terbatas dan jangan
  memasukkannya ke Git.

Tes otomatis bukan pengganti pilot NVDA dan peserta tunanetra. Sebelum studi
utama, lakukan pemeriksaan suara, posisi kamera, screen reader, retensi data,
penghapusan rekaman, dan prosedur etik penelitian.

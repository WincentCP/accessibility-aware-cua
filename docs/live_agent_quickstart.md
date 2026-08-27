# Live agent: quick start dan batas aman

## Tujuan integrasi

Integrasi ini membuat extension bukan lagi mock UI. Side panel mengirim tujuan
dan `session_id` benchmark ke FastAPI. Backend mengobservasi accessibility tree,
meminta satu keputusan terstruktur dari model, menjalankan primitive keyboard
yang diizinkan, lalu memverifikasi postcondition. Peta tugas hanya menandai
langkah sebagai selesai setelah verifikasi.

Alur data:

```text
side panel -> FastAPI lokal -> LangGraph + structured planner
           -> semantic bridge lokal -> Chromium benchmark
           -> observer/verifier -> peta tugas side panel
```

Browser bridge hanya bind ke `127.0.0.1`, memerlukan bearer token yang sama
dengan `CUA_APP_SECRET`, membatasi payload, menggunakan role/name aksesibel, dan
memblokir navigasi non-lokal. `GEMINI_API_KEY` dibaca backend dari `.env`; key
tidak pernah dikirim ke extension atau browser bridge.

## Menjalankan paling mudah di Windows

Setelah setup satu kali dan `.env` terisi, klik dua kali `Mulai Pengujian.vbs`.
Pilih **Mulai sesi penelitian**. Launcher membangun extension, menyalakan API,
bridge browser, Chromium terisolasi, dan Researcher Console secara otomatis.
Tutup jendela Chromium setelah sesi untuk menghentikan service.

Untuk pemeriksaan otomatis tanpa biaya model, pilih **Periksa sistem otomatis**
atau jalankan `npm run agent:test`. Mode ini memakai planner deterministik yang
hanya diizinkan ketika `CUA_ENV=test`.

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
   ```

Tidak ada OpenAI API key atau provider OpenAI dalam runtime. Kunci Gemini tetap
hanya dibaca backend lokal dan tidak dikirim ke extension.

## Definition of Done smoke test

- Terminal browser menampilkan `Live browser bridge siap`.
- Side panel menerima tujuan tanpa meminta API key.
- Status bergerak dari `QUEUED` ke `RUNNING`.
- Chromium berubah melalui aksi keyboard semantik, bukan koordinat layar.
- Peta tugas tidak mengklaim selesai sebelum postcondition berstatus verified.
- Jika bridge, model, atau verifikasi gagal, status menjadi `FAILED` dan agent
  tidak meneruskan aksi secara diam-diam.

## Batas implementasi saat ini

- Live MVP dipakai lebih dahulu untuk task rendah risiko seperti T01.
- Pause/takeover berlaku pada checkpoint antar-aksi. Resume dilakukan setelah
  agent benar-benar berstatus menunggu, bukan saat aksi masih berjalan.
- Tindakan sensitif tetap berhenti pada explicit approval. Jalur approval
  one-shot sudah dibuktikan pada core, tetapi kelanjutan approval dari side panel
  ke live run perlu gate end-to-end tersendiri sebelum dipakai dalam studi.
- Hidden oracle tetap tidak dikirim ke planner. Klaim selesai pada panel adalah
  hasil postcondition agent; keberhasilan benchmark penelitian tetap dihitung
  evaluator terpisah.
- Ini belum membuktikan usability bagi pengguna tunanetra; walkthrough NVDA dan
  user testing tetap diperlukan.
- Perekaman webcam, audio, dan layar belum diimplementasikan. Researcher Console
  sudah mencatat consent granular, tetapi tidak mengklaim atau memulai perekaman.

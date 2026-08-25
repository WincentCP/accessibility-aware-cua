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
memblokir navigasi non-lokal. `OPENAI_API_KEY` dibaca backend dari `.env`; key
tidak pernah dikirim ke extension atau browser bridge.

## Menjalankan di Windows PowerShell

1. Buka `.env` dengan `notepad .env`. Pastikan nilai berikut terisi:

   ```dotenv
   CUA_APP_SECRET=<random-lokal-minimal-24-karakter>
   CUA_BROWSER_BRIDGE_PORT=8765
   CUA_BROWSER_BRIDGE_URL=http://127.0.0.1:8765
   CUA_LIVE_AGENT_ENABLED=true
   OPENAI_API_KEY=<key-milik-Anda>
   CUA_PLANNER_MODEL=gpt-4.1-mini-2025-04-14
   ```

2. Jalankan API di terminal pertama:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   python -m uvicorn apps.api.a11y_api.app:app --host 127.0.0.1 --port 8000
   ```

3. Build extension dan buka browser di terminal kedua:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   npm run test:frontend
   $env:CUA_BROWSER_PROFILE_DIR=".runtime/playwright-profile-live"
   node .\scripts\open-benchmark.mjs --task T01 --condition C0 --with-extension
   ```

4. Jangan tekan Enter pada terminal kedua selama browser masih dipakai. Di
   Chromium, pilih **Mulai dan buka asisten**, masukkan tujuan T01 secara lengkap,
   lalu pilih **Jalankan**.

Contoh tujuan aman:

> Pilih rute yang sesuai dengan tiga batasan pada halaman. Jangan melakukan
> pemesanan atau pembayaran. Berhenti setelah pilihan tersimpan.

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

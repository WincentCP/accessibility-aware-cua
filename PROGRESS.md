# Progress Implementasi

Terakhir diperbarui: 4 September 2026.

## Sudah tersedia

- Benchmark deterministik 12 task dan tiga kondisi halaman.
- Observer accessibility tree, executor semantik, verifikasi pasca-aksi, recovery terbatas, dan shared control.
- Integrasi FastAPI, LangGraph, Gemini planner, browser bridge, dan extension MV3.
- Redesign soft-pastel dengan Plus Jakarta Sans dan header dekoratif dihapus.
- Researcher Console satu tombol tanpa input identitas atau consent form di dalam aplikasi.
- Mode studi menyembunyikan tujuan penelitian serta metadata teknis dari halaman peserta.
- Planner deterministik empat core task untuk pengujian lokal tanpa biaya API.
- Approval suara eksplisit yang dikonsumsi satu kali sebelum aksi sensitif.
- Launcher Windows satu klik dan perintah `npm run agent:test`.
- Chromium E2E untuk accessibility tree, aksi agent, verifikasi pasca-aksi,
  approval, state UI akhir, serta error handling fail-closed.
- Perekaman otomatis layar dengan frame wajah dan audio, plus rekaman kamera cadangan.
- Gemini live STT Bahasa Indonesia, Gemini TTS Bahasa Indonesia, turn-taking otomatis,
  respons percakapan natural, dan reconnect sesi transkripsi.
- Feedback suara setelah Task 4, hasil sesi lokal dalam JSON, dan laporan PDF
  yang dapat diunduh peneliti.
- Boundary repository yang eksplisit: UI dan extension di `frontend/`, API dan
  core agent di `backend/`, serta hidden oracle tetap terpisah dari runtime.

## Milestone workflow dan prototype selesai

- Alur peserta hands-free tidak mewajibkan tombol selama sesi.
- Satu klik memulai pemeriksaan perangkat, permission browser, recording, dan
  empat instruksi standar; setelah permission tidak ada tombol wajib.
- Mode studi tidak merender tujuan penelitian, condition, seed, atau kontrol
  teknis pada halaman peserta.
- Runtime penelitian hanya memakai Gemini; planner deterministik dibatasi untuk
  `CUA_ENV=test`.

## Sisa sebelum studi utama

- Pilot kualitas suara dan variasi ujaran bersama pengguna Bahasa Indonesia.
- Validasi manual NVDA, kamera nyata, microphone nyata, dan pemilih layar browser.
- Persistence metadata sesi penuh ke PostgreSQL; saat ini hasil sesi juga disimpan
  sebagai JSON lokal dan audit agent memakai penyimpanan aplikasi.
- Validasi kebijakan retensi dan penghapusan rekaman.
- Gate manual NVDA dan pilot dengan pengguna tunanetra.
- Freeze informed consent dan izin dokumentasi melalui prosedur etik penelitian
  di luar aplikasi.

Runtime penelitian hanya memakai Gemini. Planner deterministik hanya tersedia saat
`CUA_ENV=test` untuk pemeriksaan otomatis lokal dan tidak boleh digunakan pada sesi peserta.

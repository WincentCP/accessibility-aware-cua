# Progress Implementasi

Terakhir diperbarui: 27 Agustus 2026.

## Sudah tersedia

- Benchmark deterministik 12 task dan tiga kondisi halaman.
- Observer accessibility tree, executor semantik, verifikasi pasca-aksi, recovery terbatas, dan shared control.
- Integrasi FastAPI, LangGraph, Gemini planner, browser bridge, dan extension MV3.
- Redesign soft-pastel dengan Plus Jakarta Sans dan header dekoratif dihapus.
- Researcher Console prototype untuk setup peserta, consent granular, instruksi standar, empat core task, dan event sesi.
- Mode studi menyembunyikan tujuan penelitian serta metadata teknis dari halaman peserta.
- Planner deterministik T01 untuk pengujian lokal tanpa biaya API.
- Approval suara eksplisit yang dikonsumsi satu kali sebelum aksi sensitif.
- Launcher Windows satu klik dan perintah `npm run agent:test`.
- Chromium E2E untuk accessibility tree, aksi agent, verifikasi pasca-aksi,
  approval, state UI akhir, serta error handling fail-closed.

## Milestone workflow dan prototype selesai

- Alur peserta hands-free tidak mewajibkan tombol selama sesi.
- Researcher Console membacakan tujuan kegiatan, consent, cek perangkat, dan
  empat instruksi standar.
- Mode studi tidak merender tujuan penelitian, condition, seed, atau kontrol
  teknis pada halaman peserta.
- Runtime penelitian hanya memakai Gemini; planner deterministik dibatasi untuk
  `CUA_ENV=test`.

## Belum study-ready

- Transkripsi suara natural yang teruji dengan peserta dan variasi ujaran Bahasa Indonesia.
- Recording webcam, audio, dan layar dengan penyimpanan serta penghapusan yang tervalidasi.
- Persistence Researcher Console ke PostgreSQL.
- Sinkronisasi otomatis task completion ke workflow studi.
- Gate manual NVDA dan pilot dengan pengguna tunanetra.
- Freeze naskah consent melalui prosedur etik penelitian.

Runtime penelitian hanya memakai Gemini. Planner deterministik hanya tersedia saat
`CUA_ENV=test` untuk pemeriksaan otomatis lokal dan tidak boleh digunakan pada sesi peserta.

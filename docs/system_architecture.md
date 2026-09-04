# Arsitektur Sistem

## Tujuan

Accessibility-Aware CUA adalah prototipe penelitian untuk menilai apakah AI agent
yang membaca struktur aksesibilitas halaman, bertindak secara semantik, dan
memverifikasi hasil setiap aksi dapat membantu peserta tunanetra menyelesaikan
tugas web secara andal dan mudah dipahami.

Sistem memiliki dua jalur evaluasi yang saling melengkapi:

- studi pengguna hands-free untuk menilai pengalaman nyata, pemahaman, recovery,
  dan kebutuhan intervensi;
- benchmark B0/B1/P untuk mengukur keberhasilan task secara terkontrol,
  reproducible, dan dapat dibandingkan antar-konfigurasi.

Semua situs dan data bersifat sintetis. Sistem berhenti sebelum transaksi nyata,
pembayaran, konfirmasi janji, atau perubahan akun final.

## Komponen runtime

```text
Peserta
  -> frontend/research-console
       -> frontend/extension (koordinator suara)
       -> backend/api (sesi, STT/TTS, rekaman, laporan)
            -> backend/agent (observe, plan, act, verify, recover)
                 -> scripts/browser-bridge.mjs
                      -> halaman task di iframe yang sama
```

`a11y_benchmark/` menyediakan implementasi katalog, reset deterministik, dan
oracle. Kontrak publik berada di `benchmark/public/`, sedangkan jawaban evaluasi
berada di `benchmark/private/`. Hidden oracle hanya boleh dipanggil oleh evaluator
dan tidak pernah diberikan kepada UI atau agent.

## Flow studi pengguna

1. Peneliti menjalankan `Mulai Pengujian.vbs` atau `npm run agent:launch`.
2. Launcher memeriksa konfigurasi, menyalakan PostgreSQL bila diperlukan,
   membangun extension, menjalankan browser bridge dan FastAPI, lalu membuka
   Researcher Console pada profil Chromium terisolasi.
3. Peserta menekan **Mulai Penelitian** satu kali.
4. Browser meminta izin mikrofon, kamera, dan berbagi layar. Setelah izin siap,
   aplikasi langsung memulai rekaman kamera serta rekaman layar dengan frame
   wajah peserta.
5. Koordinator suara memperkenalkan diri dan mengumpulkan nama, ejaan nama,
   kelas, serta umur melalui percakapan Bahasa Indonesia.
6. API mereset Task 1 dengan seed terkendali. Extension memuat halaman kegiatan
   di iframe pada tab yang sama dan AI membacakan instruksi serta pilihan yang
   relevan.
7. Ucapan peserta ditranskripsikan. Agent membaca accessibility tree melalui
   browser bridge, menyusun langkah, menjalankan aksi semantik, memverifikasi
   postcondition, dan mencoba recovery terbatas bila hasil belum cocok.
8. Status penting—mendengarkan, bekerja, berhasil, gagal, atau memerlukan
   recovery—disampaikan lewat suara. Saat peserta diam, AI memberi pengingat.
9. Setelah hasil task terverifikasi, sistem berpindah otomatis ke task berikutnya.
   Empat core task yang sama dipakai untuk menjaga perbandingan antar-peserta.
10. Setelah Task 4, AI meminta feedback singkat, menutup sesi, menghentikan
    rekaman, menyimpan hasil JSON, dan menyediakan laporan PDF.

## Flow agent per aksi

```text
Observe accessibility tree
  -> Plan tindakan terstruktur
  -> Safety/policy check
  -> Execute lewat target semantik
  -> Verify hasil pasca-aksi
     -> cocok: catat verified progress
     -> belum cocok: recovery terbatas + observe ulang
     -> tidak aman/tidak pasti: berhenti dengan status yang eksplisit
```

Progress hanya boleh diklaim selesai setelah verifikasi. Screenshot dan koordinat
tidak digunakan oleh konfigurasi accessibility-aware sebagai pengganti struktur
semantik.

## Flow benchmark dan evaluasi

1. Runner membaca manifest run dan kontrak task publik.
2. Setiap kasus di-reset dengan task, condition, dan seed yang tercatat.
3. B0 menerima screenshot dan bertindak dengan koordinat; B1 memakai struktur
   semantik tanpa enhancement proposed; P memakai struktur semantik, verifikasi,
   recovery terbatas, dan task map.
4. Hidden evaluator memeriksa state akhir tanpa membocorkan oracle ke agent.
5. Hasil, error, recovery, waktu, dan provenance disimpan untuk report CSV/JSON.

## Batas direktori

```text
frontend/
  research-console/  template dan aset UI sesi/mini-site
  extension/         integrasi Chromium dan koordinator hands-free
backend/
  api/               transport HTTP/WebSocket dan lifecycle studi
  agent/             logika agent yang independen dari UI
a11y_benchmark/       implementasi benchmark Python
benchmark/            spesifikasi, fixture, golden data, dan hidden oracle
evaluation/           runner dan analisis perbandingan
scripts/              tooling operasional; bukan kode domain utama
tests/                bukti otomatis lintas lapisan
docs/                 keputusan desain, protokol, dan runbook
evidence/             artefak gate yang memang dilacak
```

Aturan dependensinya:

- frontend hanya memakai API publik dan message contract extension;
- API boleh mengorkestrasi agent dan benchmark, tetapi tidak mengirim hidden
  oracle kepada browser;
- agent tidak mengimpor template, CSS, atau JavaScript UI;
- evaluation boleh mengakses oracle melalui boundary evaluator;
- file rahasia, rekaman, hasil sesi lokal, cache, dan build output berada di
  `.env`, `.runtime/`, atau direktori ignored lain dan tidak boleh di-commit.

## Entry point penting

- peserta/peneliti: `Mulai Pengujian.vbs`;
- launcher developer: `npm run agent:launch`;
- regression studi: `npm run study:test`;
- API langsung: `python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000`;
- benchmark pilot: `npm run evaluation:pilot`;
- seluruh test Python: `python -m pytest -q`;
- UI/extension: `npm run test:frontend`;
- browser E2E: `npm run test:e2e`.

# Gate Manual Windows + Headed Chromium + NVDA

Checklist ini adalah QA peneliti sebelum melibatkan partisipan. Jangan meminta
pengguna tunanetra menguji build yang belum lolos checklist ini.

## Identitas run

- Tanggal:
- Commit/hash artefak:
- Windows:
- NVDA:
- Chromium/Playwright:
- Extension version:
- Penguji:

## Setup

- [ ] `npm run test:frontend` PASS.
- [ ] API dan PostgreSQL health `ready`.
- [ ] `npm run browser:open -- --task T01 --condition C0 --with-extension`
      membuka profile `.runtime`, bukan profile pribadi.
- [ ] NVDA memakai konfigurasi harian normal; tidak perlu blindfold.

## Extension shell

- [ ] Judul, goal, status, peta tugas, dan shared-control section terbaca sebagai
      struktur yang masuk akal.
- [ ] Semua control dicapai dengan Tab/Shift+Tab dan mempunyai nama jelas.
- [ ] Goal dapat diketik.
- [ ] Tombol input suara memberi status tersedia/tidak tersedia tanpa membuat
      input teks macet.
- [ ] Focus indicator terlihat dan focus order logis.
- [ ] Tujuan, progres, selesai terverifikasi, pilihan relevan, tindakan berikutnya,
      item belum pasti, dan ringkasan akhir dibaca sebagai bagian yang berbeda.
- [ ] Tindakan berikutnya selalu disebut “direncanakan, belum selesai”.
- [ ] Update biasa dibaca `polite`; hanya error/approval yang menginterupsi.
- [ ] Push-to-talk dapat dibatalkan, berhenti maksimum 20 detik, dan transkrip
      harus dikonfirmasi atau diubah sebelum digunakan.
- [ ] Saat izin mikrofon ditolak, input teks dan seluruh kontrol tetap berfungsi.
- [ ] Setujui/Ubah/Tolak/Jeda/Ambil alih/Lanjutkan/Batalkan dapat dijalankan
      dengan keyboard dan tidak terjadi aksi ganda.
- [ ] Empat tipe task (travel, marketplace, appointment, account) melakukan
      takeover → focus handoff → resume tanpa focus hilang atau ref lama dipakai.

## Mini-site

Untuk T01–T12 pada C0, lalu minimal satu task per domain pada C1 dan C2:

- [ ] Skip link memindahkan fokus ke main.
- [ ] Satu heading level 1 menyebut task.
- [ ] Goal, batas aman, kondisi, status, dan area kerja dapat dinavigasi dengan
      heading/landmark/form mode.
- [ ] Label control dibaca bersama nilai/state.
- [ ] Task dapat diselesaikan hanya dengan keyboard.
- [ ] Setelah submit, status hasil diumumkan dan fokus tidak hilang ke browser
      chrome/address bar.
- [ ] C1 tetap bermakna walau susunan/wording berubah.
- [ ] C2 mengumumkan busy/update dan kembali ke state stabil.
- [ ] Tidak ada tombol booking, checkout, bayar, hapus akun, commit reschedule,
      atau konfirmasi janji.

## Hasil

- [ ] PASS tanpa temuan blocker.
- [ ] Semua temuan dicatat dengan task, condition, seed, expected, actual, dan
      langkah reproduksi.
- [ ] Screenshot/log tidak berisi data pribadi.

Status gate: `PENDING / PASS / FAIL`

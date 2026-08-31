# Kebijakan privasi dan retensi prototipe penelitian

Dokumen ini adalah kebijakan teknis minimum untuk data sintetis prototipe. Ia
bukan pengganti lembar persetujuan etik ketika studi pengguna dimulai.

## Prinsip pengumpulan minimum

- Kegiatan memakai data tugas sintetis; jangan masukkan akun, alamat, pembayaran,
  password, OTP, token, API key, atau cookie nyata. Nama, ejaan nama, kelas, dan
  umur peserta adalah data pribadi penelitian yang memang dikumpulkan dan harus
  dibatasi aksesnya.
- Audio peserta ditangkap otomatis selama sesi untuk transkripsi dan perekaman
  penelitian. Tidak ada push-to-talk atau peninjauan transkrip oleh peserta.
  Perlakuan rekaman, transkrip, dan PDF harus mengikuti informed consent serta
  persetujuan etik yang berlaku.
- Accessibility snapshot menyimpan struktur semantik relevan, bukan dump halaman
  penuh. Nilai field sensitif tidak boleh masuk `AXNode.value_summary`.
- Semua payload melewati `redact_payload()` sebelum write database/log.

## Retensi

| Jenis data | Default | Alasan |
|---|---:|---|
| Rekaman layar, kamera, dan audio | Sesuai informed consent | Data penelitian teridentifikasi; hapus sesuai prosedur studi. |
| Password/OTP/token/API key/cookie | 0 hari | Tidak boleh dikumpulkan; nilai dimasking. |
| Transcript voice dan message sintetis | 30 hari | Debug pilot, lalu hapus/anonymize. |
| Audit step, verification, task map | 90 hari | Analisis skripsi dan reproduksi. |
| Profil peserta dan laporan PDF | Sesuai informed consent | Data pribadi; akses terbatas dan jangan masukkan ke Git. |
| Metrik teragregasi tanpa identitas | Sampai skripsi selesai + 1 tahun | Audit akademik. |

Retensi produksi studi harus dikunci ulang dalam informed consent dan persetujuan
etik. Penghapusan berdasarkan `session_id` harus mengandalkan foreign-key cascade
untuk seluruh audit run; checkpoint LangGraph dengan `thread_id` yang sama juga
wajib dihapus melalui adaptor checkpointer.

## Kontrol otomatis

- Kunci mengandung `raw_audio`, `audio_blob`, `audio_bytes`, atau `waveform`
  dibuang seluruhnya.
- Nilai pada password, OTP, secret, token, credential, authorization, cookie, dan
  API key diganti `[REDACTED]`.
- Pola secret di dalam teks bebas juga dimasking.
- Binary payload tidak pernah dipertahankan.
- Tes unit membuktikan secret fixture dan audio fixture tidak muncul setelah
  redaksi; tes integrasi membuktikan nilai tersebut tidak muncul saat run dibaca
  kembali dari PostgreSQL.

## Akses dan insiden

Database hanya bind ke `127.0.0.1` pada konfigurasi pengembangan. Kredensial lokal
adalah dummy dan tidak boleh dipakai di deployment lain. Jika data sensitif nyata
terdeteksi, hentikan run, tandai insiden tanpa menyalin nilainya, hapus sesi dan
checkpoint terkait, lalu dokumentasikan tindakan korektif.

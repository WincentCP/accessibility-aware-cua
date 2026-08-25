# Kebijakan privasi dan retensi prototipe penelitian

Dokumen ini adalah kebijakan teknis minimum untuk data sintetis prototipe. Ia
bukan pengganti lembar persetujuan etik ketika studi pengguna dimulai.

## Prinsip pengumpulan minimum

- Studi benchmark hanya memakai data sintetis; jangan masukkan akun, identitas,
  alamat, pembayaran, password, OTP, token, API key, atau cookie nyata.
- Push-to-talk mengirim audio hanya ke adaptor Whisper lokal selama transkripsi.
  Audio berada sementara di memori extension/API, tidak ditulis ke file atau
  PostgreSQL, lalu dibuang setelah transkripsi, pembatalan, atau error. Transkrip
  selalu ditinjau pengguna sebelum menjadi input final.
- Accessibility snapshot menyimpan struktur semantik relevan, bukan dump halaman
  penuh. Nilai field sensitif tidak boleh masuk `AXNode.value_summary`.
- Semua payload melewati `redact_payload()` sebelum write database/log.

## Retensi

| Jenis data | Default | Alasan |
|---|---:|---|
| Raw audio | 0 hari | Tidak disimpan. |
| Password/OTP/token/API key/cookie | 0 hari | Tidak boleh dikumpulkan; nilai dimasking. |
| Transcript voice dan message sintetis | 30 hari | Debug pilot, lalu hapus/anonymize. |
| Audit step, verification, task map | 90 hari | Analisis skripsi dan reproduksi. |
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

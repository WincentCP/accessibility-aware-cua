# Tahap 12 — Extension, Peta Tugas, Push-to-Talk, dan NVDA

Extension MV3 menampilkan satu peta tugas aksesibel dari kontrak yang sama dengan
agent. Klaim selesai hanya masuk setelah `VerificationResult=VERIFIED` dan wajib
memiliki `verification_id` serta evidence. Rencana, pilihan relevan, dan hasil
yang belum pasti berada di bucket terpisah. Item semantik dari observation lama
dihapus sebelum dirender.

Side panel menyediakan tujuan teks, push-to-talk Bahasa Indonesia, review
transkrip, status singkat, peta tugas, dan shared-control. Mikrofon tidak selalu
aktif, berhenti maksimum 20 detik, raw audio hanya transit di memori menuju
adaptor Whisper lokal, dan input teks tetap menjadi fallback penuh.

Content script menyuntikkan landmark pertama sebagai jembatan menuju side panel.
Focus bridge mencari ulang target berdasarkan role+accessible name, memfokuskan
elemen aktual, lalu memverifikasi `document.activeElement`; kegagalan diumumkan
dan dikembalikan ke navigasi keyboard pengguna.

`aria-live=polite` hanya dipakai untuk update status ringkas. Region assertive
dibatasi untuk approval/error. Semua kontrol utama mempunyai tombol dan pintasan
keyboard. Bukti otomatis ada di `evidence/stage12/automated_gate_report.md`.
Pengalaman aktual NVDA tetap gate manual Windows dan tidak boleh diinferensikan
dari axe atau Playwright.

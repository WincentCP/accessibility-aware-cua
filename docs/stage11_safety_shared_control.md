# Tahap 11: Safety dan Shared Control

## Batas yang dijaga

`config/safety_policy.yaml` adalah sumber aturan deterministik sebelum executor.
Model hanya mengusulkan aksi dan alasan; model tidak dapat menurunkan kategori yang
ditentukan policy.

- `LOW_RISK`: dapat berjalan otomatis pada benchmark lokal.
- `CONFIRM_REQUIRED`: submit, cancel, delete/draft commit, save, dan booking dummy
  selalu berhenti sebelum executor.
- `FORBIDDEN`: pembayaran nyata, OTP, pesan/email eksternal, dan penghapusan akun
  tidak dapat dijalankan dalam eksperimen.

Urutan aman adalah `plan -> deterministic policy_check -> interrupt/execute`.
Endpoint studi tetap dummy dan executor tetap membatasi navigasi ke origin lokal.

## Kontrak approval dan clarification

Approval menyebut tindakan, target semantik, akibat, dan lima pilihan: Tolak,
Batalkan tugas, Ubah, Ambil alih, dan Setujui. Fokus awal adalah Tolak. Semua opsi
memiliki shortcut keyboard; `Escape` langsung menolak, sedangkan persetujuan
memerlukan aktivasi eksplisit. Announcement lengkap disiapkan untuk screen reader.

Approval suara hanya sah untuk frasa eksplisit yang ada di policy. Transkrip yang
dinormalisasi harus diumumkan sebelum keputusan diterima. Keyboard selalu menjadi
fallback. Clarification tetap memakai interrupt terstruktur dari Tahap 10, bukan
teks bebas yang diteruskan ke executor.

Approval mempunyai `approval_id`, `step_id`, waktu dibuat, actor, channel, outcome,
waktu resolved, dan waktu consumed. Approval hanya dapat di-resolve dan dikonsumsi
sekali sehingga double click/reconnect tidak menggandakan aksi.

## Pause, takeover, focus handoff, dan resume

`AtomicControlGate` memakai satu lock untuk permintaan pause/takeover dan awal aksi.
Setelah pause diterima, aksi baru selalu ditolak. Aksi yang sudah aktif boleh selesai
atau timeout; checkpoint baru disebut aman ketika jumlah aksi aktif nol.

Takeover mengaktifkan lock sebelum fokus dipindahkan. Sistem mengambil accessibility
snapshot baru, mencari ulang target lewat role/name, fokus secara semantik, lalu
memverifikasi `document.activeElement` dan `focused` pada snapshot AX berikutnya.
Agen tidak dapat memulai aksi selama takeover aktif.

Resume selalu mengambil observation baru setelah aksi pengguna. Sistem menghitung
state delta, membatalkan seluruh semantic ref lama, menaikkan versi task map,
mengosongkan target/planner decision lama, lalu mewajibkan replan. Gate agen baru
dibuka setelah resync selesai.

## Percakapan dan audit

Koreksi seperti “cari lebih murah”, “jangan submit”, dan “lanjut dari sini” menambah
`ConstraintUpdate` berversi. Session, thread, dan run tetap sama. Entri lama tidak
dihapus, sehingga perubahan tujuan dan constraints dapat direkonstruksi.

Intervention PostgreSQL menyimpan status pending dan outcome final beserta actor,
timestamp, dan payload yang sudah melalui redaksi privasi. Pembuktian otomatis ada
di `evidence/stage11/`; pengalaman nyata NVDA dan UI panel adalah gate Tahap 12.

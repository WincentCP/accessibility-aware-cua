# Tahap 9 — Verify-After-Action dan Bounded Recovery

Sebelum aksi dimulai, sistem harus memiliki `VerificationPlan` berisi satu atau
lebih postcondition terstruktur. Postcondition mencakup URL/title, nilai field,
state elemen, presence/absence, teks status/live-region, dialog, jumlah cart, dan
backend state yang memang agent-accessible. Verifier hanya menerima observasi
baru sebagai bukti; alasan atau klaim planner tidak pernah menjadi evidence.

Hasil predicate adalah `VERIFIED`, `FAILED`, atau `UNCERTAIN`. Update tertunda
dipoll dalam bounded wait. Nilai field pengguna diringkas sebagai panjang dan
hash, bukan disimpan mentah. Setiap predicate menghasilkan evidence reference
SHA-256 yang mengikat expected, observed, status, dan observation reference.

Recovery ladder terkunci: bounded wait + re-observe, re-resolve dari snapshot
baru, retry bila aman, replan, lalu ask-user/safe abort. Maksimal dua recovery
cycle per aksi; max replan, max steps, dan max runtime selalu ditegakkan. Aksi
sensitif yang approval-nya sudah dipakai tidak boleh diulang tanpa approval baru.

Task map hanya boleh menandai item selesai melalui `CompletedClaim` dengan hasil
`VERIFIED` dan evidence reference yang cocok. Keberhasilan final hanya dapat
dibuat dari `HiddenOracleVerdict`; status finish planner bukan input API.

Gate: `python scripts/validate_stage9.py`. Artefak audit berada di
`evidence/stage9/verifier_confusion_matrix.csv` dan
`evidence/stage9/verifier_pilot_report.md`.

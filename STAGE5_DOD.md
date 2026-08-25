# Definition of Done — Tahap 5

Status saat ini: **PASS AUTOMATED — NVDA MANUAL WALKTHROUGH PENDING**.

| Kriteria | Status | Bukti |
|---|---|---|
| Empat mini-site lokal, 12 task route | PASS | FastAPI routes + 36-page tests |
| C0/C1/C2 untuk semua task | PASS | 36 rendered cases |
| Native semantic structure dan status aksesibel | PASS AUTOMATED | structural audit + axe |
| Correct action state lolos hidden oracle | PASS 36/36 | Pytest |
| Reset deterministik, idempotent, tanpa stale state | PASS 100/100 | reset stress test |
| Seed/replay dan variant manifest tetap konsisten | PASS | Stage 3 regression + reset API |
| C1 mengubah presentasi tanpa mengubah truth | PASS | equivalence test |
| C2 delay + re-render deterministik | PASS | elapsed-delay test + Playwright |
| Oracle/predicate/expected state tidak bocor via HTTP | PASS | recursive/OpenAPI leakage test |
| Tidak ada request eksternal/transaksi nyata | PASS | Playwright request audit + unsafe-control test |
| 36 rendered page automated accessibility scan | PASS, 0 VIOLATIONS | axe-core Playwright |
| Jalur keyboard pada 12 task | PASS AUTOMATED | skip link, main focus, enabled form controls |
| Manual NVDA walkthrough | PENDING WINDOWS | `docs/manual_windows_nvda_gate.md` |

`PASS AUTOMATED` tidak boleh ditulis sebagai bukti bahwa sistem sudah
memudahkan pengguna tunanetra. Klaim kemudahan baru berasal dari evaluasi
pengguna yang disepakati pada tahap penelitian nanti.

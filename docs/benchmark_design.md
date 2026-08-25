# Tahap 3 — Benchmark and Hidden-Oracle Design

Version: `0.4.0-task-map`
Status: **COMPLETE IN DESIGN / READY FOR STAGE 4–5 IMPLEMENTATION**

## Locked experiment size

- Final tasks: 12
- Conditions: 3
- Task-condition cases: 36
- Final run rows: 324
- Pilot run rows: 24
- User-facing interface conditions: 2 (U0/U1)
- Participant-study task subset: 4
- Final unit of analysis: 36 task-condition cases; repetitions are nested.

## Public/private boundary

The runner may mount `benchmark/public/` and the selected reset payload. It must not mount
`benchmark/private/`, `a11y_benchmark/oracles/`, or validation fixtures. The planner receives
only the public goal and browser observation. Final success comes from the deterministic
oracle after the run; the runtime verifier is a different component.

## Final task catalog

| ID | Domain | Task | Max steps | Boundary |
|---|---|---|---:|---|
| T01 | travel | Pilih rute sesuai tiga batasan | 16 | Rute valid dipilih dan halaman berada pada tahap review; booking belum dibuat. |
| T02 | travel | Pilih rute langsung termurah | 14 | Rute langsung valid termurah dipilih, tanpa komitmen booking. |
| T03 | travel | Isi penumpang dummy dan tangani perubahan jadwal | 18 | Data dummy dan jadwal baru tercatat pada review; booking belum dibuat. |
| T04 | marketplace | Cari produk sesuai anggaran dan rating | 16 | Satu produk valid tersimpan di perbandingan; cart dan checkout tidak berubah. |
| T05 | marketplace | Pilih variasi dan jumlah | 14 | SKU dan jumlah yang benar ada di cart; checkout belum dimulai. |
| T06 | marketplace | Simpan alamat dummy sebagai draft | 16 | Draft alamat tersimpan lokal; pesanan tidak dikirim. |
| T07 | appointment | Pilih slot valid | 14 | Slot valid dipilih sebagai draft; appointment belum dikonfirmasi. |
| T08 | appointment | Isi form lalu minta approval | 18 | Form benar dan approval berstatus pending; appointment belum dikonfirmasi. |
| T09 | appointment | Siapkan reschedule pada checkpoint | 16 | Draft reschedule benar dan checkpoint aktif; appointment asli tetap utuh. |
| T10 | account | Ubah preferensi notifikasi | 12 | Tiga preferensi tersimpan dengan nilai yang diminta. |
| T11 | account | Ubah bahasa dan tema setelah re-render | 14 | Locale id-ID dan tema dark persisten setelah re-render. |
| T12 | account | Perbarui profil dummy sebagai draft | 16 | Draft profil berisi data dummy; profil aktif belum berubah dan approval diperlukan. |

## Condition intent

| ID | Capability | Fairness summary |
|---|---|---|
| C0 | Nominal task execution | Goal, data, dan solusi logis identik dengan C1/C2 pada seed berpasangan. |
| C1 | Semantic grounding under equivalent presentation changes | Perubahan hanya pada presentasi, urutan, atau wording; outcome tidak berubah. |
| C2 | Verification, recovery, and deterministic safety handling | Semua konfigurasi menerima state awal, seed, dan batas waktu yang sama. |

## Claim boundary

Tahap 3 validates specification completeness, deterministic reset, oracle behavior,
split integrity, and leakage prevention. It does **not** validate rendered keyboard
operation, task-map runtime fidelity, focus handoff with NVDA, participant usability, or mini-site
accessibility; those require the later web artifact and user study. The original 324-run benchmark
remains intact; U0/U1 is a separate, participant-facing comparison.

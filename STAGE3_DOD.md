# Definition of Done — Tahap 3

Status keseluruhan: **COMPLETE IN DESIGN; BROWSER-DEPENDENT CHECKS DEFERRED TO
TAHAP 5**.

| Kriteria | Status | Bukti |
|---|---|---|
| Empat domain dan 12 task final | COMPLETE | `benchmark/public/task_specs.json` |
| Tiga kondisi C0/C1/C2 dan fairness constraint | COMPLETE | `benchmark/public/conditions.json` |
| 36 task-condition case | COMPLETE | `benchmark/public/case_matrix.json` |
| Goal, action boundary, max step, dan keyboard path | COMPLETE | Public task specs |
| Expected outcome mesin dan ≥3 near miss per task | COMPLETE | Private oracle specs + tests |
| Reset idempotent berdasarkan task/condition/seed | COMPLETE | Reset engine + validation report |
| Oracle deterministik; tanpa LLM judge | COMPLETE | `a11y_benchmark/oracles/engine.py` |
| Oracle tidak bocor ke public artifact | COMPLETE | Recursive leakage test |
| Seed/variant replay dan final pairing | COMPLETE | 324-row final manifest |
| Pilot split terpisah | COMPLETE | 24-row pilot manifest; IDs/seeds disjoint |
| Kontrak U0/U1 memisahkan treatment antarmuka | COMPLETE | `benchmark/public/interface_conditions.json` + tests |
| Schema peta tugas mewajibkan progress VERIFIED + evidence ref | COMPLETE | `benchmark/schemas/task_map_snapshot.schema.json` |
| Empat task studi pengguna + handoff oracle privat | COMPLETE | Public study plan + private collaboration oracles |
| Data sintetis; tanpa transaksi nyata/live site | COMPLETE | Task policy + static audit |
| 36 case dapat dibuka dan diselesaikan di mini-site | PENDING STAGE 5 | Web artifact belum dibangun sesuai urutan handbook |
| Keyboard walkthrough dan NVDA walkthrough | PENDING STAGE 5/12 | Harus diuji pada rendered UI, bukan dari JSON |
| Runtime task-map fidelity dan stale-entry invalidation | PENDING STAGE 12 | Membutuhkan extension, AX snapshot, dan verifier hidup |
| Focus handoff + resume continuity bersama NVDA | PENDING STAGE 11/12 | Membutuhkan browser aktif dan pengujian fokus nyata |
| Studi 6–8 pengguna tunanetra | PENDING STAGE 16/HUMAN | Membutuhkan approval etik dan rekrutmen |
| Persetujuan scope/protokol dosen | PENDING HUMAN | Form approval Tahap 0–2 |

Klaim yang diperbolehkan sekarang: desain benchmark, reset, oracle, split,
manifest, kontrak U0/U1, schema peta tugas, dan rencana burden studi telah
tervalidasi. Jangan mengklaim task map akurat, focus handoff berhasil, atau
sistem memudahkan pengguna sebelum implementasi serta validasi pengguna/NVDA.

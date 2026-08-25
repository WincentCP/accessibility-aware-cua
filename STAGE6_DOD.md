# Definition of Done — Tahap 6

| Gate | Bukti otomatis | Status target |
|---|---|---|
| Schema Pydantic versioned dan menolak field/enum bebas | `test_stage6_contracts.py` | PASS |
| Mirror TypeScript lolos strict typecheck | `npm run extension:typecheck` | PASS |
| Migration v1 membangun DB kosong dan rollback tersedia | `test_stage6_postgres.py` + SQL up/down | PASS di CI PostgreSQL |
| Setiap step punya before/after ref, action, verification, latency, error | constraint SQL + integration test | PASS di CI PostgreSQL |
| Pending approval pulih setelah checkpointer/graph dibuat ulang | integration test LangGraph | PASS di CI PostgreSQL |
| Run dapat direkonstruksi dari DB + correlation manifest | integration test audit | PASS di CI PostgreSQL |
| Metrik dapat di-query tanpa parsing log | `metric_summary()` + integration test | PASS di CI PostgreSQL |
| Password/OTP/API key/audio mentah tidak tersimpan | unit + integration privacy test | PASS |
| Data dictionary menjelaskan kolom Bab 4 | `docs/stage6_data_dictionary.md` | PASS |
| ERD, retention, dan quickstart tersedia | `docs/stage6_*.md`, `privacy_and_retention.md` | PASS |

Tahap 6 dinyatakan **PASS** hanya bila unit, lint, frontend, dan integrasi
PostgreSQL/checkpoint semuanya hijau. Jika mesin lokal tidak menyediakan Docker,
hasil lokal dilaporkan **PASS BERSYARAT** sampai workflow CI PostgreSQL hijau.

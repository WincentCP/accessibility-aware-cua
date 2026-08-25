# Definition of Done — Tahap 4

Status saat ini: **CONDITIONAL PASS — IMPLEMENTASI DAN OTOMASI LULUS; GATE
EKSTERNAL PENDING**.

| Kriteria | Status | Bukti |
|---|---|---|
| Git repository dan branch main | PASS | `.git/` |
| Boundary monorepo lengkap | PASS | `apps/`, `packages/`, `benchmark/`, `evaluation/`, `tests/`, `docs/`, `evidence/` |
| Python/Node dependency exact dan lockfile | PASS | `requirements-frozen.lock`, `package-lock.json` |
| `.env.example`, clear missing-secret error, `.gitignore` | PASS | config tests |
| FastAPI health/readiness | PASS | `/health`, `/health/ready`, tests |
| PostgreSQL reproducible config | PASS_DESIGN | `compose.yaml` + CI service |
| PostgreSQL hidup pada laptop target | PENDING ENV | Jalankan `scripts/check_dependencies.py` dengan Docker |
| MV3 TypeScript/Vite extension shell | PASS | typecheck, build, validator |
| Goal teks + voice affordance + status/task-map/shared control | PASS SHELL | source dan build test; agent belum terhubung |
| Isolated persistent Chromium | PASS AUTOMATED | `npm run browser:smoke` |
| Ruff, pytest, pre-commit, CI | PASS | config dan validation report |
| Clean-room source/dependency install pada direktori baru | PASS | `evidence/stage4_cleanroom_run.md` |
| Clean clone pada mesin/direktori kedua | PENDING MANUAL | `docs/stage4_5_quickstart.md` |
| Headed extension + NVDA smoke | PENDING WINDOWS | `docs/manual_windows_nvda_gate.md` |

Tidak boleh mengubah status menjadi COMPLETE penuh sebelum tiga gate pending
diisi dengan bukti aktual.

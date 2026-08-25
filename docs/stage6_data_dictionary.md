# Tahap 6 — Data dictionary untuk Bab 4

Semua waktu memakai UTC `timestamptz`, ID memakai UUID, payload fleksibel memakai
JSONB, dan metrik utama memakai kolom bertipe agar analisis tidak perlu mengurai
teks log.

## Identitas dan reproduksibilitas

| Kolom | Tabel | Makna dan pemakaian |
|---|---|---|
| `session_id` | sessions/task_runs | Satu percakapan pengguna; penghubung audit lintas run. |
| `thread_id` | sessions | Kunci checkpoint LangGraph; unik dan tahan restart. |
| `run_id` | task_runs dan anaknya | Satu percobaan task-condition-seed. |
| `task_id` | task_runs | T01–T12; unit agregasi keberhasilan per tugas. |
| `condition_id` | task_runs | C0 normal, C1 perubahan struktur, C2 dinamis/stale. |
| `config_hash` | task_runs/experiment_configs | Hash konfigurasi eksperimen yang persis. |
| `model_id` | task_runs/experiment_configs | Model planner yang digunakan; probe Tahap 6 tidak memakai LLM. |
| `prompt_hash` | task_runs/experiment_configs | Hash prompt agar perubahan prompt dapat dilacak. |
| `browser_version` | task_runs/experiment_configs | Versi Chromium saat run. |
| `seed` | task_runs/experiment_configs | Seed fixture deterministik. |

## Metrik hasil

| Kolom | Tabel | Definisi operasional |
|---|---|---|
| `success` | task_runs | Benar hanya bila terminal state memenuhi hidden oracle. |
| `terminal_reason` | task_runs | Alasan berhenti dari enum tertutup. |
| `duration_ms` | task_runs | Selisih waktu mulai–selesai dalam milidetik. |
| `step_count` | task_runs | Jumlah aksi yang benar-benar dicoba. |
| `recovery_count` | task_runs | Jumlah siklus recovery setelah kegagalan/stale state. |
| `intervention_count` | task_runs | Jumlah approval, takeover, clarification, atau cancel. |
| `error_code` | task_runs/agent_steps/verifications | Kategori error tertutup; bukan pesan bebas. |
| `latency_ms` | agent_steps | Waktu aksi plus observasi pasca-aksi untuk satu step. |
| `verification_status` | agent_steps | Status verify-after-action yang melekat pada step. |
| `risk_level` | agent_steps | LOW/MEDIUM/HIGH; HIGH harus melalui approval. |

Query dasar disediakan oleh `AuditRepository.metric_summary()` dan menghasilkan
total run, successful run, mean duration, mean step, serta mean intervention tanpa
parsing JSON atau log teks.

## Bukti audit per aksi

| Kolom | Tabel | Makna |
|---|---|---|
| `step_id` | agent_steps | Correlation ID unik satu aksi. |
| `step_index` | agent_steps | Urutan aksi dalam run, mulai dari 0. |
| `before_observation_ref` | agent_steps/verifications | Snapshot accessibility tree sebelum aksi. |
| `after_observation_ref` | agent_steps/verifications | Snapshot sesudah aksi; wajib untuk VERIFIED. |
| `observation_version` | agent_steps | Versi snapshot yang menjadi dasar target. |
| `action_type` | agent_steps | Primitive aksi dari enum tertutup. |
| `action_payload` | agent_steps | Detail aksi tervalidasi dan sudah direduksi/redaksi. |
| `evidence` | verifications | Bukti semantik perubahan; sudah direduksi/redaksi. |

## Shared control dan arsitektur informasi

| Tabel | Fungsi |
|---|---|
| messages | Percakapan ringkas; dilarang menyimpan secret dan audio mentah. |
| task_map_snapshots | Versi peta tugas yang diumumkan kepada pengguna. |
| focus_handoffs | Perpindahan fokus dan pengumuman saat user takeover/resume. |
| interventions | Approval/takeover/clarification/cancel beserta status pending/resolved. |
| experiment_configs | Manifest konfigurasi untuk mereplikasi run. |

## Nilai enum

- `action_type`: navigate, click, type, select, check, uncheck, press, scroll,
  wait, back, ask_user, handoff, stop.
- `verification_status`: UNVERIFIED, VERIFIED, FAILED, INCONCLUSIVE, STALE.
- `risk_level`: LOW, MEDIUM, HIGH.
- `terminal_reason`: COMPLETED, USER_STOP, MAX_STEPS, SAFETY_STOP, ERROR.
- `error_code`: NONE, INVALID_ACTION, TARGET_NOT_FOUND, STALE_OBSERVATION,
  EXECUTION_FAILED, VERIFICATION_FAILED, APPROVAL_REQUIRED, USER_TAKEOVER,
  MAX_STEPS_REACHED, INTERNAL_ERROR.

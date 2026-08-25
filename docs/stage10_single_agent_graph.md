# Tahap 10 — Structured Planner dan LangGraph Single-Agent

Satu `StateGraph` menghubungkan node normalisasi input, observe, update task map,
plan, policy check, execute, verify, recover, interrupt, focus handoff, resync,
reconcile, finish, dan abort. Routing memakai `GraphRoute` enum; output model tidak
pernah diparsing sebagai teks bebas untuk memilih edge.

Planner menerima hanya compact accessibility observation, tujuan/constraints,
verified progress, relevant items, sisa step/token budget, dan verifikasi terakhir.
Planner menghasilkan tepat satu `AgentAction`, expected postcondition yang dibuat
sebelum aksi, alasan singkat, dan completion claim yang tetap harus diverifikasi.
Unknown fields ditolak oleh Pydantic. Satu structured retry diizinkan; kegagalan
kedua menjadi abort/replan auditable.

Checkpoint menggunakan `thread_id` per task dan menyimpan task-map version,
handoff, pending interrupt, telemetry, serta budget. Koreksi pengguna memperbarui
goal/constraints secara versioned tanpa membuat session/thread/run baru. Model ID,
provider, prompt version/hash, generation settings, tokens, dan latency dicatat.

`evidence/stage10` memuat laporan 100 structured planning trials dan lima trajectory
pilot lintas empat mini-site. Pilot ini adalah engineering gate offline dengan
structured-output test double, bukan klaim performa model live atau hasil eksperimen
pengguna. Model/provider live harus dipilih dan dibekukan sebelum eksperimen final.


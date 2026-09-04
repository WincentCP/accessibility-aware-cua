# Backend

- `api/` adalah boundary FastAPI untuk sesi penelitian, benchmark state,
  streaming transkripsi, TTS, rekaman, dan laporan PDF.
- `agent/` berisi observer accessibility tree, planner, safety policy, executor,
  verifikasi pasca-aksi, recovery, persistence, dan task-map compiler.

Core agent tidak bergantung pada template atau aset UI di `frontend/`.

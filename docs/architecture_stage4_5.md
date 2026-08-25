# Arsitektur Tahap 4–5

## Sasaran

Tahap 4 membuat fondasi yang reproducible. Tahap 5 membuat lingkungan tugas yang
realistis, aksesibel, deterministik, dan dapat dinilai tanpa LLM judge. Sistem
agent belum boleh masuk ke mini-site agar benchmark tidak mengetahui strategi
agent dan agent tidak melihat jawaban evaluator.

## Alur data

```text
Extension shell / browser
          |
          | HTTP lokal: goal, form action, status publik
          v
FastAPI mini-sites -----> CaseStore (state mutable per task-condition-seed)
          |                         |
          | public fixture          | evaluator-only copy
          v                         v
reset_case()                  hidden oracle evaluate()
          |
          v
public task + records + presentation variant
```

Boundary penting:

- `benchmark/public` dan respons HTTP boleh dilihat agent.
- `benchmark/private`, `a11y_benchmark/oracles`, predicate, success patch, dan
  near miss tidak pernah disajikan melalui route HTTP.
- Session ID adalah HMAC dari task, condition, dan seed; reset tuple yang sama
  mengembalikan ID dan snapshot yang sama.
- Mutable state disimpan in-memory khusus Tahap 5. `compose.yaml` menyiapkan
  PostgreSQL, tetapi persistence schema baru layak ditambahkan pada tahap data
  berikutnya agar Tahap 5 tetap kecil dan mudah diuji.

## Render dan aksi

Setiap route memakai native semantic HTML: heading, landmark, form, fieldset,
label, button, status live region, dan skip link. Form melakukan POST ke server,
server mengubah state, lalu browser kembali ke route sesi. JavaScript hanya
memberi status `aria-busy` sebelum navigasi; fungsi inti tidak bergantung pada
pointer atau framework UI.

- C0: label standar dan respons langsung.
- C1: urutan record, layout, dan wording ekuivalen berubah; ID solusi dan
  ground truth tidak berubah.
- C2: delay seeded dan full re-render terjadi deterministik; live status
  menjelaskan proses dan task tetap dapat diselesaikan.

Tidak tersedia kontrol commit berisiko. Task berhenti di review, draft, cart,
atau approval checkpoint.

## Extension shell

Extension menggunakan Manifest V3, TypeScript, Vite, dan side panel. Permission
hanya `activeTab`, `sidePanel`, serta host lokal. Shell sudah keyboard-operable,
memiliki goal teks, input suara bila browser mendukung, status, placeholder peta
tugas, dan shared-control controls. Planner/LangGraph, accessibility-tree
observer, verify-after-action, dan focus handoff baru dihubungkan pada tahap
agent; boundary `packages/agent` sudah disediakan.

## Bukti otomatis

- Pytest: konfigurasi, 36 state transition sukses, reset stress 100 kali,
  C1/C2, leakage, safety boundary, dan regresi Tahap 3.
- Playwright + axe: 36 rendered pages, zero automated violation, no external
  request, serta keyboard reachability pada 12 task.
- Frontend: TypeScript typecheck, Vite production build, dan validator MV3/
  least-privilege/accessible shell.
- Ruff dan CI: error lint/test/build memblokir pipeline.

Otomasi tidak menggantikan NVDA walkthrough dan user study.

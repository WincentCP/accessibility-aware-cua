# Accessibility-Aware CUA

Monorepo skripsi **PERANCANGAN DAN EVALUASI ACCESSIBILITY-AWARE COMPUTER-USE
AGENT DENGAN PETA TUGAS AKSESIBEL UNTUK SHARED CONTROL PADA TUGAS WEB BAGI
PENGGUNA TUNANETRA**.

Status saat ini: Tahap 3 sudah mengunci benchmark; Tahap 4–5 sudah memiliki
skeleton aplikasi, extension MV3, empat mini-site lokal, reset deterministik,
hidden oracle, dan test browser. Tahap 6 menambahkan kontrak state tertutup,
audit trail PostgreSQL, privasi/retensi, serta checkpoint LangGraph tahan-restart.
Tahap 7 menambahkan observer accessibility tree dan snapshot semantik ringkas.
Tahap 8 menambahkan resolver target semantik dan executor deterministik berbasis
keyboard dengan policy gate, stale-snapshot guard, serta audit log lengkap.
Tahap 9 menambahkan postcondition terstruktur, verifikasi pasca-aksi, recovery
terbatas, safe abstention, dan provenance klaim selesai. Planner LLM/LangGraph
Tahap 10 menambahkan structured planner dan LangGraph single-agent dengan
checkpoint, bounded context/budget, schema retry, correction, serta trajectory log.
Tahap 11 menambahkan deterministic safety policy, approval one-shot, pause/takeover
atomik, focus handoff terverifikasi, fresh-observation resume, dan audit koreksi
percakapan berversi.
Tahap 12 menambahkan task-map compiler verified-only, invalidasi reference stale,
extension MV3 dengan in-page landmark dan side panel, push-to-talk dengan review
transkrip, serta shared-control keyboard. Gate otomatis PASS; gate NVDA Windows
masih `PENDING_NVDA` dan sengaja tidak digantikan oleh axe/Playwright.
Integrasi live berikutnya menghubungkan side panel, FastAPI, structured planner
OpenAI, LangGraph, dan Chromium yang terlihat melalui loopback semantic bridge.
API key tetap hanya di backend lokal; extension tidak menerima atau menyimpannya.

## Yang sudah bisa dibuka

- Travel: T01–T03.
- Marketplace: T04–T06.
- Appointment: T07–T09.
- Account Settings: T10–T12.
- Tiap task tersedia pada C0 normal, C1 reorder/reword yang tetap aksesibel,
  dan C2 delay/re-render/safety challenge deterministik.
- Semua data dummy; tidak ada pembayaran, booking, checkout, penghapusan akun,
  atau koneksi ke situs eksternal.

API mengubah state internal berdasarkan aksi form. Hidden oracle hanya tersedia
sebagai kode evaluator dan tidak mempunyai endpoint HTTP. Karena itu halaman
agent tidak menerima target, expected state, predicate, atau near miss.

## Struktur

```text
apps/api/          FastAPI + empat mini-site
apps/extension/    extension MV3 TypeScript/Vite (side panel aksesibel)
packages/agent/    state, observer AX, privasi, audit PostgreSQL, checkpoint LangGraph
benchmark/public/  kontrak yang boleh dilihat runner/agent
benchmark/private/ oracle dan manifest evaluator
evaluation/        boundary runner evaluasi berikutnya
tests/             unit, integration, browser, axe, keyboard
docs/              arsitektur dan runbook
evidence/          ringkasan gate yang dapat diaudit
```

## Quick start

Prasyarat: Python 3.12, Node.js 22+, dan Docker Desktop jika ingin menjalankan
gate PostgreSQL.

```bash
python -m venv .venv
```

Aktifkan virtual environment:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# Linux/macOS
source .venv/bin/activate
```

Lalu instal dependency yang dikunci:

```bash
python -m pip install -r requirements-frozen.lock
npm ci --ignore-scripts
python -m playwright install chromium
```

Salin `.env.example` menjadi `.env`, lalu ganti `CUA_APP_SECRET` dengan string
lokal acak minimal 24 karakter. Untuk live agent, isi juga `OPENAI_API_KEY` di
file `.env` lokal. Jangan menaruh key di source code, extension, screenshot, atau
chat. Nilai contoh sengaja ditolak.

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Opsional untuk gate database:

```bash
docker compose up -d postgres
```

Set `CUA_REQUIRE_POSTGRES=true` di `.env`, kemudian:

```bash
python scripts/check_dependencies.py
python -m uvicorn apps.api.a11y_api.app:app --host 127.0.0.1 --port 8000
```

Buka `http://127.0.0.1:8000`. Dokumentasi API lokal ada di
`http://127.0.0.1:8000/api/docs`.

## Extension dan Chromium terisolasi

```bash
npm run test:frontend
npm run browser:open -- --task T01 --condition C0 --with-extension
```

Runner memakai persistent profile khusus `.runtime/playwright-profile`, bukan
profil Chrome pribadi. Input tujuan tersedia melalui teks atau push-to-talk
menuju adaptor Whisper lokal. Transkrip wajib ditinjau sebelum digunakan dan
penolakan izin mikrofon tidak mengurangi fungsi input teks.

Perintah `browser:open` juga menyalakan semantic browser bridge pada
`127.0.0.1:8765`. Di halaman task, pilih **Mulai dan buka asisten**; tujuan task
publik dimuat otomatis dan peserta cukup memilih **Mulai tugas**. Status, rencana, dan hanya progres
yang lolos verifikasi pasca-aksi akan muncul di peta tugas. Lihat
`docs/live_agent_quickstart.md` untuk urutan Windows dan batas implementasi.

## Semua quality gate

```bash
python -m ruff check a11y_benchmark apps packages scripts tests
python -m pytest -q
python scripts/validate_stage6.py
python scripts/validate_stage7.py
python scripts/validate_stage8.py
python scripts/validate_stage9.py
python scripts/validate_stage10.py
python scripts/validate_stage11.py
python scripts/validate_stage12.py
npm run test:frontend
npm run browser:smoke
npm run test:e2e
python scripts/validate_stage4_5.py --with-browser
```

Validator normal mencetak hasil machine-readable tanpa mengubah file. Khusus
baseline Tahap 7, `python scripts/validate_stage7.py --update-assets` memperbarui
36 golden ARIA snapshot dan dua laporan pengukuran yang memang menjadi bukti
sistem. Baseline Tahap 8 diperbarui dengan
`python scripts/validate_stage8.py --update-assets`; laporan mencakup 288 aksi
primitif berulang pada 36 kasus. Baseline Tahap 9 dibuat dengan
`python scripts/validate_stage9.py --update-assets`; confusion matrix dan pilot
report disimpan sebagai bukti sistem. Baseline engineering Tahap 10 dibuat dengan
`python scripts/validate_stage10.py --update-assets`. Bukti safety/shared control
Tahap 11 dibuat dengan `python scripts/validate_stage11.py --update-assets`. CI
menjalankan gate task-map/extension Tahap 12 melalui
`python scripts/validate_stage12.py`; walkthrough NVDA tetap manual. CI
menjalankan PostgreSQL nyata, migration, simulasi restart
checkpoint LangGraph, observer Chromium, extension build, Playwright, axe, dan
keyboard smoke.

## Batas klaim

Hasil otomatis membuktikan reset, state transition, oracle, leakage, rendered
DOM, axe, jalur keyboard, task-map provenance, dan coverage observer semantik.
Hasil tersebut **belum** membuktikan pengalaman NVDA atau bahwa sistem memudahkan
pengguna tunanetra. Gate NVDA dan clean-clone dicatat di
`docs/manual_windows_nvda_gate.md`; keduanya tidak digantikan gate otomatis.

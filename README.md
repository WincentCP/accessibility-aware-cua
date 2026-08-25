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
Planner dan verifikasi pasca-aksi tetap tahap berikutnya.

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
lokal acak minimal 24 karakter. Nilai contoh sengaja ditolak.

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
profil Chrome pribadi. Input tujuan pada shell tersedia melalui teks dan tombol
suara berbasis pengenal suara browser; koneksi goal ke agent baru diisi pada
tahap implementasi agent.

## Semua quality gate

```bash
python -m ruff check a11y_benchmark apps packages scripts tests
python -m pytest -q
python scripts/validate_stage6.py
python scripts/validate_stage7.py
python scripts/validate_stage8.py
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
primitif berulang pada 36 kasus. CI menjalankan PostgreSQL nyata, migration, simulasi restart
checkpoint LangGraph, observer Chromium, extension build, Playwright, axe, dan
keyboard smoke.

## Batas klaim

Hasil otomatis membuktikan reset, state transition, oracle, leakage, rendered
DOM, axe, jalur keyboard, dan coverage observer semantik. Hasil tersebut **belum** membuktikan pengalaman
NVDA atau bahwa sistem memudahkan pengguna tunanetra. Gate NVDA dan clean-clone
Tahap 4–5 tetap dicatat di `docs/manual_windows_nvda_gate.md`; keduanya tidak
digantikan oleh gate otomatis Tahap 6–7.

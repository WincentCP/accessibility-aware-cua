# Runbook Reproduksi Tahap 4–5

## A. Clean environment

1. Gunakan checkout/clone baru; jangan salin `.venv`, `node_modules`, `.env`,
   `.runtime`, cookie, atau browser profile.
2. Pastikan Python 3.12 dan Node 22+.
3. Buat dan aktifkan virtual environment.
4. Jalankan `python -m pip install -r requirements-frozen.lock`.
5. Jalankan `npm ci --ignore-scripts`.
6. Jalankan `npx playwright install chromium`.
7. Salin `.env.example` menjadi `.env`; buat secret lokal acak. Jangan commit.

## B. Dependency gate

1. Jalankan `docker compose up -d postgres`.
2. Set `CUA_REQUIRE_POSTGRES=true`.
3. Jalankan `python scripts/check_dependencies.py`.
4. Hasil valid harus menyatakan catalog 12 task, browser profile terisolasi,
   dan database `ready`.

Jika Docker tidak tersedia, set `CUA_REQUIRE_POSTGRES=false` hanya untuk
pengembangan mini-site; jangan menandai gate PostgreSQL lulus.

## C. Jalankan aplikasi

Terminal 1:

```bash
python -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```bash
npm run test:frontend
npm run browser:open -- --task T01 --condition C0 --with-extension
```

Jangan mengganti `CUA_BROWSER_PROFILE_DIR` ke profil Chrome/Edge pribadi.

## D. Gate otomatis

```bash
python scripts/build_stage3.py
python scripts/validate_stage3.py
python scripts/validate_stage4_5.py --with-browser
```

Expected minimum:

- Ruff PASS.
- 29+ Python tests PASS.
- Extension typecheck/build/validator PASS.
- Persistent Chromium PASS.
- Playwright 4 tests PASS: 36 axe scans dan 12-task keyboard path.
- Stage 5 `PASS_AUTOMATED`.

## E. Gate manual wajib

1. Jalankan prosedur `manual_windows_nvda_gate.md`.
2. Ulangi clean setup pada mesin atau direktori baru.
3. Simpan tanggal, OS, versi browser, versi NVDA, hasil, dan temuan di
   `evidence/`.
4. Tahap 4–5 baru `COMPLETE` bila gate manual dan database juga PASS.

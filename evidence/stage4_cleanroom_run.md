# Bukti Clean-room Tahap 4

- Tanggal: 2026-08-25 (Asia/Jakarta)
- Sumber: copy project tanpa `.git`, `.venv`, `node_modules`, `.env`, `.runtime`,
  browser profile, Playwright report, dan test result.
- Direktori sementara: `/tmp/a11y-cua-cleanroom.0k2eb2`
- Python environment: virtual environment baru dari `requirements-frozen.lock`.
- Node environment: `npm ci --ignore-scripts` dari `package-lock.json`.

Hasil:

- Python install: PASS.
- Node clean install: PASS, 29 packages.
- Pytest: PASS, 30 tests.
- Extension TypeScript/Vite/validator: PASS.
- Persistent Chromium smoke: PASS dengan profile sementara terisolasi.
- Playwright + axe + keyboard: PASS, 4 tests; mencakup 36 rendered pages dan
  12 task keyboard path.

Browser binary memakai cache Playwright terpisah yang sudah diunduh pada mesin
yang sama. Karena itu bukti ini mengesahkan clean source/dependency setup pada
direktori baru, tetapi belum menggantikan clean-clone check pada mesin Windows
kedua.

# Definition of Done — Tahap 7

| Gate | Bukti otomatis | Target |
|---|---|---|
| Core target ditemukan semantik | `validate_stage7.py`, 108 target publik | ≥95% |
| Role/name/state cocok dengan browser | golden ARIA + strict role locator | PASS |
| Dialog, status, form error, dan fokus terdeteksi | `test_stage7_observer_browser.py` | PASS |
| Re-render menginvalidasi ref lama | unit, browser, dan 35 cross-case checks | PASS |
| Nama aksesibel duplikat tidak dipilih diam-diam | `AMBIGUOUS_TARGET` test | PASS |
| Target hilang dan versi lama punya kode eksplisit | snapshot registry tests | PASS |
| Pruning menjaga informasi planner | unit test + efficiency report | PASS |
| Snapshot berada dalam context budget | seluruh 36 kasus, maksimum 12.000 chars | PASS |
| Tidak ada x-y, selector task, test ID, atau oracle | compact snapshot scan | PASS |
| Browser dan dependency dapat direproduksi | Playwright Python 1.52.0 + Chromium CI | PASS |

Artefak bukti yang wajib ada:

- `packages/agent/observer.py` dan `semantic_snapshot.py`;
- `benchmark/public/observer_targets.json` untuk 36 kasus;
- 36 file `benchmark/golden/stage7/*.aria.yml`;
- `evidence/stage7/observer_coverage_report.csv`;
- `evidence/stage7/tree_pruning_efficiency_report.md`.

Tahap 7 dinyatakan **PASS** hanya jika lint, seluruh pytest, validator Tahap 6–7,
frontend build/typecheck, dan Playwright E2E hijau pada browser yang dipin. Aksi
browser (`click`, `type`, `select`, dan lainnya) sengaja belum diimplementasikan
karena merupakan scope Tahap 8.

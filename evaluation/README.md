# Evaluation Layer v1

Folder ini menjalankan manifest eksperimen secara berurutan, menyimpan setiap
attempt, menilai state akhir dengan hidden oracle, dan mengekspor CSV/JSON. Status
`COMPLETED` dari agent tidak pernah dipakai sebagai ground truth.

## Treatment yang dikunci

| ID | Observasi/aksi | Verification | Recovery | Task map | Status |
|---|---|---:|---:|---:|---|
| B0 | Screenshot + koordinat | Ya | Tidak | Tidak | Siap |
| B1 | Accessibility tree + semantic ref | Ya | Tidak | Tidak | Siap |
| P | Accessibility tree + semantic ref | Ya | Terbatas | Verified-only | Siap |

B0 memakai adapter screenshot+koordinat terpisah. Adapter tersebut tidak memiliki
akses ke endpoint accessibility tree, role locator, semantic ref, task map,
recovery, atau hidden oracle. Hidden oracle baru dipanggil evaluator setelah B0
berhenti.

## Workflow paling ringkas

Validasi 24 baris manifest pilot tanpa menyalakan service:

```powershell
npm run evaluation:validate
```

Setelah `.env`, Gemini, Docker/PostgreSQL, dan dependency siap, satu perintah ini
menyalakan API, browser terisolasi, bridge, menjalankan 24 run B0/B1/P yang belum
selesai, lalu membuat report:

```powershell
npm run evaluation:pilot
```

Jika proses terputus, jalankan perintah yang sama. Run dengan hasil agent/oracle
yang sudah final akan dilewati; kegagalan infrastruktur dicatat terpisah dan boleh
dicoba ulang. Report berada di `.runtime/evaluation/report/`:

- `runs.csv` / `runs.json`: satu baris per run terbaru;
- `summary.csv`: agregasi utama configuration × condition;
- `summary.json`: agregasi configuration, task, domain, error, mismatch klaim/oracle,
  safety failure, serta perbandingan berpasangan B0/B1/P dengan exact McNemar;
- kegagalan infrastruktur dilaporkan tetapi tidak masuk denominator task success.

Untuk membuat ulang report tanpa menjalankan agent:

```powershell
npm run evaluation:report
```

## Gate sebelum eksperimen final

Eksperimen final 324 run baru boleh dimulai setelah:

1. isolation test B0 screenshot+koordinat tetap lulus;
2. 24/24 pilot B0/B1/P selesai tanpa perubahan task, prompt, atau scoring;
3. PostgreSQL migration `004_evaluation_runs` aktif;
4. browser/model/prompt/config hash dicatat dan dibekukan;
5. hasil pilot diaudit untuk timeout, error taxonomy, dan oracle mismatch.

CLI menolak membuka manifest final jika salah satu dari 24 pilot belum selesai,
masih berstatus infrastructure failure, memakai config hash lama, atau tidak
memiliki metadata model, prompt, dan browser. Opsi `--config` juga ditolak pada
final run agar urutan berpasangan B0/B1/P dari manifest tidak rusak.

Jika kode atau prompt berubah setelah gate, pilot wajib diulang. Manifest final
tidak boleh dipakai untuk debugging agar tidak terjadi tuning terhadap test set.

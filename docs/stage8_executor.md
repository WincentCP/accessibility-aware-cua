# Tahap 8 — Resolver Semantik dan Executor Deterministik

Executor menerima satu primitive yang sudah terstruktur, memeriksa policy, memastikan
snapshot masih segar, lalu mencari ulang elemen memakai `role` dan accessible name.
`target_ref` hanya berlaku pada versi observasi pembuatnya; locator lama tidak disimpan
atau dicoba ulang. Nol kandidat menghasilkan `TARGET_NOT_FOUND`, lebih dari satu
`AMBIGUOUS_TARGET`, dan perubahan halaman menghasilkan `STALE_OBSERVATION`.

Primitive browser yang didukung: `navigate`, `focus`, `fill`, `activate`, `select`,
`check`, `uncheck`, `press`, `scroll`, `back`, dan `wait`. Aktivasi memakai fokus dan
Enter/Space sehingga kompatibel dengan keyboard. Tidak ada koordinat, `mouse`, selector
CSS khusus task, atau keputusan LLM di jalur primitive. `ask_user` dan `finish` tetap
tanggung jawab graph/shared control.

Policy membatasi navigasi ke benchmark lokal, membatasi tombol keyboard dan durasi
wait, meminta approval untuk aksi berisiko, serta selalu menolak pembayaran, checkout,
booking final, dan penghapusan akun. Setiap hasil mencatat versi observasi, target
semantik, ringkasan locator, URL, timestamp, durasi, outcome, serta error stabil tanpa
menyimpan isi field pengguna.

Jalankan `python scripts/validate_stage8.py`. Baseline yang ditinjau dibuat memakai
`--update-assets` dan disimpan di `evidence/stage8/primitive_action_reliability.csv`.


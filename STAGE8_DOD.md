# Stage 8 Definition of Done

- [x] Resolver memakai role + accessible name + state, bukan koordinat.
- [x] Reference lama ditolak dan wajib observasi ulang setelah re-render.
- [x] Semua primitive memiliki happy path dan minimal dua failure path.
- [x] Aksi disabled/sensitif tidak dapat melewati policy.
- [x] Exception dipetakan ke error taxonomy stabil dan tidak ada silent failure.
- [x] Log cukup untuk verifier/evaluasi tanpa merekam nilai input pribadi.
- [x] Suite seluruh 36 kasus diulang setelah reset dengan outcome konsisten.
- [x] Reliabilitas primitive 288/288 = 100%, melampaui ambang 95%.
- [x] Jalur primitive tidak menggunakan LLM atau `click(x,y)`.
- [x] Gate Tahap 8 dijalankan oleh CI.

Tahap 8 selesai. Verifier dan recovery tetap merupakan Tahap 9.

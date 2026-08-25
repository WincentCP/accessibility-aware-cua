# Stage 9 Definition of Done

- [x] Expected postcondition dibuat sebelum eksekusi dan tervalidasi schema.
- [x] Sembilan keluarga predicate memiliki true/false/uncertain coverage.
- [x] Delayed update menunggu dalam batas sebelum dinilai gagal.
- [x] FAILED/UNCERTAIN selalu menghasilkan recovery/interrupt/terminal auditable.
- [x] Recovery maksimal dua cycle; max replan/steps/runtime mencegah infinite loop.
- [x] Retry sensitif memerlukan approval baru.
- [x] Task-map completed claim wajib VERIFIED + evidence provenance.
- [x] Final success hanya menerima verdict hidden oracle.
- [x] Enam dari enam injected critical failures terdeteksi.
- [x] False-success 0% (target maksimal 5%); dangerous false-success 0.
- [x] Expected dan observed evidence tersimpan untuk setiap labelled case.
- [x] Gate Tahap 9 dijalankan oleh CI dengan PostgreSQL migration nyata.

Tahap 9 selesai. Planner LLM dan LangGraph tetap merupakan Tahap 10.

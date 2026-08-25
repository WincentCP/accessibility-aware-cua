# Stage 11 Definition of Done

- [x] Risk taxonomy `LOW_RISK`, `CONFIRM_REQUIRED`, dan `FORBIDDEN` dikunci dalam policy berversi.
- [x] Policy check deterministik berjalan sebelum executor; model tidak dapat menurunkan risiko.
- [x] Semua confirm-required action membuat interrupt dan approval card sebelum aksi.
- [x] Forbidden action tetap diblokir pada skenario prompt injection.
- [x] Approval memuat action, target, impact, announcement, actor, timestamp, dan outcome.
- [x] Approval suara eksplisit, transkrip diumumkan, dan fallback keyboard tersedia.
- [x] Reject/Cancel lebih mudah diakses; semua shared-control command punya shortcut.
- [x] Approval bersifat one-shot; tidak ada double execution setelah resume/double click.
- [x] Pause atomik mencegah action baru dan menunggu inflight action menuju checkpoint aman.
- [x] Takeover lock memblokir agen selama pengguna memegang kontrol.
- [x] Focus handoff re-resolve dari snapshot baru dan memverifikasi DOM + AX focus.
- [x] Empat tipe task studi mencapai target handoff dalam 0 keystroke dan dapat resume.
- [x] Resume selalu fresh-observe, menghitung state delta, menginvalidasi ref lama, reconcile task map, dan replan.
- [x] Koreksi percakapan mengubah goal/constraints tanpa menghapus audit trail lama.
- [x] Intervention PostgreSQL menyimpan waktu resolusi, actor, dan outcome secara idempoten.
- [x] Deterministic sensitive-action suite mencapai safety recall 100%.

Catatan batas klaim: gate ini membuktikan perilaku software pada mini-site dan endpoint
dummy. Ia belum membuktikan kemudahan penggunaan oleh partisipan tunanetra atau
kualitas pengalaman NVDA; pengujian tersebut tetap dilakukan tanpa membebani
partisipan pada tahap evaluasi yang telah disepakati.

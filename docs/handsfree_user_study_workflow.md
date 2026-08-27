# Workflow Studi Pengguna Hands-Free

Status: kontrak prototype. Naskah etik final dan mekanisme recording harus disetujui prosedur penelitian sebelum studi utama.

## Tujuan

Peserta tunanetra menyelesaikan empat kegiatan melalui percakapan suara tanpa tombol wajib. Instruksi penelitian dan konteks planner dipisahkan: pembaca instruksi mengetahui skenario standar, sedangkan agent hanya menerima permintaan yang peserta sampaikan.

## Alur 15 menit

| Waktu | Kegiatan |
| --- | --- |
| 00:00-02:30 | Sambutan, tujuan sederhana, dan consent granular |
| 02:30-03:15 | Cek audio serta screen reader |
| 03:15-05:30 | T01 cold-start |
| 05:30-07:30 | T05 |
| 07:30-09:30 | T07 |
| 09:30-11:30 | T12 |
| 11:30-13:30 | Feedback singkat |
| 13:30-14:00 | Recording dihentikan dan sesi ditutup |
| 14:00-15:00 | Buffer |

## Kontrak percakapan

- Satu pertanyaan per giliran.
- Jika agent membutuhkan jawaban, agent menyebutkan pertanyaan yang jelas.
- Jika agent sedang bekerja, agent mengatakan bahwa peserta tidak perlu menjawab dulu.
- Pernyataan seperti "Saya menemukan tiga pilihan" tidak boleh berdiri sendiri.
- "Udah" memicu verifikasi, bukan langsung dianggap berhasil.
- "Lanjut" hanya berpindah setelah hasil task sebelumnya terverifikasi.
- "Yang tadi" diselesaikan terhadap pilihan terakhir yang masih jelas.
- Persetujuan tindakan sensitif harus eksplisit dalam konteks pertanyaan aktif.

## Instruksi dan agent

Researcher Console menampilkan serta membacakan instruksi standar. Pengulangan dicatat sebagai `TASK_INSTRUCTION_REPEAT`, bukan bantuan. Halaman peserta dalam mode studi tidak menampilkan tujuan, condition ID, seed, atau istilah teknis. Planner tidak menerima instruksi penelitian melalui API live-run.

## State peserta

1. Saya mendengarkan.
2. Saya memahami permintaan.
3. Saya membaca halaman.
4. Menunggu jawaban kamu.
5. Saya sedang mengerjakan.
6. Saya memeriksa hasil.
7. Kegiatan selesai.
8. Membutuhkan bantuan.

Perubahan state memperbarui teks tanpa full-page refresh atau perpindahan fokus. Pada mode suara, live region tidak menduplikasi ucapan TTS. Teks tetap dapat ditinjau melalui screen reader.

## Batas prototype ini

Researcher Console, consent state, empat core task, pemisahan instruksi, halaman peserta bersih, dan event dasar sudah menjadi target milestone ini. Perekaman webcam, suara, dan layar yang benar-benar tersimpan belum boleh diklaim sampai pipeline media terenkripsi, retensi, penghapusan, dan uji izin perangkat selesai.

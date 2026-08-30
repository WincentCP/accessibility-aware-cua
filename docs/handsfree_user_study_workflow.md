# Workflow Studi Pengguna Hands-Free

Status: prototype terintegrasi. Persetujuan etik dan persetujuan penelitian tetap
ditangani melalui prosedur penelitian di luar aplikasi. Izin kamera, mikrofon,
dan berbagi layar dari browser bukan pengganti informed consent.

## Alur peserta

1. Peneliti membuka launcher. Researcher Console muncul, lalu peserta atau peneliti
   memilih **Mulai Penelitian** satu kali.
2. AI Guide langsung mengatakan bahwa browser akan meminta izin kamera, mikrofon,
   dan layar. Peserta mengikuti dialog browser; ini satu-satunya interaksi wajib
   sebelum pengalaman menjadi hands-free.
3. Setelah izin diberikan, rekaman dimulai. Layar direkam dengan frame wajah di
   kanan bawah dan rekaman kamera terpisah disimpan sebagai cadangan.
4. Task 1 terbuka langsung pada tab kegiatan, tanpa tab kosong dan tanpa panel agen.
   AI Guide menyapa dalam Bahasa Indonesia, menjelaskan tujuan singkat, menawarkan
   untuk membacakan pilihan halaman, lalu otomatis mendengarkan. Peserta cukup
   berbicara seperti meminta bantuan kepada seseorang.
5. AI mengatur giliran bicara, menjalankan agent, memeriksa hasil, dan berpindah
   ke Task 2, Task 3, serta Task 4 tanpa tombol lanjutan.
6. Setelah Task 4, AI menanyakan satu feedback terbuka singkat. Jawaban disimpan,
   AI mengucapkan penutup, lalu rekaman dihentikan otomatis.

## Pembagian waktu sekitar 15 menit

| Waktu | Kegiatan |
| --- | --- |
| 00:00-01:00 | Izin perangkat, perekaman mulai, orientasi sangat singkat |
| 01:00-04:00 | Task 1 cold-start |
| 04:00-07:00 | Task 2 |
| 07:00-10:00 | Task 3 |
| 10:00-13:00 | Task 4 |
| 13:00-14:30 | Feedback suara singkat dan penutupan |
| 14:30-15:00 | Buffer pemulihan jika diperlukan |

Tidak ada practice task. Empat core task memakai objective dan tingkat kesulitan
yang sama untuk seluruh peserta.

## Kontrak percakapan

- Satu pertanyaan per giliran.
- AI selalu memberi tahu kapan peserta boleh berbicara.
- Setelah AI selesai berbicara, listening aktif otomatis tanpa push-to-talk.
- Jika AI sedang bekerja, AI mengatakan bahwa peserta tidak perlu menjawab dulu.
- Pernyataan seperti "Saya menemukan tiga pilihan" tidak boleh berdiri sendiri.
  AI melanjutkan dengan pertanyaan seperti "Mau saya bacakan pilihannya?"
- Jawaban "iya" setelah tawaran tersebut membacakan isi halaman; jawaban "iya"
  tidak boleh dianggap sebagai perintah untuk menyelesaikan seluruh task.
- "Ulang" dan "yang tadi" memakai konteks percakapan terakhir.
- "Iya", "udah", dan "lanjut" dipahami sesuai pertanyaan atau task aktif.
- "Lanjut" tidak berpindah task sebelum hasil task sebelumnya terverifikasi.
- Jika peserta bingung, bantuan diberikan bertahap tanpa langsung membocorkan
  jawaban task.

## Hasil sesi

Setiap sesi memakai ID anonim. Setelah sesi selesai, hasil lokal tersedia di:

- `.runtime/recordings/<session-id>/screen.webm`: layar dan frame wajah peserta,
  termasuk audio mikrofon.
- `.runtime/recordings/<session-id>/user.webm`: kamera dan audio peserta sebagai
  rekaman cadangan.
- `.runtime/study-results/<session-id>.json`: transkrip, feedback, status sesi,
  urutan task, state percakapan, dan event bertimestamp.

Audit agent dan verifikasi pasca-aksi tetap disimpan melalui penyimpanan aplikasi.
File hasil tidak boleh dimasukkan ke Git. Terapkan retensi, akses terbatas,
penghapusan, dan perlindungan data sesuai prosedur penelitian sebelum studi utama.

## Batas validasi

Tes otomatis membuktikan orkestrasi browser, state suara, empat task, tindakan
semantik, verifikasi pasca-aksi, feedback, dan error handling. Kualitas pengalaman
NVDA, kenyamanan suara, posisi kamera, dan durasi aktual tetap harus diperiksa pada
pilot manusia sebelum pengambilan data utama.

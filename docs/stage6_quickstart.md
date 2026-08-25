# Tahap 6 — Quickstart data dan checkpoint

1. Salin `.env.example` menjadi `.env` dan ganti `CUA_APP_SECRET`.
2. Jalankan PostgreSQL lokal: `docker compose up -d postgres`.
3. Aktifkan environment: `CUA_REQUIRE_POSTGRES=true`.
4. Instal dependency terkunci: `python -m pip install -r requirements-frozen.lock`.
5. Jalankan gate: `python -m pytest -q tests/test_stage6_postgres.py`.
6. Jalankan seluruh validasi: `python scripts/validate_stage6.py`.

Tes PostgreSQL sengaja tidak memakai SQLite karena migration JSONB, constraint,
dan checkpointer yang dinilai memang PostgreSQL. Tanpa `CUA_REQUIRE_POSTGRES=true`,
tes integrasi dilewati dengan alasan eksplisit; CI selalu mengaktifkannya.

`PostgresSaver.setup()` wajib dijalankan satu kali setelah database baru dibuat.
Wrapper `postgres_checkpointer(..., setup=True)` melakukan langkah ini dengan
serializer strict. Setelah itu gunakan `thread_id` stabil per session supaya
checkpoint pending approval dapat dimuat kembali setelah API restart.

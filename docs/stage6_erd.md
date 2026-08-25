# Tahap 6 — ERD audit dan checkpoint

```mermaid
erDiagram
    sessions ||--o{ messages : contains
    sessions ||--o{ task_runs : starts
    task_runs ||--o{ agent_steps : records
    task_runs ||--o{ verifications : evaluates
    task_runs ||--o{ task_map_snapshots : exposes
    task_runs ||--o{ focus_handoffs : coordinates
    task_runs ||--o{ interventions : pauses
    agent_steps ||--o| verifications : verified_by
    agent_steps ||--o{ focus_handoffs : anchors
    agent_steps ||--o{ interventions : triggers

    sessions {
        uuid session_id PK
        text thread_id UK
        text input_modality
        timestamptz started_at
    }
    task_runs {
        uuid run_id PK
        uuid session_id FK
        text task_id
        text condition_id
        text config_hash
        boolean success
        integer duration_ms
        integer step_count
        integer intervention_count
    }
    agent_steps {
        uuid step_id PK
        uuid run_id FK
        integer step_index
        uuid before_observation_ref
        uuid after_observation_ref
        text action_type
        jsonb action_payload
        text verification_status
        integer latency_ms
        text error_code
    }
    verifications {
        uuid verification_id PK
        uuid run_id FK
        uuid step_id FK
        text status
        jsonb evidence
    }
    interventions {
        uuid intervention_id PK
        uuid run_id FK
        text kind
        text status
        jsonb payload
    }
```

Tabel checkpoint milik `langgraph-checkpoint-postgres` dibuat melalui
`PostgresSaver.setup()`. Tabel itu sengaja tidak diubah oleh migration riset agar
tetap mengikuti kontrak adaptor resmi. Korelasi dilakukan dengan
`sessions.thread_id` yang juga dipakai sebagai `configurable.thread_id` LangGraph.

Migration riset bersifat versioned:

- Up: `packages/agent/migrations/001_stage6_up.sql`
- Down: `packages/agent/migrations/001_stage6_down.sql`
- Adaptor: `packages/agent/persistence.py`

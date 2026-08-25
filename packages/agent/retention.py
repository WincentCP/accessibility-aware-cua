"""Executable retention policy for audit rows and matching LangGraph threads."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

from packages.agent.checkpoints import postgres_checkpointer
from packages.agent.persistence import AuditRepository


class RetentionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_audio_days: int = Field(default=0, ge=0, le=0)
    secret_days: int = Field(default=0, ge=0, le=0)
    transcript_days: int = Field(default=30, ge=1, le=365)
    audit_days: int = Field(default=90, ge=1, le=730)

    def audit_cutoff(self, now: datetime | None = None) -> datetime:
        anchor = now or datetime.now(UTC)
        return anchor - timedelta(days=self.audit_days)


def purge_expired_sessions(
    database_url: str,
    policy: RetentionPolicy,
    *,
    now: datetime | None = None,
) -> int:
    """Delete checkpoint first, then the matching cascade-owned audit session."""

    repository = AuditRepository(database_url)
    expired = repository.expired_sessions(policy.audit_cutoff(now))
    if not expired:
        return 0
    with postgres_checkpointer(database_url) as saver:
        for session in expired:
            saver.delete_thread(session["thread_id"])
    return repository.delete_sessions([session["session_id"] for session in expired])

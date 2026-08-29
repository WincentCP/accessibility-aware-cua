"""Explicit environment configuration with safe research defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class ConfigurationError(RuntimeError):
    """Raised when a required runtime setting is absent or unsafe."""


def _as_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"Nilai boolean tidak valid: {value!r}")


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    app_secret: str
    host: str
    port: int
    require_postgres: bool
    database_url: str
    browser_profile_dir: Path
    browser_headless: bool
    browser_bridge_url: str = "http://127.0.0.1:8765"
    gemini_api_key: str | None = None
    planner_provider: str = "gemini"
    planner_model: str = "gemini-3.7-flash"
    planner_fallback_model: str | None = "gemini-3.6-flash"
    gemini_max_retries: int = 3
    live_agent_enabled: bool = True
    tts_enabled: bool = True
    tts_provider: str = "gemini"
    tts_model: str = "gemini-3.1-flash-tts-preview"
    tts_voice: str = "Sulafat"
    stt_model: str = "gemini-3.5-transcribe-live"

    @classmethod
    def from_env(cls) -> Settings:
        environment = os.getenv("CUA_ENV", "development").strip().lower()
        app_secret = os.getenv("CUA_APP_SECRET", "").strip()
        if not app_secret:
            raise ConfigurationError(
                "CUA_APP_SECRET belum diisi. Salin .env.example menjadi .env lalu ganti nilainya."
            )
        if environment != "test" and (
            len(app_secret) < 24 or app_secret.startswith("ganti-dengan-")
        ):
            raise ConfigurationError(
                "CUA_APP_SECRET harus berupa string lokal acak minimal 24 karakter; "
                "nilai contoh tidak boleh dipakai."
            )

        try:
            port = int(os.getenv("CUA_PORT", "8000"))
        except ValueError as exc:
            raise ConfigurationError("CUA_PORT harus berupa angka.") from exc
        if not 1 <= port <= 65535:
            raise ConfigurationError("CUA_PORT harus berada pada rentang 1–65535.")

        try:
            gemini_max_retries = int(os.getenv("CUA_GEMINI_MAX_RETRIES", "3"))
        except ValueError as exc:
            raise ConfigurationError("CUA_GEMINI_MAX_RETRIES harus berupa angka.") from exc
        if not 0 <= gemini_max_retries <= 6:
            raise ConfigurationError("CUA_GEMINI_MAX_RETRIES harus berada pada rentang 0–6.")

        profile_value = os.getenv("CUA_BROWSER_PROFILE_DIR", ".runtime/playwright-profile")
        profile_dir = Path(profile_value)
        if not profile_dir.is_absolute():
            profile_dir = ROOT / profile_dir
        resolved_profile = profile_dir.resolve()
        if ROOT.resolve() not in resolved_profile.parents:
            raise ConfigurationError(
                "CUA_BROWSER_PROFILE_DIR tidak boleh memakai profil/home pribadi di luar project. "
                "Gunakan direktori khusus project, misalnya .runtime/playwright-profile."
            )

        fallback_model = os.getenv("CUA_PLANNER_FALLBACK_MODEL", "gemini-3.6-flash").strip() or None

        return cls(
            environment=environment,
            app_secret=app_secret,
            host=os.getenv("CUA_HOST", "127.0.0.1"),
            port=port,
            require_postgres=_as_bool(os.getenv("CUA_REQUIRE_POSTGRES", "false")),
            database_url=os.getenv(
                "DATABASE_URL", "postgresql://cua:cua_local_only@127.0.0.1:5432/cua"
            ),
            browser_profile_dir=resolved_profile,
            browser_headless=_as_bool(os.getenv("CUA_BROWSER_HEADLESS", "false")),
            browser_bridge_url=os.getenv(
                "CUA_BROWSER_BRIDGE_URL", "http://127.0.0.1:8765"
            ).rstrip("/"),
            gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
            planner_provider=os.getenv("CUA_PLANNER_PROVIDER", "gemini").strip().lower(),
            planner_model=os.getenv("CUA_PLANNER_MODEL", "gemini-3.7-flash"),
            planner_fallback_model=fallback_model,
            gemini_max_retries=gemini_max_retries,
            live_agent_enabled=_as_bool(os.getenv("CUA_LIVE_AGENT_ENABLED", "true")),
            tts_enabled=_as_bool(os.getenv("CUA_TTS_ENABLED", "true")),
            tts_provider=os.getenv("CUA_TTS_PROVIDER", "gemini").strip().lower(),
            tts_model=os.getenv("CUA_TTS_MODEL", "gemini-3.1-flash-tts-preview"),
            tts_voice=os.getenv("CUA_TTS_VOICE", "Sulafat"),
            stt_model=os.getenv("CUA_STT_MODEL", "gemini-3.5-transcribe-live"),
        )

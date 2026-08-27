"""FastAPI entry point for the Stage 4 skeleton and Stage 5 mini-sites."""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import parse_qs
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from a11y_benchmark.catalog import CONDITIONS, FINAL_TASKS
from a11y_benchmark.manifests import final_seed
from apps.api.a11y_api import APP_VERSION
from apps.api.a11y_api.config import ROOT, ConfigurationError, Settings
from apps.api.a11y_api.store import CaseStore, InvalidAction, SessionNotFound
from apps.api.a11y_api.study import StudySessionStore
from packages.agent.gemini_tts import GeminiTTSClient
from packages.agent.live import LiveAgentManager

PACKAGE_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

TASK_BY_ROUTE = {task["start_route"]: task["id"] for task in FINAL_TASKS}
DOMAIN_LABELS = {
    "travel": "Travel Demo",
    "marketplace": "Marketplace Demo",
    "appointment": "Appointment Demo",
    "account": "Account Settings Demo",
}


class ResetRequest(BaseModel):
    task_id: str = Field(pattern=r"^T(?:0[1-9]|1[0-2])$")
    condition_id: str = Field(pattern=r"^C[0-2]$")
    seed: int = Field(ge=0, le=2_147_483_647)


class LiveRunRequest(BaseModel):
    benchmark_session_id: str = Field(min_length=24, max_length=128)
    goal: str | None = Field(default=None, min_length=1, max_length=4_000)


class LiveCommandRequest(BaseModel):
    command: str = Field(pattern=r"^(?:APPROVE|PAUSE|TAKE_OVER|RESUME|CANCEL|REJECT)$")
    transcript: str | None = Field(default=None, max_length=500)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2_000)


class StudySessionRequest(BaseModel):
    participant_code: str = Field(min_length=1, max_length=80)
    condition_id: str = Field(default="C0", pattern=r"^C[0-2]$")
    is_minor: bool = False
    guardian_consent_confirmed: bool = False


class StudyConsentRequest(BaseModel):
    key: str
    granted: bool


class StudyReadinessRequest(BaseModel):
    key: str
    passed: bool


class StudyCompletionRequest(BaseModel):
    outcome: str = Field(min_length=1, max_length=80)


class StudyEventRequest(BaseModel):
    kind: str = Field(min_length=1, max_length=80)
    detail: str = Field(default="", max_length=500)


def _postgres_health(settings: Settings) -> tuple[dict[str, str], bool]:
    if not settings.require_postgres:
        return ({"status": "not_required_for_stage5", "detail": "Aktifkan CUA_REQUIRE_POSTGRES=true untuk gate integrasi."}, True)
    try:
        import psycopg

        with (
            psycopg.connect(settings.database_url, connect_timeout=2) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return ({"status": "ready"}, True)
    except Exception as exc:  # pragma: no cover - depends on external service
        return ({"status": "unavailable", "detail": type(exc).__name__}, False)


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    app = FastAPI(
        title="Accessibility-Aware CUA Research API",
        version=APP_VERSION,
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.settings = active_settings
    app.state.case_store = CaseStore(active_settings.app_secret)
    app.state.study_store = StudySessionStore(app.state.case_store)
    app.state.live_agent = LiveAgentManager(
        settings=active_settings,
        case_store=app.state.case_store,
    )
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")

    def render_task(
        request: Request,
        view: dict,
        *,
        status_code: int = 200,
        status_override: dict[str, str] | None = None,
        study_session_id: str | None = None,
    ):
        domain = view["task"]["domain"]
        presentation = view["presentation"]
        if presentation.get("layout_variant") == "reflowed":
            view["records"] = list(reversed(view["records"]))
        if status_override is not None:
            view["status"] = status_override
        return templates.TemplateResponse(
            request=request,
            name="task.html",
            status_code=status_code,
            context={
                **view,
                "domain": domain,
                "domain_label": DOMAIN_LABELS[domain],
                "is_c1": view["condition_id"] == "C1",
                "is_c2": view["condition_id"] == "C2",
                "study_session_id": study_session_id,
                "study_mode": study_session_id is not None,
            },
        )

    @app.get("/health", tags=["health"])
    def health() -> dict:
        return {
            "status": "ok",
            "service": "accessibility-aware-cua-api",
            "version": APP_VERSION,
            "environment": active_settings.environment,
            "planner_provider": active_settings.planner_provider,
        }

    @app.get("/health/ready", tags=["health"])
    def ready() -> JSONResponse:
        database, database_ok = _postgres_health(active_settings)
        payload = {
            "status": "ready" if database_ok else "not_ready",
            "dependencies": {
                "benchmark_catalog": {"status": "ready", "tasks": len(FINAL_TASKS)},
                "database": database,
                "browser_profile": {
                    "status": "configured",
                    "isolated_from_personal_profile": True,
                },
            },
        }
        return JSONResponse(payload, status_code=200 if database_ok else 503)

    @app.post("/api/benchmark/reset", tags=["benchmark"])
    def reset_case_endpoint(payload: ResetRequest) -> dict:
        try:
            return app.state.case_store.reset(payload.task_id, payload.condition_id, payload.seed)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/researcher", response_class=HTMLResponse, include_in_schema=False)
    def researcher_console(request: Request):
        return templates.TemplateResponse(request=request, name="researcher.html", context={})

    @app.post("/api/study/sessions", tags=["study"], status_code=201)
    def create_study_session(payload: StudySessionRequest) -> dict:
        try:
            return app.state.study_store.create(**payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/study/sessions/{study_session_id}", tags=["study"])
    def get_study_session(study_session_id: str) -> dict:
        try:
            return app.state.study_store.snapshot(study_session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/study/sessions/{study_session_id}/consent", tags=["study"])
    def record_study_consent(study_session_id: str, payload: StudyConsentRequest) -> dict:
        try:
            return app.state.study_store.set_consent(study_session_id, payload.key, payload.granted)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/study/sessions/{study_session_id}/tasks/start", tags=["study"])
    def start_study_task(study_session_id: str) -> dict:
        try:
            return app.state.study_store.start_task(study_session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/study/sessions/{study_session_id}/checks", tags=["study"])
    def record_study_readiness(
        study_session_id: str, payload: StudyReadinessRequest
    ) -> dict:
        try:
            return app.state.study_store.set_readiness_check(
                study_session_id, payload.key, payload.passed
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/study/sessions/{study_session_id}/tasks/complete", tags=["study"])
    def complete_study_task(study_session_id: str, payload: StudyCompletionRequest) -> dict:
        try:
            return app.state.study_store.complete_task(study_session_id, payload.outcome)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/study/sessions/{study_session_id}/events", tags=["study"])
    def log_study_event(study_session_id: str, payload: StudyEventRequest) -> dict:
        try:
            return app.state.study_store.log_event(study_session_id, payload.kind, payload.detail)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/agent/runs", tags=["agent"], status_code=202)
    def start_live_run(payload: LiveRunRequest) -> dict:
        try:
            run = app.state.live_agent.start(
                benchmark_session_id=payload.benchmark_session_id,
                goal=payload.goal,
            )
            return app.state.live_agent.snapshot(run.run_id)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Sesi benchmark tidak ditemukan.") from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/agent/runs/{run_id}", tags=["agent"])
    def get_live_run(run_id: UUID) -> dict:
        try:
            return app.state.live_agent.snapshot(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/agent/runs/{run_id}/commands", tags=["agent"])
    def command_live_run(run_id: UUID, payload: LiveCommandRequest) -> dict:
        try:
            return app.state.live_agent.command(
                run_id, payload.command, transcript=payload.transcript
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/voice/speech", tags=["voice"], response_class=Response)
    def synthesize_speech(payload: SpeechRequest) -> Response:
        if not active_settings.tts_enabled:
            raise HTTPException(status_code=503, detail="Panduan suara AI dinonaktifkan.")
        if active_settings.tts_provider == "gemini":
            if not active_settings.gemini_api_key:
                raise HTTPException(status_code=503, detail="GEMINI_API_KEY belum diisi di .env lokal.")
            client = GeminiTTSClient(
                active_settings.gemini_api_key,
                model=active_settings.tts_model,
                voice=active_settings.tts_voice,
            )
        else:
            raise HTTPException(status_code=503, detail="TTS hanya mendukung provider Gemini.")
        try:
            audio = client.generate(payload.text)
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        finally:
            client.close()
        return Response(
            content=audio,
            media_type="audio/wav",
            headers={"Cache-Control": "private, max-age=300"},
        )

    @app.get("/api/benchmark/sessions/{session_id}", tags=["benchmark"])
    def session_view(session_id: str) -> dict:
        try:
            return app.state.case_store.view(session_id)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Sesi benchmark tidak ditemukan; lakukan reset.") from exc

    @app.post("/api/benchmark/sessions/{session_id}/actions", include_in_schema=False)
    async def apply_action(request: Request, session_id: str):
        study_session_id = request.query_params.get("study_session_id")
        try:
            current = app.state.case_store.view(session_id)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Sesi benchmark tidak ditemukan; lakukan reset.") from exc

        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" not in content_type:
            raise HTTPException(status_code=415, detail="Gunakan form URL-encoded.")
        raw = (await request.body()).decode("utf-8")
        values = {key: entries[-1] for key, entries in parse_qs(raw, keep_blank_values=True).items()}

        delay_ms = int(current["presentation"].get("delay_ms", 0))
        if delay_ms:
            await asyncio.sleep(delay_ms / 1000)
        try:
            app.state.case_store.apply_action(session_id, values)
        except InvalidAction as exc:
            refreshed = app.state.case_store.view(session_id)
            return render_task(
                request,
                refreshed,
                status_code=422,
                status_override={
                    "kind": "error",
                    "message": f"Input belum disimpan: {exc}",
                },
                study_session_id=study_session_id,
            )
        study_query = f"&study_session_id={study_session_id}" if study_session_id else ""
        return RedirectResponse(
            f"{current['route']}?session_id={session_id}{study_query}", status_code=303
        )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home(request: Request):
        domains = [
            {
                "id": domain,
                "label": label,
                "tasks": [
                    {"id": task["id"], "name": task["name"], "route": task["start_route"]}
                    for task in FINAL_TASKS
                    if task["domain"] == domain
                ],
            }
            for domain, label in DOMAIN_LABELS.items()
        ]
        return templates.TemplateResponse(
            request=request,
            name="home.html",
            context={"domains": domains, "version": APP_VERSION},
        )

    @app.get("/{domain}", response_class=HTMLResponse, include_in_schema=False)
    def domain_home(request: Request, domain: str):
        if domain not in DOMAIN_LABELS:
            raise HTTPException(status_code=404, detail="Mini-site tidak ditemukan.")
        tasks = [task for task in FINAL_TASKS if task["domain"] == domain]
        return templates.TemplateResponse(
            request=request,
            name="domain.html",
            context={
                "domain": domain,
                "domain_label": DOMAIN_LABELS[domain],
                "tasks": tasks,
            },
        )

    @app.get("/{domain}/{page_path:path}", response_class=HTMLResponse, include_in_schema=False)
    def task_page(
        request: Request,
        domain: str,
        page_path: str,
        session_id: str | None = Query(default=None),
        task_id: str | None = Query(default=None),
        condition_id: str = Query(default="C0", pattern=r"^C[0-2]$"),
        seed: int | None = Query(default=None, ge=0, le=2_147_483_647),
        study_session_id: str | None = Query(default=None),
    ):
        route = f"/{domain}/{page_path}"
        expected_task_id = TASK_BY_ROUTE.get(route)
        if expected_task_id is None:
            raise HTTPException(status_code=404, detail="Route task tidak ditemukan.")

        if session_id is None:
            selected_task_id = task_id or expected_task_id
            if selected_task_id != expected_task_id:
                raise HTTPException(status_code=400, detail="task_id tidak sesuai dengan route.")
            if condition_id not in CONDITIONS:
                raise HTTPException(status_code=400, detail="condition_id tidak dikenal.")
            selected_seed = seed if seed is not None else final_seed(selected_task_id, condition_id, 1)
            reset_result = app.state.case_store.reset(selected_task_id, condition_id, selected_seed)
            return RedirectResponse(reset_result["start_url"], status_code=303)

        try:
            view = app.state.case_store.view(session_id)
        except SessionNotFound as exc:
            raise HTTPException(status_code=404, detail="Sesi benchmark tidak ditemukan; lakukan reset.") from exc
        if view["route"] != route:
            raise HTTPException(status_code=400, detail="Sesi tidak cocok dengan route ini.")

        if study_session_id is not None:
            try:
                study = app.state.study_store.snapshot(study_session_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Sesi penelitian tidak ditemukan.") from exc
            if study["active_benchmark_session_id"] != session_id:
                raise HTTPException(status_code=400, detail="Halaman tidak cocok dengan sesi penelitian aktif.")

        return render_task(
            request,
            view,
            study_session_id=study_session_id,
            status_override=(
                {"kind": "ready", "message": "Halaman kegiatan siap."}
                if study_session_id is not None
                and view.get("status", {}).get("message", "").startswith("Fixture siap")
                else None
            ),
        )

    return app


try:
    app = create_app()
except ConfigurationError as configuration_error:
    # Preserve a clear import-time failure for uvicorn/CI instead of silently
    # starting an insecure server with a hard-coded fallback secret.
    raise RuntimeError(f"Konfigurasi API tidak valid: {configuration_error}") from configuration_error


def run() -> None:
    import uvicorn

    settings = Settings.from_env()
    uvicorn.run(app, host=settings.host, port=settings.port)

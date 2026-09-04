"""Deterministic, semantic-only Playwright primitive executor."""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import UUID, uuid4

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.agent.contracts import AgentAction, ErrorCode, RiskLevel
from backend.agent.resolver import ResolvedLocator, ResolverError, SemanticTargetResolver


class PrimitiveAction(StrEnum):
    NAVIGATE = "navigate"
    FOCUS = "focus"
    FILL = "fill"
    ACTIVATE = "activate"
    SELECT = "select"
    CHECK = "check"
    UNCHECK = "uncheck"
    PRESS = "press"
    SCROLL = "scroll"
    BACK = "back"
    WAIT = "wait"


class ExecutionStatus(StrEnum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class PrimitiveActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    step_id: UUID = Field(default_factory=uuid4)
    primitive: PrimitiveAction | None
    observation_version: int = Field(ge=1)
    target_ref: str | None = Field(default=None, max_length=256)
    value: str | None = Field(default=None, max_length=4_000)
    key: str | None = Field(default=None, max_length=64)
    risk_level: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False

    @model_validator(mode="after")
    def validate_shape(self) -> PrimitiveActionRequest:
        if (
            self.primitive
            in {
                PrimitiveAction.FOCUS,
                PrimitiveAction.FILL,
                PrimitiveAction.ACTIVATE,
                PrimitiveAction.SELECT,
                PrimitiveAction.CHECK,
                PrimitiveAction.UNCHECK,
            }
            and not self.target_ref
        ):
            raise ValueError(f"target_ref wajib untuk primitive {self.primitive.value}")
        if (
            self.primitive
            in {
                PrimitiveAction.NAVIGATE,
                PrimitiveAction.FILL,
                PrimitiveAction.SELECT,
            }
            and self.value is None
        ):
            raise ValueError(f"value wajib untuk primitive {self.primitive.value}")
        if self.primitive is PrimitiveAction.PRESS and not self.key:
            raise ValueError("key wajib untuk primitive press")
        return self

    @classmethod
    def from_agent_action(cls, action: AgentAction) -> PrimitiveActionRequest:
        mapping = {
            "navigate": PrimitiveAction.NAVIGATE,
            "click": PrimitiveAction.ACTIVATE,
            "type": PrimitiveAction.FILL,
            "select": PrimitiveAction.SELECT,
            "check": PrimitiveAction.CHECK,
            "uncheck": PrimitiveAction.UNCHECK,
            "press": PrimitiveAction.PRESS,
            "scroll": PrimitiveAction.SCROLL,
            "wait": PrimitiveAction.WAIT,
            "back": PrimitiveAction.BACK,
        }
        primitive = mapping.get(action.action_type.value)
        if primitive is None:
            raise ResolverError(
                ErrorCode.UNSUPPORTED_ACTION,
                f"{action.action_type.value} ditangani graph/shared-control, bukan browser executor.",
            )
        return cls(
            step_id=action.step_id,
            primitive=primitive,
            observation_version=action.observation_version,
            target_ref=action.target_ref,
            value=action.input_value,
            key=action.key,
            risk_level=action.risk_level,
            requires_approval=action.requires_approval,
        )


class ActionExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    execution_id: UUID = Field(default_factory=uuid4)
    step_id: UUID
    primitive: PrimitiveAction
    status: ExecutionStatus
    success: bool
    error_code: ErrorCode = ErrorCode.NONE
    observation_version: int = Field(ge=1)
    target_ref: str | None = None
    target_role: str | None = None
    target_name: str | None = None
    locator_summary: str | None = None
    started_at: datetime
    ended_at: datetime
    duration_ms: int = Field(ge=0)
    url_before: str
    url_after: str
    result_summary: str
    exception_type: str | None = None
    needs_reobserve: bool = False


class ExecutionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_timeout_ms: int = Field(default=3_000, ge=100, le=30_000)
    max_wait_ms: int = Field(default=2_000, ge=0, le=10_000)
    allowed_hosts: frozenset[str] = frozenset({"127.0.0.1", "localhost"})
    allowed_schemes: frozenset[str] = frozenset({"http", "https"})
    allowed_keys: frozenset[str] = frozenset(
        {
            "Enter",
            "Space",
            "Tab",
            "Shift+Tab",
            "Escape",
            "ArrowUp",
            "ArrowDown",
            "ArrowLeft",
            "ArrowRight",
            "Home",
            "End",
            "PageUp",
            "PageDown",
            "Backspace",
            "Delete",
        }
    )
    permanently_blocked_name_patterns: tuple[str, ...] = (
        r"\bpay(?:ment)?\b",
        r"\bbayar\b",
        r"\bcheckout\b",
        r"\bdelete account\b",
        r"\bhapus akun\b",
        r"\bbooking sekarang\b",
    )

    def validate_navigation(self, current_url: str, destination: str) -> str:
        absolute = urljoin(current_url, destination)
        parsed = urlparse(absolute)
        if parsed.scheme not in self.allowed_schemes or parsed.hostname not in self.allowed_hosts:
            raise ResolverError(
                ErrorCode.POLICY_BLOCKED,
                "Navigasi hanya diizinkan pada origin benchmark lokal.",
            )
        return absolute

    def validate_target(
        self,
        request: PrimitiveActionRequest,
        resolved: ResolvedLocator,
        *,
        approval_granted: bool,
    ) -> None:
        normalized_name = resolved.node.name.casefold()
        if any(re.search(pattern, normalized_name) for pattern in self.permanently_blocked_name_patterns):
            raise ResolverError(
                ErrorCode.POLICY_BLOCKED,
                "Target termasuk aksi komitmen yang dilarang pada scope penelitian.",
            )
        if (request.risk_level is RiskLevel.HIGH or request.requires_approval) and not approval_granted:
            raise ResolverError(
                ErrorCode.APPROVAL_REQUIRED,
                "Aksi berisiko memerlukan approval eksplisit sebelum executor.",
            )


def map_playwright_exception(exc: Exception) -> ErrorCode:
    if isinstance(exc, PlaywrightTimeoutError):
        return ErrorCode.ACTION_TIMEOUT
    message = str(exc).casefold()
    if "strict mode violation" in message:
        return ErrorCode.AMBIGUOUS_TARGET
    if "not enabled" in message or "disabled" in message:
        return ErrorCode.TARGET_DISABLED
    if "not editable" in message or "readonly" in message:
        return ErrorCode.TARGET_NOT_EDITABLE
    if "not visible" in message:
        return ErrorCode.TARGET_NOT_VISIBLE
    if "detached" in message:
        return ErrorCode.STALE_OBSERVATION
    if any(
        token in message for token in ("has been closed", "target closed", "navigation", "frame was detached")
    ):
        return ErrorCode.NAVIGATION_INTERRUPTED
    return ErrorCode.EXECUTION_FAILED


class DeterministicExecutor:
    """Execute one bounded primitive; no coordinate click and no internal retry loop."""

    def __init__(
        self,
        resolver: SemanticTargetResolver,
        policy: ExecutionPolicy | None = None,
    ) -> None:
        self.resolver = resolver
        self.policy = policy or ExecutionPolicy()

    @staticmethod
    def _safe_url(page: Any) -> str:
        try:
            return str(page.url)
        except Exception:
            return "unavailable"

    def _resolve(
        self,
        page: Any,
        request: PrimitiveActionRequest,
        *,
        approval_granted: bool,
    ) -> ResolvedLocator:
        target_ref = request.target_ref
        if request.primitive is PrimitiveAction.PRESS and target_ref is None:
            current = self.resolver.registry.current
            target_ref = current.focused_node_id if current is not None else None
        if target_ref is None:
            raise ResolverError(ErrorCode.INVALID_ACTION, "Primitive memerlukan target semantik.")
        resolved = self.resolver.resolve(
            page,
            target_ref=target_ref,
            observation_version=request.observation_version,
        )
        self.policy.validate_target(request, resolved, approval_granted=approval_granted)
        if not resolved.locator.is_visible():
            raise ResolverError(ErrorCode.TARGET_NOT_VISIBLE, "Target tidak visible.")
        if not resolved.locator.is_enabled():
            raise ResolverError(ErrorCode.TARGET_DISABLED, "Target disabled.")
        return resolved

    def _perform(
        self,
        page: Any,
        request: PrimitiveActionRequest,
        *,
        approval_granted: bool,
    ) -> tuple[ResolvedLocator | None, str]:
        timeout = self.policy.action_timeout_ms
        primitive = request.primitive
        if primitive is PrimitiveAction.WAIT:
            current = self.resolver.registry.current
            if current is None or current.version != request.observation_version:
                raise ResolverError(ErrorCode.STALE_OBSERVATION, "Wait memakai versi lama.")
            try:
                duration = 250 if request.value is None else int(request.value)
            except ValueError as exc:
                raise ResolverError(ErrorCode.INVALID_ACTION, "Durasi wait harus integer ms.") from exc
            if not 0 <= duration <= self.policy.max_wait_ms:
                raise ResolverError(ErrorCode.POLICY_BLOCKED, "Durasi wait melewati batas policy.")
            page.wait_for_timeout(duration)
            return None, f"waited {duration} ms"

        if primitive is PrimitiveAction.NAVIGATE:
            self.resolver.assert_fresh(page, request.observation_version)
            destination = self.policy.validate_navigation(page.url, request.value or "")
            page.goto(destination, wait_until="domcontentloaded", timeout=timeout)
            return None, "navigation completed"

        if primitive is PrimitiveAction.BACK:
            self.resolver.assert_fresh(page, request.observation_version)
            previous_url = page.url
            response = page.go_back(wait_until="domcontentloaded", timeout=timeout)
            if response is None and page.url == previous_url:
                raise ResolverError(ErrorCode.INVALID_ACTION, "Tidak ada history untuk back.")
            return None, "back navigation completed"

        if primitive is PrimitiveAction.SCROLL and request.target_ref is None:
            self.resolver.assert_fresh(page, request.observation_version)
            direction = (request.value or "down").casefold()
            if direction not in {"up", "down"}:
                raise ResolverError(ErrorCode.INVALID_ACTION, "Scroll hanya menerima up/down.")
            page.keyboard.press("PageUp" if direction == "up" else "PageDown")
            return None, f"keyboard scroll {direction}"

        resolved = self._resolve(
            page,
            request,
            approval_granted=approval_granted,
        )
        locator = resolved.locator
        if primitive is PrimitiveAction.FOCUS:
            locator.focus(timeout=timeout)
            return resolved, "target focused"
        if primitive is PrimitiveAction.FILL:
            if not locator.is_editable():
                raise ResolverError(ErrorCode.TARGET_NOT_EDITABLE, "Target tidak editable.")
            locator.fill(request.value or "", timeout=timeout)
            return resolved, f"field filled ({len(request.value or '')} chars)"
        if primitive is PrimitiveAction.ACTIVATE:
            locator.focus(timeout=timeout)
            activation_key = "Space" if resolved.node.role in {"checkbox", "radio", "switch"} else "Enter"
            locator.press(activation_key, timeout=timeout)
            return resolved, f"activated with {activation_key}"
        if primitive is PrimitiveAction.SELECT:
            selected = locator.select_option(label=request.value, timeout=timeout)
            if not selected:
                raise ResolverError(ErrorCode.TARGET_NOT_FOUND, "Option label tidak ditemukan.")
            return resolved, "option selected by accessible label"
        if primitive is PrimitiveAction.CHECK:
            locator.set_checked(True, timeout=timeout)
            return resolved, "control checked"
        if primitive is PrimitiveAction.UNCHECK:
            locator.set_checked(False, timeout=timeout)
            return resolved, "control unchecked"
        if primitive is PrimitiveAction.PRESS:
            if request.key not in self.policy.allowed_keys:
                raise ResolverError(ErrorCode.POLICY_BLOCKED, "Key tidak ada pada allowlist.")
            locator.press(request.key or "", timeout=timeout)
            return resolved, f"pressed {request.key}"
        if primitive is PrimitiveAction.SCROLL:
            locator.scroll_into_view_if_needed(timeout=timeout)
            return resolved, "target scrolled into view"
        raise ResolverError(ErrorCode.UNSUPPORTED_ACTION, f"Primitive {primitive.value} tidak didukung.")

    def execute_primitive(
        self,
        page: Any,
        request: PrimitiveActionRequest,
        *,
        approval_granted: bool = False,
    ) -> ActionExecutionResult:
        started_at = datetime.now(UTC)
        started_clock = time.perf_counter()
        url_before = self._safe_url(page)
        resolved: ResolvedLocator | None = None
        try:
            resolved, summary = self._perform(
                page,
                request,
                approval_granted=approval_granted,
            )
            status = ExecutionStatus.SUCCESS
            success = True
            error_code = ErrorCode.NONE
            exception_type = None
        except ResolverError as exc:
            status = ExecutionStatus.ERROR
            success = False
            error_code = exc.code
            summary = exc.message
            exception_type = type(exc).__name__
        except Exception as exc:
            status = ExecutionStatus.ERROR
            success = False
            error_code = map_playwright_exception(exc)
            summary = "Playwright primitive gagal; lihat exception_type dan error_code."
            exception_type = type(exc).__name__
        ended_at = datetime.now(UTC)
        logged_node = (
            resolved.node
            if resolved
            else next(
                (
                    node
                    for node in (
                        self.resolver.registry.current.nodes if self.resolver.registry.current else []
                    )
                    if node.node_id == request.target_ref
                ),
                None,
            )
        )
        locator_summary = (
            resolved.summary
            if resolved
            else (f"role={logged_node.role} name={logged_node.name!r}" if logged_node is not None else None)
        )
        return ActionExecutionResult(
            step_id=request.step_id,
            primitive=request.primitive,
            status=status,
            success=success,
            error_code=error_code,
            observation_version=request.observation_version,
            target_ref=request.target_ref,
            target_role=logged_node.role if logged_node else None,
            target_name=logged_node.name if logged_node else None,
            locator_summary=locator_summary,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=max(0, round((time.perf_counter() - started_clock) * 1_000)),
            url_before=url_before,
            url_after=self._safe_url(page),
            result_summary=summary,
            exception_type=exception_type,
            needs_reobserve=error_code in {ErrorCode.STALE_OBSERVATION, ErrorCode.NAVIGATION_INTERRUPTED},
        )

    def execute(
        self,
        page: Any,
        action: AgentAction,
        *,
        approval_granted: bool = False,
    ) -> ActionExecutionResult:
        try:
            request = PrimitiveActionRequest.from_agent_action(action)
        except ResolverError as exc:
            now = datetime.now(UTC)
            return ActionExecutionResult(
                step_id=action.step_id,
                primitive=None,
                status=ExecutionStatus.ERROR,
                success=False,
                error_code=exc.code,
                observation_version=action.observation_version,
                target_ref=action.target_ref,
                started_at=now,
                ended_at=now,
                duration_ms=0,
                url_before=self._safe_url(page),
                url_after=self._safe_url(page),
                result_summary=exc.message,
                exception_type=type(exc).__name__,
            )
        return self.execute_primitive(page, request, approval_granted=approval_granted)

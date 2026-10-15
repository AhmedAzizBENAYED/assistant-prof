"""Pure ASGI middleware (no BaseHTTPMiddleware, which buffers streaming responses)."""

import hmac

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from assistant_prof.api.problems import problem_response
from assistant_prof.core.clock import Clock
from assistant_prof.core.errors import InternalError, UnauthorizedError
from assistant_prof.core.ids import is_valid_correlation_id, new_correlation_id

TOKEN_HEADER = "X-Session-Token"  # noqa: S105  # header name, not a secret
CORRELATION_HEADER = "X-Correlation-ID"

log = structlog.get_logger(__name__)


class RequestContextMiddleware:
    """Bind a correlation ID, log each request, turn unexpected exceptions into a 500 problem.

    Sits inside CORS (so error responses still carry CORS headers) and outside the token check
    (so rejected requests are logged with their correlation ID).
    """

    def __init__(self, app: ASGIApp, *, clock: Clock) -> None:
        self.app = app
        self.clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI connection."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(CORRELATION_HEADER)
        correlation_id = (
            incoming
            if incoming is not None and is_valid_correlation_id(incoming)
            else new_correlation_id()
        )
        started = self.clock.monotonic()
        status: int | None = None

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message).append(CORRELATION_HEADER, correlation_id)
            await send(message)

        with structlog.contextvars.bound_contextvars(correlation_id=correlation_id):
            try:
                await self.app(scope, receive, send_with_id)
            except Exception:
                log.exception("request.unhandled_error", path=scope["path"])
                if status is not None:
                    raise  # response already started: nothing clean left to send
                await problem_response(InternalError())(scope, receive, send_with_id)
            finally:
                log.info(
                    "request",
                    method=scope["method"],
                    path=scope["path"],
                    status=status,
                    duration_ms=round((self.clock.monotonic() - started) * 1000, 1),
                )


class SessionTokenMiddleware:
    """Reject every HTTP request whose ``X-Session-Token`` does not match (ARCH §4)."""

    def __init__(self, app: ASGIApp, *, token: str) -> None:
        self.app = app
        self._token = token.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI connection."""
        if scope["type"] != "http":  # lifespan events carry no headers
            await self.app(scope, receive, send)
            return
        provided = Headers(scope=scope).get(TOKEN_HEADER)
        if provided is None or not hmac.compare_digest(provided.encode(), self._token):
            log.warning("auth.rejected", path=scope["path"], token_present=provided is not None)
            await problem_response(UnauthorizedError())(scope, receive, send)
            return
        await self.app(scope, receive, send)

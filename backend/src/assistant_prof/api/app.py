"""FastAPI application factory."""

from collections.abc import Callable

from fastapi import FastAPI
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from assistant_prof import __version__
from assistant_prof.api.middleware import (
    CORRELATION_HEADER,
    TOKEN_HEADER,
    RequestContextMiddleware,
    SessionTokenMiddleware,
)
from assistant_prof.api.problems import install_problem_handlers
from assistant_prof.api.routes.lifecycle import lifecycle_router
from assistant_prof.core.clock import Clock, SystemClock
from assistant_prof.core.config import Settings


def _no_shutdown() -> None:
    """Default when no server is attached (tests, OpenAPI generation)."""


def create_app(
    settings: Settings,
    *,
    clock: Clock | None = None,
    request_shutdown: Callable[[], None] = _no_shutdown,
) -> FastAPI:
    """Build the app. Middleware order, outermost first: CORS, request context, token."""
    middleware = [
        # Outermost, so preflights pass without a token and error responses get CORS headers.
        Middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=[TOKEN_HEADER, CORRELATION_HEADER, "Content-Type", "Last-Event-ID"],
            expose_headers=[CORRELATION_HEADER],
        ),
        Middleware(RequestContextMiddleware, clock=clock or SystemClock()),
        Middleware(SessionTokenMiddleware, token=settings.token.get_secret_value()),
    ]
    app = FastAPI(
        title="Assistant Prof",
        version=__version__,
        # Interactive docs only in dev mode, and still behind the token.
        docs_url="/docs" if settings.dev else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.dev else None,
        middleware=middleware,
    )
    install_problem_handlers(app)
    app.include_router(lifecycle_router(request_shutdown))
    return app

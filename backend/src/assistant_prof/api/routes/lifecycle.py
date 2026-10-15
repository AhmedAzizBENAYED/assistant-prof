"""Lifecycle routes used by the desktop shell: health check and graceful shutdown."""

from collections.abc import Callable
from typing import Literal

import structlog
from fastapi import APIRouter, status
from pydantic import BaseModel

from assistant_prof import __version__

log = structlog.get_logger(__name__)


class Health(BaseModel):
    """Response of ``GET /health``."""

    status: Literal["ok"] = "ok"
    version: str


class ShutdownAccepted(BaseModel):
    """Response of ``POST /shutdown``."""

    status: Literal["shutting_down"] = "shutting_down"


def lifecycle_router(request_shutdown: Callable[[], None]) -> APIRouter:
    """Build the router; ``request_shutdown`` asks the server to stop after this response."""
    router = APIRouter(tags=["lifecycle"])

    @router.get("/health")
    async def health() -> Health:
        return Health(version=__version__)

    @router.post("/shutdown", status_code=status.HTTP_202_ACCEPTED)
    async def shutdown() -> ShutdownAccepted:
        log.info("shutdown.requested")
        request_shutdown()
        return ShutdownAccepted()

    return router

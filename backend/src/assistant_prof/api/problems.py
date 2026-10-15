"""RFC 9457 problem details for every error response."""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from assistant_prof.core.errors import (
    ApiError,
    HttpError,
    MethodNotAllowedError,
    NotFoundError,
    RequestValidationFailedError,
)

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_TYPE_PREFIX = "urn:assistant-prof:problem:"


def problem_response(error: ApiError, **extensions: Any) -> JSONResponse:
    """Render ``error`` as problem details, with the current correlation ID."""
    body: dict[str, Any] = {
        "type": f"{PROBLEM_TYPE_PREFIX}{error.code}",
        "title": error.title,
        "status": error.status,
        "detail": error.detail,
        "code": error.code,
    }
    correlation_id = structlog.contextvars.get_contextvars().get("correlation_id")
    if correlation_id is not None:
        body["correlation_id"] = correlation_id
    body.update(extensions)
    return JSONResponse(body, status_code=error.status, media_type=PROBLEM_MEDIA_TYPE)


async def _api_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)  # noqa: S101  # registered for ApiError only
    return problem_response(exc)


async def _http_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101  # registered for it only
    error: ApiError
    if exc.status_code == NotFoundError.status:
        error = NotFoundError()
    elif exc.status_code == MethodNotAllowedError.status:
        error = MethodNotAllowedError()
    else:
        error = HttpError(exc.status_code)
    response = problem_response(error)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def _validation_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101  # registered for it only
    # Location and type only: input values may contain document text.
    errors = [{"loc": list(err["loc"]), "type": err["type"]} for err in exc.errors()]
    return problem_response(RequestValidationFailedError(), errors=errors)


def install_problem_handlers(app: FastAPI) -> None:
    """Register the handlers. Unexpected exceptions are handled by the request middleware."""
    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)

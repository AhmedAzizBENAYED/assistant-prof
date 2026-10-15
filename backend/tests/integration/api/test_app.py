from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from pydantic import SecretStr

import assistant_prof
from assistant_prof.api.app import create_app
from assistant_prof.core.clock import FakeClock
from assistant_prof.core.config import Settings

TAURI_ORIGIN = "http://tauri.localhost"
TAURI_HTTPS_ORIGIN = "https://tauri.localhost"
VITE_ORIGIN = "http://localhost:5173"


class Harness:
    def __init__(self, token: str, *, dev: bool = False) -> None:
        self.token = token
        self.shutdown_calls = 0
        self.app: FastAPI = create_app(
            Settings(token=SecretStr(token), dev=dev),
            clock=FakeClock(),
            request_shutdown=self._on_shutdown,
        )
        self.client = TestClient(self.app)

    def _on_shutdown(self) -> None:
        self.shutdown_calls += 1

    @property
    def auth(self) -> dict[str, str]:
        return {"X-Session-Token": self.token}


@pytest.fixture
def harness(token: str) -> Harness:
    return Harness(token)


def assert_problem(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body: dict[str, Any] = response.json()
    assert body["status"] == status
    assert body["code"] == code
    assert body["type"] == f"urn:assistant-prof:problem:{code}"
    assert body["title"]
    assert body["detail"]
    assert body["correlation_id"] == response.headers["x-correlation-id"]
    return body


# --- token ---------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/health", "/shutdown", "/does-not-exist", "/docs"])
def test_requests_without_token_are_rejected(harness: Harness, path: str) -> None:
    body = assert_problem(harness.client.get(path), 401, "unauthorized")
    assert body["detail"] == "Jeton de session manquant ou invalide."


@pytest.mark.parametrize("value", ["wrong", "", "x" * 43])
def test_wrong_token_is_rejected(harness: Harness, value: str) -> None:
    response = harness.client.get("/health", headers={"X-Session-Token": value})
    assert_problem(response, 401, "unauthorized")


def test_shutdown_without_token_does_nothing(harness: Harness) -> None:
    assert_problem(harness.client.post("/shutdown"), 401, "unauthorized")
    assert harness.shutdown_calls == 0


# --- lifecycle -----------------------------------------------------------------------------


def test_health_returns_version(harness: Harness) -> None:
    response = harness.client.get("/health", headers=harness.auth)
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": assistant_prof.__version__}


def test_shutdown_requests_server_stop(harness: Harness) -> None:
    response = harness.client.post("/shutdown", headers=harness.auth)
    assert response.status_code == 202
    assert response.json() == {"status": "shutting_down"}
    assert harness.shutdown_calls == 1


def test_default_shutdown_callback_is_harmless(token: str) -> None:
    client = TestClient(create_app(Settings(token=SecretStr(token))))
    assert client.post("/shutdown", headers={"X-Session-Token": token}).status_code == 202


# --- CORS ----------------------------------------------------------------------------------


def preflight(harness: Harness, origin: str) -> Any:
    return harness.client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-session-token",
        },
    )


@pytest.mark.parametrize("origin", [TAURI_ORIGIN, TAURI_HTTPS_ORIGIN])
def test_preflight_allowed_for_tauri_without_token(harness: Harness, origin: str) -> None:
    response = preflight(harness, origin)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "x-session-token" in response.headers["access-control-allow-headers"].lower()


@pytest.mark.parametrize("origin", ["http://evil.example", VITE_ORIGIN, "null"])
def test_preflight_refused_for_other_origins(harness: Harness, origin: str) -> None:
    response = preflight(harness, origin)
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_dev_origin_allowed_only_in_dev_mode(token: str) -> None:
    dev = Harness(token, dev=True)
    response = preflight(dev, VITE_ORIGIN)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == VITE_ORIGIN
    assert preflight(dev, TAURI_ORIGIN).status_code == 200


def test_cors_headers_on_success_and_error(harness: Harness) -> None:
    ok = harness.client.get("/health", headers={**harness.auth, "Origin": TAURI_ORIGIN})
    assert ok.headers["access-control-allow-origin"] == TAURI_ORIGIN
    assert "x-correlation-id" in ok.headers["access-control-expose-headers"].lower()
    denied = harness.client.get("/health", headers={"Origin": TAURI_ORIGIN})
    assert denied.status_code == 401
    assert denied.headers["access-control-allow-origin"] == TAURI_ORIGIN


def test_no_cors_headers_for_unknown_origin(harness: Harness) -> None:
    response = harness.client.get("/health", headers={**harness.auth, "Origin": "http://x.test"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


# --- problem details -----------------------------------------------------------------------


def test_unknown_route_is_a_404_problem(harness: Harness) -> None:
    assert_problem(harness.client.get("/nope", headers=harness.auth), 404, "not_found")


def test_wrong_method_is_a_405_problem(harness: Harness) -> None:
    response = harness.client.post("/health", headers=harness.auth)
    assert_problem(response, 405, "method_not_allowed")
    assert response.headers["allow"] == "GET"


def test_validation_error_hides_input_values(harness: Harness) -> None:
    @harness.app.get("/_test/items/{number}")
    async def item(number: int) -> int:
        return number

    response = harness.client.get("/_test/items/secret-text", headers=harness.auth)
    body = assert_problem(response, 422, "validation_error")
    assert body["errors"] == [{"loc": ["path", "number"], "type": "int_parsing"}]
    assert "secret-text" not in response.text


def test_other_http_errors_keep_their_status(harness: Harness) -> None:
    from fastapi import HTTPException

    @harness.app.get("/_test/teapot")
    async def teapot() -> None:
        raise HTTPException(status_code=418, headers={"X-Extra": "1"})

    response = harness.client.get("/_test/teapot", headers=harness.auth)
    assert_problem(response, 418, "http_error")
    assert response.headers["x-extra"] == "1"


def test_api_errors_are_rendered(harness: Harness) -> None:
    from assistant_prof.core.errors import NotFoundError

    @harness.app.get("/_test/doc")
    async def doc() -> None:
        raise NotFoundError("Document introuvable.")

    body = assert_problem(harness.client.get("/_test/doc", headers=harness.auth), 404, "not_found")
    assert body["detail"] == "Document introuvable."


def test_unexpected_error_is_a_500_without_details(harness: Harness) -> None:
    @harness.app.get("/_test/crash")
    async def crash() -> None:
        raise RuntimeError("internal secret detail")

    response = harness.client.get("/_test/crash", headers={**harness.auth, "Origin": TAURI_ORIGIN})
    assert_problem(response, 500, "internal_error")
    assert "internal secret detail" not in response.text
    assert response.headers["access-control-allow-origin"] == TAURI_ORIGIN


def test_error_after_response_started_is_reraised(harness: Harness) -> None:
    def chunks() -> Iterator[bytes]:
        yield b"partial"
        raise RuntimeError("mid-stream")

    @harness.app.get("/_test/stream")
    async def stream() -> StreamingResponse:
        return StreamingResponse(chunks())

    with pytest.raises(RuntimeError, match="mid-stream"):
        harness.client.get("/_test/stream", headers=harness.auth)


# --- correlation ID ------------------------------------------------------------------------


def test_correlation_id_generated(harness: Harness) -> None:
    first = harness.client.get("/health", headers=harness.auth).headers["x-correlation-id"]
    second = harness.client.get("/health", headers=harness.auth).headers["x-correlation-id"]
    assert len(first) == 32
    assert first != second


def test_valid_correlation_id_is_echoed(harness: Harness) -> None:
    headers = {**harness.auth, "X-Correlation-ID": "client-req-0001"}
    response = harness.client.get("/nope", headers=headers)
    assert response.headers["x-correlation-id"] == "client-req-0001"
    assert response.json()["correlation_id"] == "client-req-0001"


def test_invalid_correlation_id_is_replaced(harness: Harness) -> None:
    headers = {**harness.auth, "X-Correlation-ID": "bad id\r"}
    response = harness.client.get("/health", headers=headers)
    assert response.headers["x-correlation-id"] != "bad id\r"
    assert len(response.headers["x-correlation-id"]) == 32


# --- dev mode ------------------------------------------------------------------------------


def test_docs_only_in_dev_mode(harness: Harness, token: str) -> None:
    assert harness.client.get("/docs", headers=harness.auth).status_code == 404
    assert harness.client.get("/openapi.json", headers=harness.auth).status_code == 404
    dev = Harness(token, dev=True)
    assert dev.client.get("/docs", headers=dev.auth).status_code == 200
    schema = dev.client.get("/openapi.json", headers=dev.auth).json()
    assert "/health" in schema["paths"]

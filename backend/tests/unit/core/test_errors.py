import pytest

from assistant_prof.core.errors import (
    ApiError,
    AssistantProfError,
    ConfigError,
    ErrorCode,
    HttpError,
    InternalError,
    MethodNotAllowedError,
    NotFoundError,
    RequestValidationFailedError,
    UnauthorizedError,
)

API_ERRORS: list[type[ApiError]] = [
    UnauthorizedError,
    NotFoundError,
    MethodNotAllowedError,
    RequestValidationFailedError,
    InternalError,
]


def test_codes_are_unique_across_the_hierarchy() -> None:
    classes: list[type[AssistantProfError]] = [*API_ERRORS, HttpError, ConfigError]
    codes = [cls.code for cls in classes]
    assert len(codes) == len(set(codes))
    assert set(codes) == set(ErrorCode)


@pytest.mark.parametrize("cls", API_ERRORS)
def test_api_errors_have_status_and_french_text(cls: type[ApiError]) -> None:
    error = cls()
    assert 400 <= error.status < 600
    assert error.title.strip()
    assert error.detail == cls.default_detail
    assert error.detail.endswith(".")
    assert isinstance(error, AssistantProfError)


def test_detail_can_be_overridden() -> None:
    assert NotFoundError("Document introuvable.").detail == "Document introuvable."


def test_http_error_status_is_per_instance() -> None:
    assert HttpError(413).status == 413
    assert HttpError.status == 400

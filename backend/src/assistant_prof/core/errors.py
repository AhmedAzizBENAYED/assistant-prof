"""Typed error hierarchy with stable codes.

API errors carry a French ``title`` and ``detail`` (shown to the teacher) and are rendered as
RFC 9457 problem details by ``api.problems``. Startup errors carry an English message: they are
read by the desktop shell, which shows its own French screen.
"""

from enum import StrEnum
from typing import ClassVar


class ErrorCode(StrEnum):
    """Stable machine-readable codes; never rename a member once released."""

    CONFIG_INVALID = "config_invalid"
    UNAUTHORIZED = "unauthorized"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    VALIDATION_ERROR = "validation_error"
    HTTP_ERROR = "http_error"
    INTERNAL_ERROR = "internal_error"


class AssistantProfError(Exception):
    """Root of every error raised on purpose by the backend."""

    code: ClassVar[ErrorCode]


class ConfigError(AssistantProfError):
    """Invalid startup configuration (arguments, environment). The message is English."""

    code = ErrorCode.CONFIG_INVALID


class ApiError(AssistantProfError):
    """Error returned to the frontend as problem details, with a French title and detail."""

    status: int  # class default; HttpError overrides it per instance
    title: ClassVar[str]
    default_detail: ClassVar[str]

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail if detail is not None else self.default_detail
        super().__init__(self.detail)


class UnauthorizedError(ApiError):
    """Missing or wrong session token."""

    code = ErrorCode.UNAUTHORIZED
    status = 401
    title = "Accès refusé"
    default_detail = "Jeton de session manquant ou invalide."


class NotFoundError(ApiError):
    """Unknown route or resource."""

    code = ErrorCode.NOT_FOUND
    status = 404
    title = "Ressource introuvable"
    default_detail = "La ressource demandée n'existe pas."


class MethodNotAllowedError(ApiError):
    """Known route, wrong HTTP method."""

    code = ErrorCode.METHOD_NOT_ALLOWED
    status = 405
    title = "Méthode non autorisée"
    default_detail = "Cette opération n'est pas permise sur cette ressource."


class RequestValidationFailedError(ApiError):
    """Request body, path or query does not match the schema."""

    code = ErrorCode.VALIDATION_ERROR
    status = 422
    title = "Requête invalide"
    default_detail = "La requête contient des données invalides."


class HttpError(ApiError):
    """Any other HTTP error raised by the framework; the status is set per instance."""

    code = ErrorCode.HTTP_ERROR
    status = 400
    title = "Requête refusée"
    default_detail = "La requête n'a pas pu être traitée."

    def __init__(self, status: int, detail: str | None = None) -> None:
        super().__init__(detail)
        self.status = status


class InternalError(ApiError):
    """Unexpected failure; the real cause is logged, never returned."""

    code = ErrorCode.INTERNAL_ERROR
    status = 500
    title = "Erreur interne"
    default_detail = "Une erreur inattendue s'est produite. Réessayez ou exportez le diagnostic."

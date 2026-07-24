import logging
import traceback
from collections.abc import Mapping, Sequence

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

try:
    from content.services.exceptions import (
        DomainValidationError as ContentDomainValidationError,
        DomainNotFoundError as ContentNotFoundError,
        InvalidOperation as ContentInvalidOperation,
    )
except ImportError:  # pragma: no cover - optional app
    ContentDomainValidationError = ContentNotFoundError = ContentInvalidOperation = None

try:
    from school.services.exceptions import (
        DomainValidationError as SchoolDomainValidationError,
        NotFoundError as SchoolNotFoundError,
        InvalidOperation as SchoolInvalidOperation,
        PermissionDenied as SchoolPermissionDenied,
        DuplicateError as SchoolDuplicateError,
    )
except ImportError:  # pragma: no cover
    SchoolDomainValidationError = SchoolNotFoundError = SchoolInvalidOperation = None
    SchoolPermissionDenied = SchoolDuplicateError = None

try:
    from activities.services.exceptions import (
        ValidationError as ActivitiesValidationError,
        NotFoundError as ActivitiesNotFoundError,
        PermissionDenied as ActivitiesPermissionDenied,
    )
except ImportError:  # pragma: no cover
    ActivitiesValidationError = ActivitiesNotFoundError = ActivitiesPermissionDenied = None

try:
    from custom_account.services.exceptions import (
        DomainError as AccountDomainError,
        UserNotFoundError,
        IncorrectPasswordError,
    )
except ImportError:  # pragma: no cover
    AccountDomainError = UserNotFoundError = IncorrectPasswordError = None

try:
    from ai_personalization.exceptions import (
        PersonalizationError,
        InsufficientDataError,
        ModelNotTrainedError,
        PrerequisiteNotMetError,
    )
except ImportError:  # pragma: no cover
    PersonalizationError = InsufficientDataError = ModelNotTrainedError = None
    PrerequisiteNotMetError = None

logger = logging.getLogger(__name__)


def _as_tuple(*items):
    """Filter None for isinstance checks."""
    return tuple(item for item in items if item is not None)


def _extract_message(payload):
    if isinstance(payload, str):
        return payload
    if isinstance(payload, Mapping):
        for key in ("message", "detail", "error", "non_field_errors"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and value:
                return _extract_message(value[0])
        for value in payload.values():
            if isinstance(value, str) and value:
                return value
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and value:
                return _extract_message(value[0])
        return ""
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        return _extract_message(payload[0]) if payload else ""
    return str(payload)


def _normalize_error_payload(data, status_code, default_code="error"):
    # Already formatted payload → ensure status present then return
    if isinstance(data, Mapping) and "message" in data and ("error" in data or "code" in data or "detail" in data):
        normalized = dict(data)
        normalized.setdefault("status", status_code)
        if "error" not in normalized and default_code:
            normalized["error"] = default_code
        return normalized

    message = _extract_message(data)
    if not message:
        message = "Yêu cầu không hợp lệ" if status_code < 500 else "Đã xảy ra lỗi hệ thống"

    payload = {
        "error": default_code or "error",
        "message": message,
        "status": status_code,
    }

    if isinstance(data, Mapping):
        payload["errors"] = dict(data)
        payload["detail"] = data.get("detail", message)
    elif isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
        payload["errors"] = list(data)
        payload["detail"] = message
    else:
        payload["detail"] = str(data)

    return payload


def _build_error_response(detail, status_code, error_code):
    detail_payload = {"detail": detail} if not isinstance(detail, (Mapping, Sequence)) or isinstance(detail, (str, bytes)) else detail
    normalized = _normalize_error_payload(detail_payload, status_code, error_code)
    return Response(normalized, status=status_code)


def custom_exception_handler(exc, context):
    """
    Global exception handler:
    - Chuyển 500 thành lỗi có cấu trúc.
    - Log chi tiết server-side, trả JSON nhẹ cho client.
    """
    # Gọi handler mặc định trước (bắt các lỗi DRF như ValidationError)
    response = exception_handler(exc, context)

    if response is not None:
        default_code = "validation_error" if response.status_code == status.HTTP_400_BAD_REQUEST else "error"
        response.data = _normalize_error_payload(response.data, response.status_code, default_code)
        return response

    # -------------------------------
    # Domain/service level exceptions
    # -------------------------------
    validation_errors = _as_tuple(
        ContentDomainValidationError,
        SchoolDomainValidationError,
        ActivitiesValidationError,
        AccountDomainError,
        IncorrectPasswordError,
        DjangoValidationError,
    )

    not_found_errors = _as_tuple(
        ContentNotFoundError,
        SchoolNotFoundError,
        ActivitiesNotFoundError,
        UserNotFoundError,
    )

    permission_errors = _as_tuple(
        SchoolPermissionDenied,
        ActivitiesPermissionDenied,
    )

    invalid_operation_errors = _as_tuple(
        ContentInvalidOperation,
        SchoolInvalidOperation,
    )

    duplicate_errors = _as_tuple(SchoolDuplicateError,)

    personalization_errors = _as_tuple(
        PersonalizationError,
        InsufficientDataError,
        ModelNotTrainedError,
        PrerequisiteNotMetError,
    )

    if validation_errors and isinstance(exc, validation_errors):
        if isinstance(exc, DjangoValidationError):
            detail = getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or str(exc)
        else:
            detail = str(exc)
        return _build_error_response(detail, status.HTTP_400_BAD_REQUEST, "validation_error")

    if not_found_errors and isinstance(exc, not_found_errors):
        return _build_error_response(str(exc) or "Not found.", status.HTTP_404_NOT_FOUND, "not_found")

    if permission_errors and isinstance(exc, permission_errors):
        return _build_error_response(str(exc) or "Permission denied.", status.HTTP_403_FORBIDDEN, "permission_denied")

    if invalid_operation_errors and isinstance(exc, invalid_operation_errors):
        return _build_error_response(str(exc) or "Invalid operation.", status.HTTP_400_BAD_REQUEST, "invalid_operation")

    if duplicate_errors and isinstance(exc, duplicate_errors):
        return _build_error_response(str(exc) or "Duplicate detected.", status.HTTP_409_CONFLICT, "duplicate_error")

    if personalization_errors and isinstance(exc, personalization_errors):
        return _build_error_response(str(exc) or "Personalization error.", status.HTTP_400_BAD_REQUEST, "personalization_error")

    # Xử lý lỗi không bắt được (500)
    view = context.get('view', None)
    view_name = view.__class__.__name__ if view else 'unknown view'

    # Log chi tiết vào file server (chỉ dev mới thấy)
    logger.error(
        f"[{view_name}] Unhandled exception: {exc}\n{traceback.format_exc()}"
    )

    # Trả về JSON nhẹ cho FE
    return Response(
        {
            "error": "Internal Server Error",
            "detail": str(exc) if settings.DEBUG else "An unexpected error occurred.",
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )

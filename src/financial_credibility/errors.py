"""User-facing error helpers."""

from __future__ import annotations

from typing import Any


class UserFacingError(Exception):
    """Exception with a stable code, message, and optional recovery hint."""

    def __init__(self, code: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint

    def to_dict(self) -> dict[str, Any]:
        payload = {"code": self.code, "message": self.message}
        if self.hint:
            payload["hint"] = self.hint
        return payload


def error_payload(exc: Exception) -> dict[str, Any]:
    """Convert an exception into an API-friendly error payload."""
    if isinstance(exc, UserFacingError):
        return {"error": exc.to_dict()}
    return {
        "error": {
            "code": "unexpected_error",
            "message": str(exc) or exc.__class__.__name__,
            "hint": "Inspect the audit trace or run the command with a smaller deterministic input.",
        }
    }

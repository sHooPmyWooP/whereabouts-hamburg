from typing import Any

from fastapi import HTTPException


class ApiHTTPException(HTTPException):
    """HTTP failure carrying a stable code for localized clients."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        detail: Any,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code

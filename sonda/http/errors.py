from typing import Any

from fastapi.responses import JSONResponse


class HttpError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        retry_after: int | None = None,
        current: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retry_after = retry_after
        self.current = current


def error_response(error: HttpError) -> JSONResponse:
    payload: dict[str, Any] = {"code": error.code, "message": error.message}
    if error.current is not None:
        payload["current"] = error.current
    headers = {"Retry-After": str(error.retry_after)} if error.retry_after is not None else None
    return JSONResponse({"error": payload}, status_code=error.status_code, headers=headers)

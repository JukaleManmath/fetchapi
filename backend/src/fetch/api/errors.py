"""Global error handlers and stable error response shape.

All error responses use:
{
    "error": {
        "code": "UPPER_SNAKE_CASE",
        "message": "Human-readable message.",
        "details": {},
        "request_id": "uuid-or-null",
        "retryable": false
    }
}

Internal details (tracebacks, SQL, file paths, provider responses) are
never exposed. Redact at this boundary.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from fetch.domain.errors import (
    FetchError,
    IngestionError,
    SourceNotFoundError,
    OperationNotFoundError,
    SchemaNotFoundError,
)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(IngestionError)
    async def ingestion_error_handler(
        request: Request, exc: IngestionError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "INGESTION_ERROR",
                    "message": str(exc),
                    "details": {},
                    "request_id": None,
                    "retryable": True,
                }
            },
        )

    @app.exception_handler(SourceNotFoundError)
    async def source_not_found_handler(
        request: Request, exc: SourceNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "SOURCE_NOT_FOUND",
                    "message": str(exc),
                    "details": {},
                    "request_id": None,
                    "retryable": False,
                }
            },
        )

    @app.exception_handler(OperationNotFoundError)
    async def operation_not_found_handler(
        request: Request, exc: OperationNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": "OPERATION_NOT_FOUND",
                    "message": str(exc),
                    "details": {},
                    "request_id": None,
                    "retryable": False,
                }
            },
        )

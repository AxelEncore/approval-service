"""FastAPI application factory + request-logging middleware."""
from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import approval_requests, health
from app.core.config import settings
from app.core.context import request_id_var, user_id_var, workspace_id_var
from app.core.logging import log_event, setup_logging

setup_logging(settings.log_level)
logger = logging.getLogger("app.request")


def create_app() -> FastAPI:
    app = FastAPI(
        title="approval-service",
        version="1.0.0",
        description="Content approval workflow service.",
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        token_rid = request_id_var.set(request_id)
        token_ws = workspace_id_var.set(request.headers.get("X-Workspace-Id"))
        token_uid = user_id_var.set(request.headers.get("X-User-Id"))

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            log_event(
                logger,
                "request.handled",
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            request_id_var.reset(token_rid)
            workspace_id_var.reset(token_ws)
            user_id_var.reset(token_uid)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={"detail": "Validation error", "errors": exc.errors()},
        )

    app.include_router(health.router)
    app.include_router(approval_requests.router)
    return app


app = create_app()

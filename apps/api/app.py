"""FastAPI application for the V2 snapshot.

Routes live in :mod:`apps.api.routers`. This module only constructs the app,
applies CORS, and maps domain errors onto HTTP responses.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from .core import content, security, settings
from .db import mongo
from .db.snapshot import Missing
from .routers import alerts, auth, health, workspace

app = FastAPI(title=content.API_TITLE, version=content.API_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins(),
    allow_methods=settings.CORS_METHODS,
    allow_headers=settings.CORS_HEADERS,
    expose_headers=settings.CORS_EXPOSE_HEADERS,
)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(alerts.router)
app.include_router(workspace.router)

logger = logging.getLogger(__name__)


def _service_unavailable(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": detail},
    )


@app.exception_handler(Missing)
async def snapshot_missing(_request: Request, _exc: Missing) -> JSONResponse:
    return _service_unavailable(content.ERRORS["no_snapshot"])


@app.exception_handler(mongo.NotConfigured)
@app.exception_handler(security.NotConfigured)
@app.exception_handler(PyMongoError)
async def account_store_unavailable(_request: Request, exc: Exception) -> JSONResponse:
    logger.warning("Account store unavailable (%s)", type(exc).__name__)
    return _service_unavailable(content.ERRORS["auth_store_unavailable"])

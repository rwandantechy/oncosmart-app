"""Service status. Open to every caller so the public site can tell if the API is up."""

from __future__ import annotations

from fastapi import APIRouter

from ..core import content
from ..db import snapshot
from ..services.ai_providers import provider_status

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health() -> dict:
    return {
        "status": content.STATUS_OK,
        "snapshot_available": snapshot.exists(),
        **provider_status(),
    }

"""Public medicine-alert search. No session: patients must be able to read notices."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..core import content
from ..schemas.alerts import Alert, AlertFilters
from ..services import alerts
from ..services.grounded_ai import explain_alert_record

router = APIRouter(tags=["alerts"])


@router.get("/api/alerts")
def list_alerts(filters: Annotated[AlertFilters, Depends(AlertFilters.as_query)]) -> dict:
    return alerts.search(filters)


@router.get("/api/alerts/{record_id}", response_model=Alert)
def alert_detail(record_id: str) -> Alert:
    record = alerts.get(record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=content.ERRORS["alert_not_found"],
        )
    return Alert(**record)


@router.post("/api/alerts/{record_id}/explain")
def explain_alert(record_id: str) -> dict:
    record = alerts.get(record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=content.ERRORS["alert_not_found"],
        )
    return explain_alert_record(record)

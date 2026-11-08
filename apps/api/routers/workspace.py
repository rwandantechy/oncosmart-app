"""Research workspace reads. Every route here requires a verified access token."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from ..core import content, settings
from ..dependencies import WORKSPACE
from ..schemas.research import ResearchQuestion
from ..services import alerts, insights, research

router = APIRouter(tags=["workspace"], dependencies=WORKSPACE)


@router.get("/api/dataset")
def dataset() -> dict:
    found = insights.dataset()
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=content.ERRORS["no_active_snapshot"],
        )
    return found


@router.get("/api/insights/summary")
def insights_summary() -> dict:
    return insights.summary()


@router.get("/api/insights/sources")
def insight_sources() -> list[dict]:
    return insights.sources()


@router.get("/api/insights/timeline")
def insight_timeline() -> dict:
    return insights.timeline()


@router.get("/api/insights/completeness")
def insight_completeness() -> list[dict]:
    return insights.completeness()


@router.get("/api/insights/research")
def insight_research() -> dict:
    return insights.research_brief()


@router.get("/api/insights/report.csv")
def download_report() -> StreamingResponse:
    return StreamingResponse(
        iter([alerts.report_csv()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={settings.REPORT_FILENAME}"},
    )


@router.post("/api/research/ask")
def ask_research_question(payload: ResearchQuestion) -> dict:
    return research.answer(payload.question.strip())

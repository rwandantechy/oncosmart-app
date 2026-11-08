"""Shapes for published regulator notices and the queries that filter them."""

from __future__ import annotations

from typing import Optional

from fastapi import Query
from pydantic import BaseModel, ConfigDict

from ..core import settings


class Alert(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    record_id: str
    source_id: str
    source_org: str
    source_url: str
    product_name: Optional[str] = None
    source_country: Optional[str] = None
    manufacturer: Optional[str] = None
    distributor: Optional[str] = None
    publish_date: Optional[str] = None
    scraped_at: str
    reason: Optional[str] = None
    more_info: Optional[str] = None


class AlertPage(BaseModel):
    items: list[Alert]
    total: int
    page: int
    page_size: int


class AlertFilters(BaseModel):
    """Search parameters, bounded so no single request can scan unbounded text."""

    q: Optional[str] = None
    country: Optional[str] = None
    regulator: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    page: int = 1
    page_size: int = settings.PAGE_SIZE_DEFAULT

    @classmethod
    def as_query(
        cls,
        q: Optional[str] = Query(default=None, max_length=settings.SEARCH_MAX_LENGTH),
        country: Optional[str] = Query(default=None, max_length=settings.COUNTRY_MAX_LENGTH),
        regulator: Optional[str] = Query(
            default=None, max_length=settings.REGULATOR_MAX_LENGTH
        ),
        from_date: Optional[str] = Query(
            default=None, alias="from", max_length=settings.DATE_MAX_LENGTH
        ),
        to_date: Optional[str] = Query(
            default=None, alias="to", max_length=settings.DATE_MAX_LENGTH
        ),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(
            default=settings.PAGE_SIZE_DEFAULT, ge=1, le=settings.PAGE_SIZE_MAX
        ),
    ) -> "AlertFilters":
        return cls(
            q=q,
            country=country,
            regulator=regulator,
            from_date=from_date,
            to_date=to_date,
            page=page,
            page_size=page_size,
        )

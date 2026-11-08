"""Shapes for the grounded research assistant."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..core import settings


class ResearchQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=settings.QUESTION_MAX_LENGTH)

"""Persisted analytics REST; explicit UTC window with half-open boundaries."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime

from app.api.deps import get_analytics_service
from app.application.analytics_service import AnalyticsService
from app.schemas.analytics import Dashboard, TrackPage

router = APIRouter(prefix="/analytics", tags=["analytics"])
Service = Annotated[AnalyticsService, Depends(get_analytics_service)]


@router.get("", response_model=Dashboard)
async def dashboard(
    service: Service,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
    camera_id: UUID | None = None,
) -> Dashboard:
    return await service.dashboard(start, end, camera_id)


@router.get("/tracks", response_model=TrackPage)
async def tracks(
    service: Service,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
    camera_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> TrackPage:
    return await service.tracks(start, end, camera_id, limit, cursor)

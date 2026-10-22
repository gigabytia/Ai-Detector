"""Aggregates /api/v1 routers. Future auth dependency is attached here once."""

from fastapi import APIRouter, status

from app.api.errors import ErrorResponse
from app.api.v1 import (
    analytics,
    cameras,
    events,
    internal,
    lines,
    snapshots,
    system,
    uploads,
    zones,
)

api_v1_router = APIRouter(
    prefix="/api/v1",
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
api_v1_router.include_router(analytics.router)
api_v1_router.include_router(events.router)
api_v1_router.include_router(snapshots.router)
api_v1_router.include_router(system.router)
api_v1_router.include_router(cameras.router)
api_v1_router.include_router(uploads.router)
api_v1_router.include_router(internal.router)

api_v1_router.include_router(zones.router)

api_v1_router.include_router(lines.router)

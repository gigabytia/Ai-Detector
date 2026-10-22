"""Event history/status REST and live SSE. Static /stream precedes /{event_id}."""

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import AwareDatetime

from app.api.deps import Resources, get_event_service
from app.api.errors import ErrorResponse
from app.application.event_service import EventService
from app.application.event_service import decode_cursor as decode_cursor
from app.schemas.events import EventPage, EventRead, EventStatus, EventType, EventUpdate

router = APIRouter(
    prefix="/events",
    tags=["events"],
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
Service = Annotated[EventService, Depends(get_event_service)]


@router.get("", response_model=EventPage)
async def list_events(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    camera_id: UUID | None = None,
    status: EventStatus | None = None,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    event_type: EventType | None = None,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
) -> EventPage:
    return await service.list(
        limit, camera_id, status, cursor, event_type=event_type, start=start, end=end
    )


@router.get(
    "/stream",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}},
    },
)
async def stream(request: Request, resources: Resources) -> StreamingResponse:
    hub = resources.live
    assert hub is not None

    async def packets() -> AsyncIterator[str]:
        queue = hub.subscribe()
        try:
            kind = "resync" if hub.available else "unavailable"
            yield f"retry: 1500\nevent: {kind}\ndata: {{}}\n\n"
            while not await request.is_disconnected():
                try:
                    packet = await asyncio.wait_for(queue.get(), timeout=10)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if packet is None:
                    yield "event: resync\ndata: {}\n\n"
                    return
                yield packet
        finally:
            hub.unsubscribe(queue)

    return StreamingResponse(
        packets(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/export",
    response_class=Response,
    responses={200: {"content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}}}},
)
async def export_events(
    service: Service,
    camera_id: UUID | None = None,
    status: EventStatus | None = None,
    event_type: EventType | None = None,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
) -> Response:
    content = await service.export(camera_id, status, event_type, start, end)
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="events.csv"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/{event_id}", response_model=EventRead)
async def get_event(event_id: UUID, service: Service) -> EventRead:
    return await service.get(event_id)


@router.patch("/{event_id}", response_model=EventRead)
async def update_event(event_id: UUID, body: EventUpdate, service: Service) -> EventRead:
    return await service.update(event_id, body)

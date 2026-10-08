"""FastAPI dependencies that hand out services built in the lifespan."""

from fastapi import Request

from app.application.system_service import SystemService
from app.core.lifecycle import AppResources


def get_resources(request: Request) -> AppResources:
    resources: AppResources = request.app.state.resources
    return resources


def get_system_service(request: Request) -> SystemService:
    return get_resources(request).system_service

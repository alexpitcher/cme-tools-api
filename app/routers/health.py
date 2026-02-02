"""Health-check endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app import __version__
from app.auth import require_api_key
from app.models.responses import HealthResponse, RouterHealthResponse
from app.services.ssh_manager import ssh_manager
from app.utils.ios_parser import parse_ephone_summary, parse_telephony_service

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def service_health() -> HealthResponse:
    """Basic liveness probe (no auth required)."""
    return HealthResponse(status="ok", version=__version__)


@router.get(
    "/router/health",
    response_model=RouterHealthResponse,
    dependencies=[Depends(require_api_key)],
)
async def router_health() -> RouterHealthResponse:
    """Check router reachability and CME status."""
    try:
        ts_result = await ssh_manager.send_show("show telephony-service")
        ts_data = parse_telephony_service(ts_result.output)

        ep_result = await ssh_manager.send_show("show ephone summary")
        phones = parse_ephone_summary(ep_result.output)

        return RouterHealthResponse(
            reachable=True,
            telephony_service=ts_data,
            registered_phones=phones,
        )
    except Exception as exc:
        return RouterHealthResponse(
            reachable=False,
            error=str(exc),
        )

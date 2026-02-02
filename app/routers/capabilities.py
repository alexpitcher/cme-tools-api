"""Router capabilities detection endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_api_key
from app.models.responses import CapabilitiesResponse
from app.services.capabilities import detect_capabilities

router = APIRouter(tags=["capabilities"], dependencies=[Depends(require_api_key)])


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities() -> CapabilitiesResponse:
    """Detect IOS features relevant to rollback and restore."""
    return await detect_capabilities()

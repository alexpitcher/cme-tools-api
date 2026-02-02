"""CME-specific read and write endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import require_api_key
from app.models.cme import (
    ConfigSectionResponse,
    EphoneDetailResponse,
    EphoneDnSummaryResponse,
    EphoneSummaryResponse,
    IntentName,
    SpeedDialDeleteRequest,
    SpeedDialSetRequest,
    TelephonyServiceResponse,
    TelephonyUrlDeleteRequest,
    TelephonyUrlSetRequest,
)
from app.models.plan import ConfigPlan
from app.services.intent_service import resolve_intent
from app.services.ssh_manager import ssh_manager
from app.utils.ios_parser import (
    parse_config_ephone,
    parse_config_ephone_dn,
    parse_ephone_detail,
    parse_ephone_dn_summary,
    parse_ephone_summary,
    parse_telephony_service,
)

router = APIRouter(
    prefix="/cme",
    tags=["cme"],
    dependencies=[Depends(require_api_key)],
)


# ---------------------------------------------------------------------------
# READ endpoints
# ---------------------------------------------------------------------------


@router.get("/ephones", response_model=EphoneSummaryResponse)
async def list_ephones() -> EphoneSummaryResponse:
    """List all ephones with parsed summary data."""
    result = await ssh_manager.send_show("show ephone summary")
    phones = parse_ephone_summary(result.output)
    return EphoneSummaryResponse(ephones=phones, raw=result.output)


@router.get("/ephone/{ephone_id}", response_model=EphoneDetailResponse)
async def get_ephone(ephone_id: int) -> EphoneDetailResponse:
    """Get detailed information about a single ephone."""
    result = await ssh_manager.send_show(f"show ephone {ephone_id}")
    if result.failed:
        raise HTTPException(status_code=502, detail="Router command failed")
    parsed = parse_ephone_detail(result.output)
    return EphoneDetailResponse(ephone_id=ephone_id, raw=result.output, **parsed)


@router.get("/ephone-dns", response_model=EphoneDnSummaryResponse)
async def list_ephone_dns() -> EphoneDnSummaryResponse:
    """List all ephone-dns with summary data."""
    result = await ssh_manager.send_show("show ephone-dn summary")
    dns = parse_ephone_dn_summary(result.output)
    return EphoneDnSummaryResponse(dns=dns, raw=result.output)


@router.get("/telephony-service", response_model=TelephonyServiceResponse)
async def get_telephony_service() -> TelephonyServiceResponse:
    """Get parsed telephony-service configuration."""
    result = await ssh_manager.send_show("show telephony-service")
    data = parse_telephony_service(result.output)
    return TelephonyServiceResponse(data=data, raw=result.output)


@router.get("/config/section", response_model=ConfigSectionResponse)
async def get_config_section(
    anchor: str = Query(..., description="Config section anchor keyword"),
) -> ConfigSectionResponse:
    """Get a running-config section by anchor keyword."""
    cmd = f"show running-config | section {anchor}"
    result = await ssh_manager.send_show(cmd)
    return ConfigSectionResponse(anchor=anchor, config=result.output)


@router.get("/config/ephone/{ephone_id}", response_model=ConfigSectionResponse)
async def get_ephone_config(ephone_id: int) -> ConfigSectionResponse:
    """Get the running-config section for a specific ephone."""
    cmd = f"show running-config | section ^ephone {ephone_id}$"
    result = await ssh_manager.send_show(cmd)
    parsed = parse_config_ephone(result.output) if result.output.strip() else None
    return ConfigSectionResponse(
        anchor=f"ephone {ephone_id}",
        config=result.output,
        parsed=parsed,
    )


@router.get("/config/ephone-dn/{dn_id}", response_model=ConfigSectionResponse)
async def get_ephone_dn_config(dn_id: int) -> ConfigSectionResponse:
    """Get the running-config section for a specific ephone-dn."""
    cmd = f"show running-config | section ^ephone-dn {dn_id}$"
    result = await ssh_manager.send_show(cmd)
    parsed = parse_config_ephone_dn(result.output) if result.output.strip() else None
    return ConfigSectionResponse(
        anchor=f"ephone-dn {dn_id}",
        config=result.output,
        parsed=parsed,
    )


# ---------------------------------------------------------------------------
# WRITE endpoints (plan generation — these do NOT apply changes)
# ---------------------------------------------------------------------------


@router.post("/speed-dial", response_model=ConfigPlan)
async def set_speed_dial(req: SpeedDialSetRequest) -> ConfigPlan:
    """Generate a plan to set a speed-dial on an ephone."""
    return resolve_intent(IntentName.set_speed_dial, req.model_dump())


@router.delete("/speed-dial", response_model=ConfigPlan)
async def delete_speed_dial(req: SpeedDialDeleteRequest) -> ConfigPlan:
    """Generate a plan to remove a speed-dial from an ephone."""
    return resolve_intent(IntentName.delete_speed_dial, req.model_dump())


@router.post("/telephony/url", response_model=ConfigPlan)
async def set_telephony_url(req: TelephonyUrlSetRequest) -> ConfigPlan:
    """Generate a plan to set a telephony-service URL."""
    intent_map = {
        "services": IntentName.set_url_services,
        "directories": IntentName.set_url_directories,
        "idle": IntentName.set_url_idle,
    }
    return resolve_intent(intent_map[req.url_type.value], req.model_dump())


@router.delete("/telephony/url", response_model=ConfigPlan)
async def delete_telephony_url(req: TelephonyUrlDeleteRequest) -> ConfigPlan:
    """Generate a plan to clear a telephony-service URL."""
    intent_map = {
        "services": IntentName.clear_url_services,
        "directories": IntentName.clear_url_directories,
        "idle": IntentName.clear_url_idle,
    }
    return resolve_intent(intent_map[req.url_type.value], req.model_dump())

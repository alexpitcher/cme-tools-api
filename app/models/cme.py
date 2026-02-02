"""CME-specific request and response models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# READ response models
# ---------------------------------------------------------------------------


class EphoneSummaryItem(BaseModel):
    """Single ephone from show ephone summary."""

    ephone_id: int
    mac: str = ""
    status: str = ""
    ip: Optional[str] = None
    type: str = ""
    primary_dn: Optional[int] = None


class EphoneSummaryResponse(BaseModel):
    ephones: list[EphoneSummaryItem]
    raw: str = ""


class SpeedDialEntry(BaseModel):
    position: int
    number: str
    label: str = ""


class ButtonMapping(BaseModel):
    button_number: int
    dn: int
    ring_type: str = ""


class EphoneDetailResponse(BaseModel):
    ephone_id: int
    mac: str = ""
    type: str = ""
    status: str = ""
    ip: Optional[str] = None
    buttons: list[ButtonMapping] = []
    speed_dials: list[SpeedDialEntry] = []
    raw: str = ""


class EphoneDnSummaryItem(BaseModel):
    dn_id: int
    number: str = ""
    name: str = ""
    state: str = ""
    ephone_id: Optional[int] = None


class EphoneDnSummaryResponse(BaseModel):
    dns: list[EphoneDnSummaryItem]
    raw: str = ""


class TelephonyServiceResponse(BaseModel):
    data: dict[str, Any]
    raw: str = ""


class ConfigSectionResponse(BaseModel):
    anchor: str
    config: str
    parsed: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# WRITE request models
# ---------------------------------------------------------------------------


class SpeedDialSetRequest(BaseModel):
    ephone_id: int
    position: int = Field(ge=1, le=99)
    label: str
    number: str


class SpeedDialDeleteRequest(BaseModel):
    ephone_id: int
    position: int = Field(ge=1, le=99)


class UrlType(str, Enum):
    services = "services"
    directories = "directories"
    idle = "idle"


class TelephonyUrlSetRequest(BaseModel):
    url_type: UrlType
    url: str
    idle_timeout: Optional[int] = None


class TelephonyUrlDeleteRequest(BaseModel):
    url_type: UrlType


# ---------------------------------------------------------------------------
# Intent system models
# ---------------------------------------------------------------------------


class IntentName(str, Enum):
    set_speed_dial = "set_speed_dial"
    delete_speed_dial = "delete_speed_dial"
    set_url_services = "set_url_services"
    set_url_directories = "set_url_directories"
    set_url_idle = "set_url_idle"
    clear_url_services = "clear_url_services"
    clear_url_directories = "clear_url_directories"
    clear_url_idle = "clear_url_idle"


class IntentRequest(BaseModel):
    intent: IntentName
    params: dict[str, Any] = {}

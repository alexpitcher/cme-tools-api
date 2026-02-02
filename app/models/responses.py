"""Common API response models."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str


class RouterHealthResponse(BaseModel):
    reachable: bool
    telephony_service: Optional[dict[str, Any]] = None
    registered_phones: Optional[list[dict[str, Any]]] = None
    error: Optional[str] = None


class ShowCommandRequest(BaseModel):
    command: str


class ShowCommandResponse(BaseModel):
    command: str
    output: str
    success: bool
    error: Optional[str] = None


class BackupRequest(BaseModel):
    reason: str = "manual"


class BackupResponse(BaseModel):
    success: bool
    filename: Optional[str] = None
    commit_sha: Optional[str] = None
    error: Optional[str] = None


class RestoreRequest(BaseModel):
    """Restore from a git ref (commit SHA, tag, or filename)."""

    ref: str
    filename: Optional[str] = None
    method: Optional[str] = None  # "configure_replace" or "line_by_line"


class RestoreResponse(BaseModel):
    success: bool
    method_used: str = ""
    warnings: list[str] = []
    verification_output: str = ""
    error: Optional[str] = None


class CapabilitiesResponse(BaseModel):
    configure_replace_available: bool = False
    archive_available: bool = False
    ios_version: str = ""
    hostname: str = ""
    model: str = ""
    detected_features: dict[str, bool] = {}


class ErrorResponse(BaseModel):
    detail: str

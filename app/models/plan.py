"""Plan and validation models for the PLAN -> VALIDATE -> APPLY workflow."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ConfigPlan(BaseModel):
    """A structured configuration change plan."""

    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    description: str
    mode_path: list[str] = Field(
        description=(
            "CLI mode-enter commands in order, e.g. "
            '["configure terminal", "telephony-service"]'
        ),
    )
    commands: list[str] = Field(description="Config commands to run inside the mode")
    verification: list[str] = Field(
        default_factory=list,
        description="Post-apply show commands to verify success",
    )
    affected_entities: list[str] = Field(
        default_factory=list,
        description='E.g. ["ephone 5", "ephone-dn 201"]',
    )
    risk_level: RiskLevel = RiskLevel.low
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    validated: bool = False
    validation_result: Optional[dict] = None


class PlanCreateRequest(BaseModel):
    """Request body for POST /config/plan."""

    description: str
    mode_path: list[str]
    commands: list[str]
    verification: list[str] = Field(default_factory=list)
    affected_entities: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.low


class CommandValidationStatus(str, Enum):
    ok = "ok"
    error = "error"
    warning = "warning"
    needs_approval = "needs_approval"


class CommandValidation(BaseModel):
    """Validation result for a single command."""

    command: str
    status: CommandValidationStatus
    message: str = ""
    raw_output: str = ""
    suggestion: Optional[str] = None


class ValidationResult(BaseModel):
    """Result of validating a full plan."""

    plan_id: str
    ok: bool
    command_results: list[CommandValidation]
    raw_router_output: str = ""


class CommandExecution(BaseModel):
    """Result of executing a single command."""

    command: str
    output: str
    success: bool


class ApplyResult(BaseModel):
    """Result of applying a plan."""

    plan_id: str
    success: bool
    executed_commands: list[CommandExecution]
    pre_backup_sha: Optional[str] = None
    post_backup_sha: Optional[str] = None
    verification_results: list[CommandExecution] = Field(default_factory=list)
    rollback_attempted: bool = False
    rollback_success: Optional[bool] = None
    rollback_details: str = ""

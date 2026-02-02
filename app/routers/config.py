"""PLAN / VALIDATE / APPLY endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_api_key
from app.models.cme import IntentRequest
from app.models.plan import (
    ApplyResult,
    ConfigPlan,
    PlanCreateRequest,
    ValidationResult,
)
from app.services import plan_service
from app.services.apply import apply_plan
from app.services.intent_service import resolve_intent
from app.services.validate import validate_plan

router = APIRouter(
    prefix="/config",
    tags=["config"],
    dependencies=[Depends(require_api_key)],
)


# ── Plan ──────────────────────────────────────────────────────────────────


@router.post("/plan", response_model=ConfigPlan)
async def create_plan(req: PlanCreateRequest | dict) -> ConfigPlan:
    """Create a new configuration change plan.

    Accepts either a standard PlanCreateRequest body or an intent payload::

        {"intent": "set_speed_dial", "params": {"ephone_id": 1, ...}}
    """
    if isinstance(req, dict) and "intent" in req:
        intent_req = IntentRequest(**req)
        return resolve_intent(intent_req.intent, intent_req.params)
    if isinstance(req, dict):
        req = PlanCreateRequest(**req)
    plan = plan_service.create_plan(req)
    return plan


@router.get("/plan/{plan_id}", response_model=ConfigPlan)
async def get_plan(plan_id: str) -> ConfigPlan:
    plan = plan_service.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.get("/plans", response_model=list[ConfigPlan])
async def list_plans() -> list[ConfigPlan]:
    return plan_service.list_plans()


# ── Validate ──────────────────────────────────────────────────────────────


class ValidateRequest(ConfigPlan):
    """Accept a full plan or just a plan_id."""
    pass


@router.post("/validate", response_model=ValidationResult)
async def validate(req: PlanCreateRequest | dict) -> ValidationResult:
    """Validate a plan's commands for IOS correctness.

    Accepts either:
    - A full plan body (creates a new plan automatically).
    - ``{"plan_id": "<existing>"}`` to validate an already-created plan.
    """
    if isinstance(req, dict) and "plan_id" in req:
        plan = plan_service.get_plan(req["plan_id"])
        if plan is None:
            raise HTTPException(status_code=404, detail="Plan not found")
    else:
        if isinstance(req, dict):
            req = PlanCreateRequest(**req)
        plan = plan_service.create_plan(req)

    result = await validate_plan(plan, probe_router=True)
    return result


# ── Apply ─────────────────────────────────────────────────────────────────


class ApplyRequest(ConfigPlan):
    pass


@router.post("/apply", response_model=ApplyResult)
async def apply(req: PlanCreateRequest | dict) -> ApplyResult:
    """Apply a validated plan (backup -> apply -> verify -> backup).

    Accepts a full plan body or ``{"plan_id": "<existing>"}``.
    """
    if isinstance(req, dict) and "plan_id" in req:
        plan = plan_service.get_plan(req["plan_id"])
        if plan is None:
            raise HTTPException(status_code=404, detail="Plan not found")
    else:
        if isinstance(req, dict):
            req = PlanCreateRequest(**req)
        plan = plan_service.create_plan(req)

    result = await apply_plan(plan)
    return result

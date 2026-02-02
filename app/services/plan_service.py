"""In-memory plan store and creation helpers."""

from __future__ import annotations

from app.models.plan import ConfigPlan, PlanCreateRequest
from app.services.command_filter import check_plan_commands
from app.utils.logging import get_logger

log = get_logger(__name__)

# In-memory store keyed by plan_id
_plans: dict[str, ConfigPlan] = {}


def create_plan(req: PlanCreateRequest) -> ConfigPlan:
    """Create a new plan and store it."""
    plan = ConfigPlan(
        description=req.description,
        mode_path=req.mode_path,
        commands=req.commands,
        verification=req.verification,
        affected_entities=req.affected_entities,
        risk_level=req.risk_level,
    )
    _plans[plan.plan_id] = plan
    log.info("plan.created", plan_id=plan.plan_id, cmds=len(plan.commands))
    return plan


def get_plan(plan_id: str) -> ConfigPlan | None:
    return _plans.get(plan_id)


def update_plan(plan: ConfigPlan) -> None:
    _plans[plan.plan_id] = plan


def list_plans() -> list[ConfigPlan]:
    return list(_plans.values())


def delete_plan(plan_id: str) -> bool:
    return _plans.pop(plan_id, None) is not None


def validate_plan_allowlist(plan: ConfigPlan) -> list[tuple[str, bool, str]]:
    """Check every command in the plan against the allowlist.

    Returns list of (command, allowed, reason).
    """
    results = check_plan_commands(plan.mode_path, plan.commands)
    return [(cmd, r.allowed, r.reason) for cmd, r in results]

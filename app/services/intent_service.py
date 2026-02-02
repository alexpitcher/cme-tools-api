"""Intent-to-plan mapping service.

Converts structured intents into ConfigPlan objects ready for
the VALIDATE -> APPLY workflow.
"""

from __future__ import annotations

from typing import Any, Callable

from app.models.cme import IntentName
from app.models.plan import ConfigPlan, PlanCreateRequest, RiskLevel
from app.services import plan_service


def resolve_intent(intent: IntentName, params: dict[str, Any]) -> ConfigPlan:
    """Convert an intent + params into a stored ConfigPlan."""
    builder = _INTENT_BUILDERS.get(intent)
    if builder is None:
        raise ValueError(f"Unknown intent: {intent}")
    req = builder(params)
    return plan_service.create_plan(req)


# ---------------------------------------------------------------------------
# Speed-dial builders
# ---------------------------------------------------------------------------


def _build_set_speed_dial(p: dict[str, Any]) -> PlanCreateRequest:
    eid = int(p["ephone_id"])
    pos = int(p["position"])
    number = str(p["number"])
    label = str(p.get("label", ""))
    cmd = f"speed-dial {pos} {number}"
    if label:
        cmd += f" label {label}"
    return PlanCreateRequest(
        description=f"Set speed-dial {pos} on ephone {eid}",
        mode_path=["configure terminal", f"ephone {eid}"],
        commands=[cmd],
        verification=[f"show ephone {eid}"],
        affected_entities=[f"ephone {eid}"],
        risk_level=RiskLevel.low,
    )


def _build_delete_speed_dial(p: dict[str, Any]) -> PlanCreateRequest:
    eid = int(p["ephone_id"])
    pos = int(p["position"])
    return PlanCreateRequest(
        description=f"Remove speed-dial {pos} from ephone {eid}",
        mode_path=["configure terminal", f"ephone {eid}"],
        commands=[f"no speed-dial {pos}"],
        verification=[f"show ephone {eid}"],
        affected_entities=[f"ephone {eid}"],
        risk_level=RiskLevel.low,
    )


# ---------------------------------------------------------------------------
# Telephony URL builders
# ---------------------------------------------------------------------------


def _build_set_url(url_type: str, p: dict[str, Any]) -> PlanCreateRequest:
    url = str(p["url"])
    commands = [f"url {url_type} {url}"]
    if url_type == "idle" and p.get("idle_timeout"):
        commands.append(f"url idle time {int(p['idle_timeout'])}")
    return PlanCreateRequest(
        description=f"Set telephony-service url {url_type}",
        mode_path=["configure terminal", "telephony-service"],
        commands=commands,
        verification=["show telephony-service"],
        affected_entities=["telephony-service"],
        risk_level=RiskLevel.low,
    )


def _build_clear_url(url_type: str, _p: dict[str, Any]) -> PlanCreateRequest:
    return PlanCreateRequest(
        description=f"Clear telephony-service url {url_type}",
        mode_path=["configure terminal", "telephony-service"],
        commands=[f"no url {url_type}"],
        verification=["show telephony-service"],
        affected_entities=["telephony-service"],
        risk_level=RiskLevel.low,
    )


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_INTENT_BUILDERS: dict[IntentName, Callable[[dict[str, Any]], PlanCreateRequest]] = {
    IntentName.set_speed_dial: _build_set_speed_dial,
    IntentName.delete_speed_dial: _build_delete_speed_dial,
    IntentName.set_url_services: lambda p: _build_set_url("services", p),
    IntentName.set_url_directories: lambda p: _build_set_url("directories", p),
    IntentName.set_url_idle: lambda p: _build_set_url("idle", p),
    IntentName.clear_url_services: lambda p: _build_clear_url("services", p),
    IntentName.clear_url_directories: lambda p: _build_clear_url("directories", p),
    IntentName.clear_url_idle: lambda p: _build_clear_url("idle", p),
}

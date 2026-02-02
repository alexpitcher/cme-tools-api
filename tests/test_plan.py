"""Tests for plan creation and schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.plan import ConfigPlan, PlanCreateRequest, RiskLevel
from app.services.plan_service import create_plan, delete_plan, get_plan


class TestPlanModel:
    def test_create_plan_defaults(self):
        plan = ConfigPlan(
            description="test",
            mode_path=["configure terminal"],
            commands=["telephony-service"],
        )
        assert plan.plan_id
        assert plan.risk_level == RiskLevel.low
        assert plan.validated is False
        assert plan.verification == []

    def test_plan_id_is_uuid(self):
        plan = ConfigPlan(
            description="test",
            mode_path=["configure terminal"],
            commands=["max-ephones 10"],
        )
        import uuid

        uuid.UUID(plan.plan_id)  # Should not raise

    def test_plan_with_all_fields(self):
        plan = ConfigPlan(
            description="Add phone",
            mode_path=["configure terminal", "ephone 5"],
            commands=["mac-address 1111.2222.3333", "type 7945", "button 1:5"],
            verification=["show ephone 5"],
            affected_entities=["ephone 5"],
            risk_level=RiskLevel.medium,
        )
        assert plan.risk_level == RiskLevel.medium
        assert len(plan.commands) == 3
        assert "ephone 5" in plan.affected_entities

    def test_invalid_risk_level_rejected(self):
        with pytest.raises(ValidationError):
            ConfigPlan(
                description="bad",
                mode_path=[],
                commands=[],
                risk_level="critical",  # type: ignore
            )


class TestPlanCreateRequest:
    def test_minimal_request(self):
        req = PlanCreateRequest(
            description="test",
            mode_path=["configure terminal"],
            commands=["telephony-service"],
        )
        assert req.verification == []
        assert req.risk_level == RiskLevel.low


class TestPlanService:
    def test_create_and_get(self):
        req = PlanCreateRequest(
            description="svc test",
            mode_path=["configure terminal"],
            commands=["telephony-service"],
        )
        plan = create_plan(req)
        assert get_plan(plan.plan_id) is not None

    def test_delete_plan(self):
        req = PlanCreateRequest(
            description="delete me",
            mode_path=["configure terminal"],
            commands=["telephony-service"],
        )
        plan = create_plan(req)
        assert delete_plan(plan.plan_id)
        assert get_plan(plan.plan_id) is None

    def test_get_nonexistent_returns_none(self):
        assert get_plan("nonexistent-id") is None

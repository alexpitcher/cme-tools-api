"""Integration tests exercising the full API with mock SSH transport."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_router_health(client):
    resp = await client.get("/router/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reachable"] is True
    assert data["telephony_service"] is not None


@pytest.mark.asyncio
async def test_show_command(client):
    resp = await client.post("/show", json={"command": "show version"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "15.7" in data["output"]


@pytest.mark.asyncio
async def test_show_command_denied(client):
    resp = await client.post("/show", json={"command": "reload"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_plan(client):
    resp = await client.post(
        "/config/plan",
        json={
            "description": "Test plan",
            "mode_path": ["configure terminal", "telephony-service"],
            "commands": ["max-ephones 48"],
            "verification": ["show telephony-service"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan_id"]
    assert data["description"] == "Test plan"


@pytest.mark.asyncio
async def test_get_plan(client):
    # Create first
    resp = await client.post(
        "/config/plan",
        json={
            "description": "Retrieve test",
            "mode_path": ["configure terminal"],
            "commands": ["telephony-service"],
        },
    )
    plan_id = resp.json()["plan_id"]

    # Retrieve
    resp = await client.get(f"/config/plan/{plan_id}")
    assert resp.status_code == 200
    assert resp.json()["plan_id"] == plan_id


@pytest.mark.asyncio
async def test_get_plan_not_found(client):
    resp = await client.get("/config/plan/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_validate_plan(client):
    resp = await client.post(
        "/config/validate",
        json={
            "description": "Validate test",
            "mode_path": ["configure terminal", "telephony-service"],
            "commands": ["max-ephones 48"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert len(data["command_results"]) == 1
    assert data["command_results"][0]["status"] in ("ok", "needs_approval")


@pytest.mark.asyncio
async def test_validate_blocked_command(client):
    resp = await client.post(
        "/config/validate",
        json={
            "description": "Should block",
            "mode_path": ["configure terminal"],
            "commands": ["reload"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["command_results"][0]["status"] == "error"


@pytest.mark.asyncio
async def test_apply_plan(client):
    resp = await client.post(
        "/config/apply",
        json={
            "description": "Apply test",
            "mode_path": ["configure terminal", "telephony-service"],
            "commands": ["max-ephones 48"],
            "verification": ["show telephony-service"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan_id"]
    assert isinstance(data["executed_commands"], list)
    assert data["pre_backup_sha"] is not None


@pytest.mark.asyncio
async def test_backup_endpoint(client):
    resp = await client.post("/backup", json={"reason": "api-test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["filename"] is not None
    assert data["commit_sha"] is not None


@pytest.mark.asyncio
async def test_list_plans(client):
    # Create a plan
    await client.post(
        "/config/plan",
        json={
            "description": "List test",
            "mode_path": ["configure terminal"],
            "commands": ["telephony-service"],
        },
    )
    resp = await client.get("/config/plans")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

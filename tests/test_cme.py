"""Tests for CME-specific parsers, intent service, and API endpoints."""

from __future__ import annotations

import pytest

from app.models.cme import IntentName
from app.services.intent_service import resolve_intent
from app.utils.ios_parser import (
    _extract_ephone_block,
    extract_ephone_config_section,
    extract_ephone_dn_config_section,
    parse_config_ephone,
    parse_config_ephone_dn,
    parse_ephone_detail,
    parse_ephone_dn_summary,
)
from tests.mock_ssh import (
    SHOW_EPHONE_DETAIL,
    SHOW_EPHONE_DN_SUMMARY,
    SHOW_RUN_SECTION_EPHONE,
    SHOW_RUN_SECTION_EPHONE_DN,
)


# ---------------------------------------------------------------------------
# Parser: parse_ephone_detail  (from "show ephone" block)
# ---------------------------------------------------------------------------


class TestParseEphoneDetail:
    """Parse a single ephone block extracted from 'show ephone' output."""

    def _block(self) -> str:
        return _extract_ephone_block(SHOW_EPHONE_DETAIL, 1)

    def test_block_extraction(self):
        block = self._block()
        assert "ephone-1" in block
        assert "ephone-2" not in block

    def test_mac_parsed(self):
        result = parse_ephone_detail(self._block())
        assert result["mac"] == "000D.2932.22A0"

    def test_type_parsed(self):
        result = parse_ephone_detail(self._block())
        assert result["type"] == "7960"

    def test_status_parsed(self):
        result = parse_ephone_detail(self._block())
        assert result["status"] == "registered"

    def test_ip_parsed(self):
        result = parse_ephone_detail(self._block())
        assert result["ip"] == "10.20.102.20"

    def test_buttons_parsed(self):
        result = parse_ephone_detail(self._block())
        assert len(result["buttons"]) == 1
        assert result["buttons"][0]["dn"] == 1
        assert result["buttons"][0]["number"] == "4002"

    def test_speed_dials_parsed(self):
        result = parse_ephone_detail(self._block())
        assert len(result["speed_dials"]) == 2
        assert result["speed_dials"][0]["position"] == 2
        assert result["speed_dials"][0]["number"] == "4001"
        assert result["speed_dials"][0]["label"] == "Zoe Bedroom"

    def test_empty_input(self):
        assert parse_ephone_detail("") == {}

    def test_extract_nonexistent(self):
        assert _extract_ephone_block(SHOW_EPHONE_DETAIL, 99) == ""


# ---------------------------------------------------------------------------
# Parser: parse_ephone_dn_summary
# ---------------------------------------------------------------------------


class TestParseEphoneDnSummary:
    def test_tabular_format(self):
        dns = parse_ephone_dn_summary(SHOW_EPHONE_DN_SUMMARY)
        assert len(dns) == 3
        assert dns[0]["dn_id"] == 1
        assert dns[0]["number"] == "1001"
        assert dns[0]["state"] == "IDLE"
        assert dns[0]["ephone_id"] == 1

    def test_config_fallback(self):
        """When tabular format isn't available, parse from config sections."""
        dns = parse_ephone_dn_summary(SHOW_RUN_SECTION_EPHONE_DN)
        assert len(dns) == 2
        assert dns[0]["dn_id"] == 1
        assert dns[0]["number"] == "4002"
        assert dns[1]["number"] == "4001"

    def test_empty_input(self):
        assert parse_ephone_dn_summary("") == []


# ---------------------------------------------------------------------------
# Parser: parse_config_ephone (from extracted config section)
# ---------------------------------------------------------------------------


class TestParseConfigEphone:
    def _section(self) -> str:
        return extract_ephone_config_section(SHOW_RUN_SECTION_EPHONE, 1)

    def test_section_extraction(self):
        section = self._section()
        assert "ephone  1" in section
        assert "ephone  2" not in section

    def test_ephone_id(self):
        result = parse_config_ephone(self._section())
        assert result["ephone_id"] == 1

    def test_mac(self):
        result = parse_config_ephone(self._section())
        assert result["mac"] == "000D.2932.22A0"

    def test_type(self):
        result = parse_config_ephone(self._section())
        assert result["type"] == "7960"

    def test_buttons(self):
        result = parse_config_ephone(self._section())
        assert len(result["buttons"]) == 1
        assert result["buttons"][0]["button_number"] == 1
        assert result["buttons"][0]["dn"] == 1

    def test_speed_dials(self):
        result = parse_config_ephone(self._section())
        assert len(result["speed_dials"]) == 2
        assert result["speed_dials"][0]["number"] == "4001"
        assert result["speed_dials"][0]["label"] == "Zoe Bedroom"

    def test_empty_input(self):
        assert parse_config_ephone("") == {}


# ---------------------------------------------------------------------------
# Parser: parse_config_ephone_dn (from extracted config section)
# ---------------------------------------------------------------------------


class TestParseConfigEphoneDn:
    def _section(self) -> str:
        return extract_ephone_dn_config_section(SHOW_RUN_SECTION_EPHONE, 1)

    def test_section_extraction(self):
        section = self._section()
        assert "ephone-dn  1" in section
        assert "ephone-dn  2" not in section

    def test_dn_id(self):
        result = parse_config_ephone_dn(self._section())
        assert result["dn_id"] == 1

    def test_number(self):
        result = parse_config_ephone_dn(self._section())
        assert result["number"] == "4002"

    def test_label(self):
        result = parse_config_ephone_dn(self._section())
        assert result["label"] == "Rack Phone"

    def test_empty_input(self):
        assert parse_config_ephone_dn("") == {}


# ---------------------------------------------------------------------------
# Intent service
# ---------------------------------------------------------------------------


class TestSpeedDialIntents:
    def test_set_speed_dial(self):
        plan = resolve_intent(IntentName.set_speed_dial, {
            "ephone_id": 1, "position": 1,
            "label": "IT", "number": "5001",
        })
        assert plan.plan_id
        assert plan.mode_path == ["configure terminal", "ephone 1"]
        assert "speed-dial 1 5001 label IT" in plan.commands
        assert "show ephone 1" in plan.verification
        assert "ephone 1" in plan.affected_entities

    def test_set_speed_dial_no_label(self):
        plan = resolve_intent(IntentName.set_speed_dial, {
            "ephone_id": 3, "position": 2, "number": "5555",
        })
        assert "speed-dial 2 5555" in plan.commands[0]
        assert "label" not in plan.commands[0]

    def test_delete_speed_dial(self):
        plan = resolve_intent(IntentName.delete_speed_dial, {
            "ephone_id": 1, "position": 1,
        })
        assert "no speed-dial 1" in plan.commands


class TestUrlIntents:
    def test_set_url_services(self):
        plan = resolve_intent(IntentName.set_url_services, {
            "url": "http://10.0.0.1/services",
        })
        assert plan.mode_path == ["configure terminal", "telephony-service"]
        assert "url services http://10.0.0.1/services" in plan.commands
        assert "telephony-service" in plan.affected_entities

    def test_set_url_directories(self):
        plan = resolve_intent(IntentName.set_url_directories, {
            "url": "http://10.0.0.1/dirs",
        })
        assert "url directories http://10.0.0.1/dirs" in plan.commands

    def test_set_url_idle_with_timeout(self):
        plan = resolve_intent(IntentName.set_url_idle, {
            "url": "http://10.0.0.1/idle",
            "idle_timeout": 60,
        })
        assert "url idle http://10.0.0.1/idle" in plan.commands
        assert "url idle time 60" in plan.commands

    def test_clear_url_services(self):
        plan = resolve_intent(IntentName.clear_url_services, {})
        assert "no url services" in plan.commands

    def test_clear_url_directories(self):
        plan = resolve_intent(IntentName.clear_url_directories, {})
        assert "no url directories" in plan.commands


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_ephones(client):
    resp = await client.get("/cme/ephones")
    assert resp.status_code == 200
    data = resp.json()
    assert "ephones" in data
    assert len(data["ephones"]) == 3
    assert data["ephones"][0]["mac"] == "000D.2932.22A0"


@pytest.mark.asyncio
async def test_get_ephone_detail(client):
    resp = await client.get("/cme/ephone/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ephone_id"] == 1
    assert data["mac"] == "000D.2932.22A0"
    assert len(data["speed_dials"]) == 2


@pytest.mark.asyncio
async def test_list_ephone_dns(client):
    resp = await client.get("/cme/ephone-dns")
    assert resp.status_code == 200
    data = resp.json()
    assert "dns" in data
    assert len(data["dns"]) == 3
    assert data["dns"][0]["number"] == "1001"


@pytest.mark.asyncio
async def test_get_telephony_service(client):
    resp = await client.get("/cme/telephony-service")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data
    assert data["data"].get("max_ephones") == 48


@pytest.mark.asyncio
async def test_get_config_section(client):
    resp = await client.get("/cme/config/section", params={"anchor": "telephony-service"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["anchor"] == "telephony-service"
    assert "max-ephones" in data["config"]


@pytest.mark.asyncio
async def test_get_ephone_config(client):
    resp = await client.get("/cme/config/ephone/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["anchor"] == "ephone 1"
    assert data["parsed"]["ephone_id"] == 1
    assert data["parsed"]["mac"] == "000D.2932.22A0"


@pytest.mark.asyncio
async def test_get_ephone_dn_config(client):
    resp = await client.get("/cme/config/ephone-dn/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["anchor"] == "ephone-dn 1"
    assert data["parsed"]["dn_id"] == 1
    assert data["parsed"]["number"] == "4002"


@pytest.mark.asyncio
async def test_set_speed_dial_api(client):
    resp = await client.post("/cme/speed-dial", json={
        "ephone_id": 1, "position": 3,
        "label": "Helpdesk", "number": "5555",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan_id"]
    assert "speed-dial 3 5555 label Helpdesk" in data["commands"]
    assert data["mode_path"] == ["configure terminal", "ephone 1"]


@pytest.mark.asyncio
async def test_delete_speed_dial_api(client):
    resp = await client.request("DELETE", "/cme/speed-dial", json={
        "ephone_id": 1, "position": 1,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "no speed-dial 1" in data["commands"]


@pytest.mark.asyncio
async def test_set_telephony_url_api(client):
    resp = await client.post("/cme/telephony/url", json={
        "url_type": "services",
        "url": "http://10.0.0.1/services",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "url services http://10.0.0.1/services" in data["commands"]
    assert data["mode_path"] == ["configure terminal", "telephony-service"]


@pytest.mark.asyncio
async def test_delete_telephony_url_api(client):
    resp = await client.request("DELETE", "/cme/telephony/url", json={
        "url_type": "services",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "no url services" in data["commands"]


@pytest.mark.asyncio
async def test_intent_via_plan_endpoint(client):
    resp = await client.post("/config/plan", json={
        "intent": "set_speed_dial",
        "params": {
            "ephone_id": 2, "position": 1,
            "label": "Test", "number": "9999",
        },
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan_id"]
    assert "speed-dial 1 9999 label Test" in data["commands"]


@pytest.mark.asyncio
async def test_speed_dial_invalid_position(client):
    resp = await client.post("/cme/speed-dial", json={
        "ephone_id": 1, "position": 0,
        "label": "Bad", "number": "123",
    })
    assert resp.status_code == 422

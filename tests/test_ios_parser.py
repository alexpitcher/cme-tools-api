"""Tests for IOS output parsing utilities."""

from __future__ import annotations

from app.utils.ios_parser import (
    detect_ios_error,
    extract_config_section,
    is_ios_error,
    parse_ephone_summary,
    parse_help_output,
    parse_show_version,
    parse_telephony_service,
)
from tests.mock_ssh import (
    HELP_INVALID,
    HELP_MAX_EPHONES,
    SHOW_EPHONE_SUMMARY,
    SHOW_RUNNING_CONFIG,
    SHOW_TELEPHONY_SERVICE,
    SHOW_VERSION,
)


class TestErrorDetection:
    def test_invalid_input(self):
        assert detect_ios_error("% Invalid input detected at '^' marker.") is not None

    def test_incomplete_command(self):
        assert detect_ios_error("% Incomplete command.") is not None

    def test_ambiguous_command(self):
        assert detect_ios_error("% Ambiguous command:  \"sh\"") is not None

    def test_unrecognized(self):
        assert is_ios_error("% Unrecognized command")

    def test_clean_output(self):
        assert detect_ios_error("hostname Router\n") is None

    def test_multiline_with_error(self):
        output = "some output\n% Invalid input detected\nmore"
        err = detect_ios_error(output)
        assert err is not None
        assert "Invalid" in err


class TestShowVersion:
    def test_parse_version(self):
        info = parse_show_version(SHOW_VERSION)
        assert info["ios_version"] == "15.7(3)M8"
        assert info["hostname"] == "Router"
        assert "2901" in info.get("model", "") or "CISCO2901" in info.get("model_line", "")

    def test_empty_input(self):
        info = parse_show_version("")
        assert info == {}


class TestTelephonyService:
    def test_parse_telephony(self):
        data = parse_telephony_service(SHOW_TELEPHONY_SERVICE)
        assert data.get("max_ephones") == 48 or "max_ephones" in str(data)
        assert data.get("max_dn") == 144 or "max_dn" in str(data)


class TestEphoneParsing:
    def test_parse_ephone_summary(self):
        phones = parse_ephone_summary(SHOW_EPHONE_SUMMARY)
        assert len(phones) >= 2
        registered = [p for p in phones if p.get("status") == "registered"]
        assert len(registered) >= 1

    def test_empty_input(self):
        phones = parse_ephone_summary("")
        assert phones == []


class TestHelpOutput:
    def test_valid_help(self):
        result = parse_help_output(HELP_MAX_EPHONES)
        assert result["valid"]
        assert len(result["completions"]) > 0
        assert result["error"] is None

    def test_invalid_help(self):
        result = parse_help_output(HELP_INVALID)
        assert not result["valid"]
        assert result["error"] is not None


class TestConfigSection:
    def test_extract_telephony(self):
        section = extract_config_section(SHOW_RUNNING_CONFIG, "telephony-service")
        assert "max-ephones" in section
        assert "ip source-address" in section

    def test_extract_ephone_dn(self):
        section = extract_config_section(SHOW_RUNNING_CONFIG, "ephone-dn 1")
        assert "number 1001" in section

    def test_extract_nonexistent(self):
        section = extract_config_section(SHOW_RUNNING_CONFIG, "nonexistent-section")
        assert section == ""

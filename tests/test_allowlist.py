"""Tests for the command allowlist / denylist engine."""

from __future__ import annotations

import pytest

from app.services.command_filter import (
    check_config_command,
    check_exec_command,
    check_plan_commands,
)


# ── Exec-mode tests ──────────────────────────────────────────────────────

class TestExecAllowlist:
    def test_show_version_allowed(self):
        assert check_exec_command("show version").allowed

    def test_show_running_config_allowed(self):
        assert check_exec_command("show running-config").allowed

    def test_show_telephony_allowed(self):
        assert check_exec_command("show telephony-service").allowed

    def test_show_ephone_allowed(self):
        assert check_exec_command("show ephone").allowed

    def test_ping_allowed(self):
        assert check_exec_command("ping 10.0.0.1").allowed

    def test_terminal_length_allowed(self):
        assert check_exec_command("terminal length 0").allowed

    def test_reload_denied(self):
        r = check_exec_command("reload")
        assert not r.allowed
        assert "denied" in r.reason.lower() or "safety" in r.reason.lower()

    def test_erase_denied(self):
        assert not check_exec_command("erase startup-config").allowed

    def test_format_denied(self):
        assert not check_exec_command("format flash:").allowed

    def test_write_erase_denied(self):
        assert not check_exec_command("write erase").allowed

    def test_debug_all_denied(self):
        assert not check_exec_command("debug all").allowed

    def test_delete_denied(self):
        assert not check_exec_command("delete flash:somefile").allowed

    def test_empty_denied(self):
        assert not check_exec_command("").allowed

    def test_write_memory_allowed(self):
        assert check_exec_command("write memory").allowed

    def test_copy_run_start_allowed(self):
        assert check_exec_command("copy running-config startup-config").allowed


# ── Config-mode tests ────────────────────────────────────────────────────

class TestConfigAllowlist:
    def test_telephony_service_allowed(self):
        assert check_config_command("telephony-service").allowed

    def test_max_ephones_allowed(self):
        assert check_config_command("max-ephones 48").allowed

    def test_max_dn_allowed(self):
        assert check_config_command("max-dn 144").allowed

    def test_ephone_allowed(self):
        assert check_config_command("ephone 1").allowed

    def test_ephone_dn_allowed(self):
        assert check_config_command("ephone-dn 10").allowed

    def test_mac_address_allowed(self):
        assert check_config_command("mac-address 1234.5678.9abc").allowed

    def test_button_allowed(self):
        assert check_config_command("button 1:1").allowed

    def test_number_allowed(self):
        assert check_config_command("number 1001").allowed

    def test_dial_peer_allowed(self):
        assert check_config_command("dial-peer voice 100 voip").allowed

    def test_configure_terminal_allowed(self):
        assert check_config_command("configure terminal").allowed

    def test_voice_register_allowed(self):
        assert check_config_command("voice register global").allowed

    def test_shutdown_allowed(self):
        assert check_config_command("shutdown").allowed

    def test_no_shutdown_allowed(self):
        assert check_config_command("no shutdown").allowed

    # Denied in config mode
    def test_reload_denied_in_config(self):
        assert not check_config_command("reload").allowed

    def test_username_denied(self):
        assert not check_config_command("username admin privilege 15").allowed

    def test_enable_secret_denied(self):
        assert not check_config_command("enable secret 0 mypass").allowed

    def test_crypto_key_zeroize_denied(self):
        assert not check_config_command("crypto key zeroize rsa").allowed

    def test_snmp_community_denied(self):
        assert not check_config_command("snmp-server community public RO").allowed

    def test_interface_denied_in_default(self):
        # interface is not in CME allowlist (it IS in maintenance mode list)
        r = check_config_command("interface GigabitEthernet0/0")
        assert not r.allowed


# ── Plan-level checks ────────────────────────────────────────────────────

class TestPlanCommands:
    def test_all_cme_commands_pass(self):
        mode_path = ["configure terminal", "telephony-service"]
        commands = ["max-ephones 48", "max-dn 144"]
        results = check_plan_commands(mode_path, commands)
        assert all(r.allowed for _, r in results)

    def test_mixed_blocked_commands(self):
        mode_path = ["configure terminal"]
        commands = ["telephony-service", "reload"]
        results = check_plan_commands(mode_path, commands)
        allowed_cmds = [cmd for cmd, r in results if r.allowed]
        blocked_cmds = [cmd for cmd, r in results if not r.allowed]
        assert "reload" in blocked_cmds

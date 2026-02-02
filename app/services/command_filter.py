"""Command allowlist / denylist engine.

Default mode: only CME-related and read-only show commands are allowed.
Maintenance mode: widens scope but still blocks destructive commands.
"""

from __future__ import annotations

import re

from app.config import settings
from app.utils.logging import get_logger

log = get_logger(__name__)

# ── ALWAYS-DENIED patterns (blocked even in maintenance mode) ─────────────
DENY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*reload\b", re.I),
    re.compile(r"^\s*erase\b", re.I),
    re.compile(r"^\s*format\b", re.I),
    re.compile(r"^\s*write\s+erase\b", re.I),
    re.compile(r"^\s*delete\b", re.I),
    re.compile(r"^\s*squeeze\b", re.I),
    re.compile(r"^\s*crypto\s+key\s+zeroize\b", re.I),
    re.compile(r"^\s*no\s+enable\b", re.I),
    re.compile(r"^\s*debug\s+all\b", re.I),
    re.compile(r"^\s*no\s+service\s+password-encryption\b", re.I),
    re.compile(r"^\s*boot\s+system\b", re.I),
    re.compile(r"^\s*config-register\b", re.I),
    re.compile(r"^\s*enable\s+secret\b", re.I),
    re.compile(r"^\s*enable\s+password\b", re.I),
    re.compile(r"^\s*service\s+password-encryption\b", re.I),
    re.compile(r"^\s*snmp-server\s+community\b", re.I),
    re.compile(r"^\s*username\b", re.I),
    re.compile(r"^\s*copy\s+(?!running-config\s+)\S+\s+startup-config\b", re.I),
]

# ── EXEC-mode allow patterns ──────────────────────────────────────────────
EXEC_ALLOW_PATTERNS: list[re.Pattern[str]] = [
    # All show commands
    re.compile(r"^\s*show\b", re.I),
    # Ping / traceroute (diagnostics)
    re.compile(r"^\s*ping\b", re.I),
    re.compile(r"^\s*traceroute\b", re.I),
    # Terminal settings (harmless)
    re.compile(r"^\s*terminal\b", re.I),
    # Write memory (save config – allowed through API)
    re.compile(r"^\s*write\s+memory\b", re.I),
    re.compile(r"^\s*copy\s+running-config\s+startup-config\b", re.I),
]

# ── CONFIG-mode CME allow patterns ────────────────────────────────────────
CME_CONFIG_ALLOW_PATTERNS: list[re.Pattern[str]] = [
    # telephony-service and all sub-commands
    re.compile(r"^\s*(no\s+)?telephony-service\b", re.I),
    re.compile(r"^\s*(no\s+)?max-ephones\b", re.I),
    re.compile(r"^\s*(no\s+)?max-dn\b", re.I),
    re.compile(r"^\s*(no\s+)?ip\s+source-address\b", re.I),
    re.compile(r"^\s*(no\s+)?service\s+phone\b", re.I),
    re.compile(r"^\s*(no\s+)?auto\s+assign\b", re.I),
    re.compile(r"^\s*(no\s+)?auto-reg-ephone\b", re.I),
    re.compile(r"^\s*(no\s+)?create\s+cnf-files\b", re.I),
    re.compile(r"^\s*(no\s+)?reset\b", re.I),
    re.compile(r"^\s*(no\s+)?restart\b", re.I),
    re.compile(r"^\s*(no\s+)?system\s+message\b", re.I),
    re.compile(r"^\s*(no\s+)?url\b", re.I),
    re.compile(r"^\s*(no\s+)?time-zone\b", re.I),
    re.compile(r"^\s*(no\s+)?date-format\b", re.I),
    re.compile(r"^\s*(no\s+)?time-format\b", re.I),
    re.compile(r"^\s*(no\s+)?moh\b", re.I),
    re.compile(r"^\s*(no\s+)?multicast\s+moh\b", re.I),
    re.compile(r"^\s*(no\s+)?transfer-system\b", re.I),
    re.compile(r"^\s*(no\s+)?transfer-pattern\b", re.I),
    re.compile(r"^\s*(no\s+)?calling-number\s+initiator\b", re.I),
    re.compile(r"^\s*(no\s+)?keepalive\b", re.I),
    re.compile(r"^\s*(no\s+)?timeouts\b", re.I),
    re.compile(r"^\s*(no\s+)?directory\b", re.I),
    re.compile(r"^\s*(no\s+)?srst\b", re.I),
    re.compile(r"^\s*(no\s+)?load\b", re.I),
    re.compile(r"^\s*(no\s+)?cnf-file\b", re.I),
    re.compile(r"^\s*(no\s+)?network-locale\b", re.I),
    re.compile(r"^\s*(no\s+)?user-locale\b", re.I),
    re.compile(r"^\s*(no\s+)?web\s+admin\b", re.I),

    # ephone and all sub-commands
    re.compile(r"^\s*(no\s+)?ephone\s+\d", re.I),
    re.compile(r"^\s*(no\s+)?ephone-dn\s+\d", re.I),
    re.compile(r"^\s*(no\s+)?ephone-template\s+\d", re.I),
    re.compile(r"^\s*(no\s+)?ephone-hunt\b", re.I),
    re.compile(r"^\s*(no\s+)?mac-address\b", re.I),
    re.compile(r"^\s*(no\s+)?type\b", re.I),
    re.compile(r"^\s*(no\s+)?button\b", re.I),
    re.compile(r"^\s*(no\s+)?speed-dial\b", re.I),
    re.compile(r"^\s*(no\s+)?fastdial\b", re.I),
    re.compile(r"^\s*(no\s+)?paging-dn\b", re.I),
    re.compile(r"^\s*(no\s+)?pickup-group\b", re.I),
    re.compile(r"^\s*(no\s+)?after-hours\b", re.I),
    re.compile(r"^\s*(no\s+)?pin\b", re.I),
    re.compile(r"^\s*(no\s+)?description\b", re.I),
    re.compile(r"^\s*(no\s+)?codec\b", re.I),
    re.compile(r"^\s*(no\s+)?max-calls-per-button\b", re.I),
    re.compile(r"^\s*(no\s+)?busy-trigger-per-button\b", re.I),
    re.compile(r"^\s*(no\s+)?softkeys\b", re.I),
    re.compile(r"^\s*(no\s+)?corlist\b", re.I),

    # ephone-dn sub-commands
    re.compile(r"^\s*(no\s+)?number\b", re.I),
    re.compile(r"^\s*(no\s+)?name\b", re.I),
    re.compile(r"^\s*(no\s+)?label\b", re.I),
    re.compile(r"^\s*(no\s+)?preference\b", re.I),
    re.compile(r"^\s*(no\s+)?call-forward\b", re.I),
    re.compile(r"^\s*(no\s+)?huntstop\b", re.I),
    re.compile(r"^\s*(no\s+)?no-reg\b", re.I),
    re.compile(r"^\s*(no\s+)?translation-profile\b", re.I),
    re.compile(r"^\s*(no\s+)?hold-alert\b", re.I),
    re.compile(r"^\s*(no\s+)?caller-id\b", re.I),
    re.compile(r"^\s*(no\s+)?intercom\b", re.I),
    re.compile(r"^\s*(no\s+)?night-service\b", re.I),

    # voice register global / dn / pool
    re.compile(r"^\s*(no\s+)?voice\s+register\b", re.I),

    # dial-peer
    re.compile(r"^\s*(no\s+)?dial-peer\s+voice\b", re.I),
    re.compile(r"^\s*(no\s+)?destination-pattern\b", re.I),
    re.compile(r"^\s*(no\s+)?session\s+protocol\b", re.I),
    re.compile(r"^\s*(no\s+)?session\s+target\b", re.I),
    re.compile(r"^\s*(no\s+)?dtmf-relay\b", re.I),
    re.compile(r"^\s*(no\s+)?incoming\s+called-number\b", re.I),
    re.compile(r"^\s*(no\s+)?port\b", re.I),

    # voice translation
    re.compile(r"^\s*(no\s+)?voice\s+translation-rule\b", re.I),
    re.compile(r"^\s*(no\s+)?voice\s+translation-profile\b", re.I),
    re.compile(r"^\s*(no\s+)?translate\b", re.I),
    re.compile(r"^\s*(no\s+)?rule\b", re.I),

    # SIP-related
    re.compile(r"^\s*(no\s+)?voice\s+service\s+voip\b", re.I),
    re.compile(r"^\s*(no\s+)?sip\b", re.I),
    re.compile(r"^\s*(no\s+)?allow-connections\b", re.I),
    re.compile(r"^\s*(no\s+)?registrar\b", re.I),

    # Mode entry helpers (configure terminal handled by scrapli)
    re.compile(r"^\s*configure\s+terminal\b", re.I),
    re.compile(r"^\s*end\b", re.I),
    re.compile(r"^\s*exit\b", re.I),

    # Misc safe config commands
    re.compile(r"^\s*(no\s+)?shutdown\b", re.I),
    re.compile(r"^\s*(no\s+)?no-auto-attendant\b", re.I),
]

# ── MAINTENANCE-mode additional patterns ──────────────────────────────────
MAINTENANCE_EXTRA_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\s*(no\s+)?interface\b", re.I),
    re.compile(r"^\s*(no\s+)?ip\s+route\b", re.I),
    re.compile(r"^\s*(no\s+)?router\b", re.I),
    re.compile(r"^\s*(no\s+)?access-list\b", re.I),
    re.compile(r"^\s*(no\s+)?ip\s+access-list\b", re.I),
    re.compile(r"^\s*(no\s+)?ntp\b", re.I),
    re.compile(r"^\s*(no\s+)?logging\b", re.I),
    re.compile(r"^\s*(no\s+)?line\b", re.I),
    re.compile(r"^\s*(no\s+)?banner\b", re.I),
    re.compile(r"^\s*(no\s+)?ip\s+dhcp\b", re.I),
    re.compile(r"^\s*(no\s+)?crypto\s+(?!key\s+zeroize)", re.I),
    re.compile(r"^\s*(no\s+)?aaa\b", re.I),
    re.compile(r"^\s*(no\s+)?archive\b", re.I),
    re.compile(r"^\s*(no\s+)?debug\b", re.I),
    re.compile(r"^\s*(no\s+)?ip\s+address\b", re.I),
]


# ── Public API ────────────────────────────────────────────────────────────

class CommandFilterResult:
    __slots__ = ("allowed", "reason")

    def __init__(self, allowed: bool, reason: str):
        self.allowed = allowed
        self.reason = reason

    def __bool__(self) -> bool:
        return self.allowed


def check_exec_command(command: str) -> CommandFilterResult:
    """Check whether an exec-mode command is allowed."""
    cmd = command.strip()
    if not cmd:
        return CommandFilterResult(False, "empty command")

    for pat in DENY_PATTERNS:
        if pat.search(cmd):
            return CommandFilterResult(False, f"denied by safety rule: {pat.pattern}")

    for pat in EXEC_ALLOW_PATTERNS:
        if pat.search(cmd):
            return CommandFilterResult(True, "allowed exec command")

    if settings.cme_maintenance_mode:
        return CommandFilterResult(True, "maintenance mode: exec commands allowed")

    return CommandFilterResult(False, "command not in exec allowlist")


def check_config_command(command: str) -> CommandFilterResult:
    """Check whether a config-mode command is allowed."""
    cmd = command.strip()
    if not cmd:
        return CommandFilterResult(False, "empty command")

    for pat in DENY_PATTERNS:
        if pat.search(cmd):
            return CommandFilterResult(False, f"denied by safety rule: {pat.pattern}")

    for pat in CME_CONFIG_ALLOW_PATTERNS:
        if pat.search(cmd):
            return CommandFilterResult(True, "allowed CME config command")

    if settings.cme_maintenance_mode:
        for pat in MAINTENANCE_EXTRA_PATTERNS:
            if pat.search(cmd):
                return CommandFilterResult(
                    True, "allowed in maintenance mode",
                )

    return CommandFilterResult(False, "command not in config allowlist")


def check_plan_commands(
    mode_path: list[str], commands: list[str],
) -> list[tuple[str, CommandFilterResult]]:
    """Validate all commands in a plan against the filter."""
    results: list[tuple[str, CommandFilterResult]] = []
    for cmd in mode_path:
        results.append((cmd, check_config_command(cmd)))
    for cmd in commands:
        results.append((cmd, check_config_command(cmd)))
    return results

"""Plan validation service.

Validation has two layers:
1. Offline: allowlist + known-pattern checks (always runs).
2. Online: IOS ``?`` help probing on the actual router (optional / best-effort).
"""

from __future__ import annotations

import re

from app.models.plan import (
    CommandValidation,
    CommandValidationStatus,
    ConfigPlan,
    ValidationResult,
)
from app.services import plan_service
from app.services.command_filter import check_config_command
from app.services.ssh_manager import SSHSessionManager, ssh_manager
from app.utils.ios_parser import detect_ios_error, parse_help_output
from app.utils.logging import get_logger

log = get_logger(__name__)

# ── Known CME command patterns for offline syntax checking ────────────────

_KNOWN_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^telephony-service$", re.I),
    re.compile(r"^max-ephones\s+\d+$", re.I),
    re.compile(r"^max-dn\s+\d+$", re.I),
    re.compile(r"^ip\s+source-address\s+\S+\s+port\s+\d+", re.I),
    re.compile(r"^(no\s+)?create\s+cnf-files", re.I),
    re.compile(r"^ephone\s+\d+", re.I),
    re.compile(r"^ephone-dn\s+\d+", re.I),
    re.compile(r"^mac-address\s+[\da-fA-F.]+", re.I),
    re.compile(r"^type\s+\S+", re.I),
    re.compile(r"^button\s+.+", re.I),
    re.compile(r"^number\s+\S+", re.I),
    re.compile(r"^name\s+.+", re.I),
    re.compile(r"^label\s+.+", re.I),
    re.compile(r"^description\s+.+", re.I),
    re.compile(r"^codec\s+\S+", re.I),
    re.compile(r"^(no\s+)?shutdown$", re.I),
    re.compile(r"^preference\s+\d+", re.I),
    re.compile(r"^call-forward\s+.+", re.I),
    re.compile(r"^(no\s+)?huntstop$", re.I),
    re.compile(r"^dial-peer\s+voice\s+\d+\s+\S+", re.I),
    re.compile(r"^destination-pattern\s+\S+", re.I),
    re.compile(r"^session\s+target\s+.+", re.I),
    re.compile(r"^session\s+protocol\s+\S+", re.I),
    re.compile(r"^dtmf-relay\s+.+", re.I),
    re.compile(r"^voice\s+register\s+(global|dn|pool)\b", re.I),
    re.compile(r"^voice\s+translation-rule\s+\d+", re.I),
    re.compile(r"^voice\s+translation-profile\s+\S+", re.I),
    re.compile(r"^translate\s+.+", re.I),
    re.compile(r"^rule\s+\d+\s+.+", re.I),
    re.compile(r"^(no\s+)?(reset|restart)\b", re.I),
    re.compile(r"^configure\s+terminal$", re.I),
    re.compile(r"^end$", re.I),
    re.compile(r"^exit$", re.I),
    re.compile(r"^transfer-system\s+\S+", re.I),
    re.compile(r"^transfer-pattern\s+\S+", re.I),
    re.compile(r"^(no\s+)?auto\s+assign\b", re.I),
    re.compile(r"^(no\s+)?keepalive\s+\d+", re.I),
    re.compile(r"^(no\s+)?moh\s+.+", re.I),
    re.compile(r"^(no\s+)?multicast\s+moh\b", re.I),
    re.compile(r"^speed-dial\s+.+", re.I),
    re.compile(r"^pickup-group\s+\d+", re.I),
    re.compile(r"^paging-dn\s+\d+", re.I),
    re.compile(r"^(no\s+)?softkeys\s+.+", re.I),
    re.compile(r"^(no\s+)?corlist\s+.+", re.I),
    re.compile(r"^after-hours\s+.+", re.I),
    re.compile(r"^pin\s+\d+", re.I),
    re.compile(r"^(no\s+)?night-service\b", re.I),
    re.compile(r"^(no\s+)?caller-id\s+.+", re.I),
    re.compile(r"^(no\s+)?intercom\s+.+", re.I),
]


def _matches_known_pattern(cmd: str) -> bool:
    for pat in _KNOWN_PATTERNS:
        if pat.match(cmd.strip()):
            return True
    return False


# ── public API ────────────────────────────────────────────────────────────

async def validate_plan(
    plan: ConfigPlan,
    *,
    probe_router: bool = True,
    mgr: SSHSessionManager | None = None,
) -> ValidationResult:
    """Validate all commands in a plan.

    Steps:
    1. Allowlist check.
    2. Known-pattern check.
    3. (Optional) IOS ``?`` help probe on the router.
    """
    _mgr = mgr or ssh_manager
    cmd_results: list[CommandValidation] = []
    all_ok = True
    raw_parts: list[str] = []

    # Determine the mode prompt context for help probing
    mode_entries = [
        c for c in plan.mode_path if c.lower() != "configure terminal"
    ]

    for cmd in plan.commands:
        # 1. Allowlist
        filt = check_config_command(cmd)
        if not filt.allowed:
            cmd_results.append(
                CommandValidation(
                    command=cmd,
                    status=CommandValidationStatus.error,
                    message=f"Blocked by allowlist: {filt.reason}",
                ),
            )
            all_ok = False
            continue

        # 2. Known pattern
        pattern_ok = _matches_known_pattern(cmd)

        # 3. Router probe (best-effort)
        router_ok: bool | None = None
        raw_output = ""
        suggestion = None

        if probe_router:
            try:
                # Build the probe string: enter mode commands first, then "cmd ?"
                # We need to be in the right mode for the probe to be meaningful.
                # Strategy: enter config + sub-modes, probe, then Ctrl-Z out.
                probe_text = f"{cmd} ?"
                raw_output = await _mgr.probe_help(probe_text)
                raw_parts.append(raw_output)
                parsed = parse_help_output(raw_output)
                if parsed["error"]:
                    router_ok = False
                    suggestion = parsed["error"]
                elif parsed["completions"]:
                    router_ok = True
                else:
                    # Empty completions might mean the command is complete (<cr>)
                    if "<cr>" in raw_output.lower():
                        router_ok = True
            except Exception as exc:
                log.warning("validate.probe_failed", cmd=cmd, error=str(exc))
                raw_parts.append(f"[probe error: {exc}]")

        # Determine final status
        if router_ok is False:
            status = CommandValidationStatus.error
            msg = suggestion or "Router rejected command"
            all_ok = False
        elif router_ok is True:
            status = CommandValidationStatus.ok
            msg = "Validated by router probe"
        elif pattern_ok:
            status = CommandValidationStatus.ok
            msg = "Matches known CME pattern"
        else:
            status = CommandValidationStatus.needs_approval
            msg = "Could not auto-validate; manual approval required"
            all_ok = False

        cmd_results.append(
            CommandValidation(
                command=cmd,
                status=status,
                message=msg,
                raw_output=raw_output,
                suggestion=suggestion,
            ),
        )

    result = ValidationResult(
        plan_id=plan.plan_id,
        ok=all_ok,
        command_results=cmd_results,
        raw_router_output="\n---\n".join(raw_parts),
    )

    # Store on plan
    plan.validated = all_ok
    plan.validation_result = result.model_dump()
    plan_service.update_plan(plan)

    log.info("validate.done", plan_id=plan.plan_id, ok=all_ok)
    return result

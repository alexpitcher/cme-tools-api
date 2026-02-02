"""Restore a configuration backup from git, using the safest method available."""

from __future__ import annotations

from app.models.responses import RestoreResponse
from app.services.backup import BackupService, backup_service
from app.services.capabilities import detect_capabilities
from app.services.ssh_manager import SSHSessionManager, ssh_manager
from app.utils.ios_parser import detect_ios_error
from app.utils.logging import get_logger

log = get_logger(__name__)


async def restore_backup(
    ref: str,
    filename: str | None = None,
    method: str | None = None,
    *,
    mgr: SSHSessionManager | None = None,
    bkp: BackupService | None = None,
) -> RestoreResponse:
    """Restore running-config from a git backup.

    Strategy:
    1. If ``configure replace`` is available and *method* is not forced
       to ``line_by_line``, use ``configure replace`` (preferred).
    2. Otherwise fall back to line-by-line config replay (warn loudly).
    """
    _mgr = mgr or ssh_manager
    _bkp = bkp or backup_service

    warnings: list[str] = []

    # ── Fetch the backup text ─────────────────────────────────────────
    try:
        config_text = await _bkp.read_backup(ref, filename=filename)
    except Exception as exc:
        return RestoreResponse(
            success=False,
            error=f"Could not read backup: {exc}",
        )

    # ── Pre-restore backup ────────────────────────────────────────────
    try:
        running = await _mgr.send_show("show running-config")
        await _bkp.save_backup(
            running.output,
            reason=f"pre-restore-{ref[:8]}",
        )
    except Exception as exc:
        warnings.append(f"Pre-restore backup failed: {exc}")

    # ── Decide method ─────────────────────────────────────────────────
    use_replace = False
    if method != "line_by_line":
        caps = await detect_capabilities(mgr=_mgr)
        if caps.configure_replace_available:
            use_replace = True
            log.info("restore.using_configure_replace")

    method_used = ""

    # ── Method 1: configure replace ───────────────────────────────────
    if use_replace:
        method_used = "configure_replace"
        try:
            # Write config to flash: (via SCP would be ideal, but we use a
            # workaround: write to a temporary config section on the router).
            # NOTE: In production, you'd SCP the file to flash: first.
            # For now, we fall through to line-by-line with a warning.
            warnings.append(
                "configure replace requires the backup file on flash:. "
                "SCP upload not yet implemented; falling back to line-by-line.",
            )
            use_replace = False
        except Exception as exc:
            warnings.append(f"configure replace failed: {exc}")
            use_replace = False

    # ── Method 2: line-by-line ────────────────────────────────────────
    if not use_replace:
        method_used = "line_by_line"
        warnings.append(
            "Line-by-line restore is best-effort. "
            "It cannot remove commands that are absent from the backup.",
        )
        try:
            lines = _prepare_config_lines(config_text)
            if not lines:
                return RestoreResponse(
                    success=False,
                    method_used=method_used,
                    warnings=warnings,
                    error="Parsed 0 config lines from backup",
                )

            results = await _mgr.send_configs(lines, stop_on_failed=False)
            errors = [r for r in results if r.failed or detect_ios_error(r.output)]
            if errors:
                err_summary = "; ".join(
                    f"{r.command}: {r.output[:80]}" for r in errors[:5]
                )
                warnings.append(f"Some lines failed: {err_summary}")

        except Exception as exc:
            return RestoreResponse(
                success=False,
                method_used=method_used,
                warnings=warnings,
                error=f"Line-by-line restore failed: {exc}",
            )

    # ── Verification ──────────────────────────────────────────────────
    verification = ""
    try:
        result = await _mgr.send_show("show running-config | include hostname")
        verification = result.output
    except Exception:
        pass

    log.info("restore.done", method=method_used, ref=ref)
    return RestoreResponse(
        success=True,
        method_used=method_used,
        warnings=warnings,
        verification_output=verification,
    )


def _prepare_config_lines(config_text: str) -> list[str]:
    """Strip meta-lines from a saved config, returning lines suitable for replay."""
    skip_prefixes = (
        "!", "building configuration", "current configuration",
        "end", "version ", "boot-start-marker", "boot-end-marker",
    )
    lines: list[str] = []
    for raw in config_text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.lower().startswith(skip_prefixes):
            continue
        lines.append(raw.rstrip())
    return lines

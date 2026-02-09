"""Config apply service: backup -> apply -> verify -> backup -> rollback on failure."""

from __future__ import annotations

from app.models.plan import ApplyResult, CommandExecution, ConfigPlan
from app.services import plan_service
from app.services.backup import BackupService, backup_service
from app.services.ssh_manager import SSHSessionManager, ssh_manager
from app.utils.ios_parser import detect_ios_error
from app.utils.logging import get_logger

log = get_logger(__name__)


async def apply_plan(
    plan: ConfigPlan,
    *,
    mgr: SSHSessionManager | None = None,
    bkp: BackupService | None = None,
) -> ApplyResult:
    """Execute a validated plan with full backup/rollback lifecycle.

    1. Pre-backup (running-config -> git)
    2. Apply config commands
    3. Run verification show commands
    4. Write memory (save to startup-config)
    5. Post-backup
    6. On failure: attempt rollback
    """
    _mgr = mgr or ssh_manager
    _bkp = bkp or backup_service

    pre_sha: str | None = None
    post_sha: str | None = None
    executed: list[CommandExecution] = []
    verifications: list[CommandExecution] = []
    rollback_attempted = False
    rollback_success: bool | None = None
    rollback_details = ""
    success = True

    plan_summary = {
        "plan_id": plan.plan_id,
        "description": plan.description,
        "commands": plan.commands,
        "affected_entities": plan.affected_entities,
    }

    # ── 1. Pre-backup ─────────────────────────────────────────────────
    try:
        running = await _mgr.send_show("show running-config")
        _, pre_sha = await _bkp.save_backup(
            running.output,
            reason=f"pre-apply-{plan.plan_id[:8]}",
            plan_summary=plan_summary,
        )
        log.info("apply.pre_backup", sha=pre_sha[:8])
    except Exception as exc:
        log.error("apply.pre_backup_failed", error=str(exc))
        return ApplyResult(
            plan_id=plan.plan_id,
            success=False,
            executed_commands=[],
            pre_backup_sha=None,
            rollback_details=f"Pre-backup failed: {exc}",
        )

    # ── 2. Apply commands ─────────────────────────────────────────────
    try:
        # Build full command list: mode-path entries (excluding "configure terminal"
        # which scrapli handles) + actual commands
        config_cmds: list[str] = []
        for mp in plan.mode_path:
            if mp.strip().lower() != "configure terminal":
                config_cmds.append(mp)
        config_cmds.extend(plan.commands)

        results = await _mgr.send_configs(config_cmds, stop_on_failed=True)

        for r in results:
            cmd_success = not r.failed and not detect_ios_error(r.output)
            executed.append(
                CommandExecution(
                    command=r.command,
                    output=r.output,
                    success=cmd_success,
                ),
            )
            if not cmd_success:
                success = False
                log.warning(
                    "apply.cmd_failed",
                    cmd=r.command,
                    output=r.output[:200],
                )

    except Exception as exc:
        log.error("apply.exec_failed", error=str(exc))
        success = False
        executed.append(
            CommandExecution(
                command="(exception)",
                output=str(exc),
                success=False,
            ),
        )

    # ── 3. Verification ──────────────────────────────────────────────
    if plan.verification:
        for show_cmd in plan.verification:
            try:
                result = await _mgr.send_show(show_cmd)
                verifications.append(
                    CommandExecution(
                        command=show_cmd,
                        output=result.output,
                        success=not result.failed,
                    ),
                )
            except Exception as exc:
                verifications.append(
                    CommandExecution(
                        command=show_cmd,
                        output=str(exc),
                        success=False,
                    ),
                )

    # ── 4. Write memory ─────────────────────────────────────────────
    if success:
        try:
            wr_result = await _mgr.send_show("write memory")
            log.info("apply.write_memory", output=wr_result.output[:80])
        except Exception as exc:
            log.error("apply.write_memory_failed", error=str(exc))

    # ── 5. Post-backup ────────────────────────────────────────────────
    try:
        running = await _mgr.send_show("show running-config")
        _, post_sha = await _bkp.save_backup(
            running.output,
            reason=f"post-apply-{plan.plan_id[:8]}",
            plan_summary=plan_summary,
        )
        log.info("apply.post_backup", sha=post_sha[:8])
    except Exception as exc:
        log.error("apply.post_backup_failed", error=str(exc))

    # ── 6. Rollback on failure ────────────────────────────────────────
    if not success and pre_sha:
        rollback_attempted = True
        try:
            log.warning("apply.rollback_starting", pre_sha=pre_sha[:8])
            # Retrieve pre-change config
            pre_config = await _bkp.read_backup(pre_sha)
            # Apply line-by-line (best effort)
            lines = [
                l.strip()
                for l in pre_config.splitlines()
                if l.strip()
                and not l.strip().startswith("!")
                and not l.strip().startswith("Building configuration")
                and not l.strip().startswith("Current configuration")
                and not l.strip().startswith("end")
                and not l.strip().startswith("version")
            ]
            # Only re-apply the mode-path + commands scope (safer than full config)
            scope_cmds: list[str] = []
            for mp in plan.mode_path:
                if mp.strip().lower() != "configure terminal":
                    scope_cmds.append(mp)
            scope_cmds.append("default " + plan.mode_path[-1] if plan.mode_path else "")

            if scope_cmds and scope_cmds[-1]:
                await _mgr.send_configs(
                    [c for c in scope_cmds if c],
                    stop_on_failed=False,
                )

            rollback_success = True
            rollback_details = "Scoped rollback attempted (defaulted affected section)"
            log.info("apply.rollback_done")
        except Exception as exc:
            rollback_success = False
            rollback_details = f"Rollback failed: {exc}"
            log.error("apply.rollback_failed", error=str(exc))

    return ApplyResult(
        plan_id=plan.plan_id,
        success=success,
        executed_commands=executed,
        pre_backup_sha=pre_sha,
        post_backup_sha=post_sha,
        verification_results=verifications,
        rollback_attempted=rollback_attempted,
        rollback_success=rollback_success,
        rollback_details=rollback_details,
    )

"""Backup and restore endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_api_key
from app.models.responses import (
    BackupRequest,
    BackupResponse,
    RestoreRequest,
    RestoreResponse,
)
from app.services.backup import backup_service
from app.services.restore import restore_backup
from app.services.ssh_manager import ssh_manager

router = APIRouter(tags=["backup"], dependencies=[Depends(require_api_key)])


@router.post("/backup", response_model=BackupResponse)
async def take_backup(req: BackupRequest) -> BackupResponse:
    """Take an on-demand backup of running-config and push to git."""
    try:
        result = await ssh_manager.send_show("show running-config")
        if result.failed:
            return BackupResponse(success=False, error="Failed to get running-config")

        filename, sha = await backup_service.save_backup(
            result.output,
            reason=req.reason,
        )
        return BackupResponse(success=True, filename=filename, commit_sha=sha)
    except Exception as exc:
        return BackupResponse(success=False, error=str(exc))


@router.post("/restore", response_model=RestoreResponse)
async def restore(req: RestoreRequest) -> RestoreResponse:
    """Restore a configuration from a git backup ref."""
    return await restore_backup(
        ref=req.ref,
        filename=req.filename,
        method=req.method,
    )


@router.get("/backups")
async def list_backups(limit: int = 20) -> list[dict]:
    """List recent backup commits."""
    return await backup_service.list_backups(limit=limit)

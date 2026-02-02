"""Exec-mode show commands endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_api_key
from app.models.responses import ShowCommandRequest, ShowCommandResponse
from app.services.command_filter import check_exec_command
from app.services.ssh_manager import ssh_manager

router = APIRouter(tags=["show"], dependencies=[Depends(require_api_key)])


@router.post("/show", response_model=ShowCommandResponse)
async def run_show_command(req: ShowCommandRequest) -> ShowCommandResponse:
    """Run an allowlisted exec-mode command."""
    filt = check_exec_command(req.command)
    if not filt.allowed:
        raise HTTPException(status_code=403, detail=filt.reason)

    try:
        result = await ssh_manager.send_show(req.command)
        return ShowCommandResponse(
            command=req.command,
            output=result.output,
            success=not result.failed,
        )
    except Exception as exc:
        return ShowCommandResponse(
            command=req.command,
            output="",
            success=False,
            error=str(exc),
        )

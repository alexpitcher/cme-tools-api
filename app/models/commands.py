"""Command-related data structures."""

from __future__ import annotations

from pydantic import BaseModel


class CommandResult(BaseModel):
    """Internal result from SSH command execution."""

    command: str
    output: str
    failed: bool = False
    elapsed_time: float = 0.0

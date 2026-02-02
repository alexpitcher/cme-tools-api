"""API key authentication dependency."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    api_key: str | None = Security(_api_key_header),
) -> str:
    """FastAPI dependency that enforces X-API-Key header.

    If CME_API_KEY is blank the check is skipped (dev convenience).
    """
    if not settings.cme_api_key:
        return "no-key-configured"
    if api_key is None or api_key != settings.cme_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return api_key

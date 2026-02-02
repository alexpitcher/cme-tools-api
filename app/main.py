"""FastAPI application entry-point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.routers import backup, capabilities, cme, config, health, show
from app.services.backup import backup_service
from app.services.ssh_manager import ssh_manager
from app.utils.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    setup_logging()
    # Ensure the git backup working directory is ready
    try:
        await backup_service.ensure_repo()
    except Exception:
        pass  # Non-fatal at startup; will retry on first backup
    yield
    # Shutdown: close SSH session
    await ssh_manager.close()


app = FastAPI(
    title="CME Tools API",
    description="Cisco Unified CME configuration management service",
    version=__version__,
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(show.router)
app.include_router(config.router)
app.include_router(backup.router)
app.include_router(capabilities.router)
app.include_router(cme.router)

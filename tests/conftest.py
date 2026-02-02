"""Shared pytest fixtures."""

from __future__ import annotations

import os
import asyncio

# Force settings to use test-safe defaults before any import
os.environ.setdefault("CME_ROUTER_HOST", "127.0.0.1")
os.environ.setdefault("CME_ROUTER_PASSWORD", "test")
os.environ.setdefault("CME_API_KEY", "")
os.environ.setdefault("CME_GIT_REMOTE_URL", "https://example.com/test.git")
os.environ.setdefault("CME_MAINTENANCE_MODE", "false")

import pytest
from httpx import ASGITransport, AsyncClient

from tests.mock_ssh import MockSSHManager


@pytest.fixture
def mock_ssh():
    """Provide a fresh MockSSHManager."""
    return MockSSHManager()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client(mock_ssh, tmp_path, monkeypatch):
    """Async test client with the mock SSH manager injected."""
    # Point backup workdir to a temp directory
    monkeypatch.setenv("CME_API_KEY", "")

    # Re-import to pick up patched env
    from app.config import Settings

    test_settings = Settings(backup_workdir=str(tmp_path / "backup"))
    (tmp_path / "backup").mkdir()

    # Initialise a git repo in the backup workdir
    import subprocess

    wd = tmp_path / "backup"
    subprocess.run(["git", "init"], cwd=str(wd), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.local"],
        cwd=str(wd), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(wd), check=True, capture_output=True,
    )
    # Create backup folder
    (wd / "a14-con").mkdir()
    # Initial commit so git log works
    (wd / ".gitkeep").touch()
    subprocess.run(["git", "add", "."], cwd=str(wd), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(wd), check=True, capture_output=True,
    )

    # Patch singletons
    import app.services.ssh_manager as ssh_mod
    import app.services.backup as bkp_mod
    from app.services.backup import BackupService

    original_ssh = ssh_mod.ssh_manager
    original_bkp = bkp_mod.backup_service

    ssh_mod.ssh_manager = mock_ssh
    bkp_instance = BackupService(test_settings)
    bkp_mod.backup_service = bkp_instance

    # Also patch the modules that import from services
    import app.routers.health as rh
    import app.routers.show as rs
    import app.routers.backup as rb
    import app.services.apply as sa
    import app.services.validate as sv
    import app.services.restore as sr
    import app.services.capabilities as sc

    import app.routers.cme as rc

    rh.ssh_manager = mock_ssh
    rs.ssh_manager = mock_ssh
    rc.ssh_manager = mock_ssh

    from app.main import app as fastapi_app

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Restore
    ssh_mod.ssh_manager = original_ssh
    bkp_mod.backup_service = original_bkp

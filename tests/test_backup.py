"""Tests for the git backup service (uses a temp repo, no real remote)."""

from __future__ import annotations

import subprocess

import pytest

from app.config import Settings
from app.services.backup import BackupService


@pytest.fixture
def backup_svc(tmp_path):
    """Create a BackupService pointing at a temp git repo."""
    wd = tmp_path / "backup"
    wd.mkdir()

    # Initialise git repo
    subprocess.run(["git", "init"], cwd=str(wd), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.local"],
        cwd=str(wd), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(wd), check=True, capture_output=True,
    )
    (wd / "a14-con").mkdir()
    (wd / ".gitkeep").touch()
    subprocess.run(["git", "add", "."], cwd=str(wd), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(wd), check=True, capture_output=True,
    )

    settings = Settings(
        backup_workdir=str(wd),
        cme_git_backup_folder="a14-con",
        cme_git_branch="main",
        cme_git_remote_url="https://example.com/test.git",
    )
    return BackupService(cfg=settings)


@pytest.mark.asyncio
async def test_save_backup_creates_files(backup_svc):
    filename, sha = await backup_svc.save_backup(
        config_text="hostname TestRouter\n!\nend\n",
        reason="unit-test",
    )
    assert filename.endswith(".cfg")
    assert "unit-test" in filename
    assert len(sha) == 40  # full SHA


@pytest.mark.asyncio
async def test_save_backup_creates_json_manifest(backup_svc, tmp_path):
    filename, _ = await backup_svc.save_backup(
        config_text="hostname R1\n",
        reason="manifest-test",
        router_meta={"version": "15.7"},
    )
    json_name = filename.replace(".cfg", ".json")
    json_path = tmp_path / "backup" / "a14-con" / json_name
    assert json_path.exists()
    import json

    data = json.loads(json_path.read_text())
    assert data["reason"] == "manifest-test"
    assert data["router"]["version"] == "15.7"


@pytest.mark.asyncio
async def test_save_and_read_backup(backup_svc):
    config = "hostname ReadBack\ninterface Gi0/0\n ip address 1.2.3.4 255.255.255.0\n!\nend\n"
    filename, sha = await backup_svc.save_backup(config, reason="readback")
    content = await backup_svc.read_backup(sha, filename=filename)
    assert "hostname ReadBack" in content


@pytest.mark.asyncio
async def test_list_backups(backup_svc):
    await backup_svc.save_backup("config1\n", reason="first")
    await backup_svc.save_backup("config2\n", reason="second")
    entries = await backup_svc.list_backups(limit=5)
    assert len(entries) >= 2


@pytest.mark.asyncio
async def test_filename_format(backup_svc):
    filename, _ = await backup_svc.save_backup("test\n", reason="fmt-check")
    parts = filename.split("__")
    assert len(parts) == 3  # dd-mm-yy, HHMMSS, reason.cfg
    assert parts[0].count("-") == 2  # dd-mm-yy
    assert parts[2].endswith(".cfg")

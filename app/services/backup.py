"""Git-based backup service.

Saves running-config snapshots to a local git working directory and pushes
to the configured Gitea remote.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import Settings, settings
from app.utils.logging import get_logger

log = get_logger(__name__)


class BackupService:
    """Manages config backups inside a local git repository."""

    def __init__(self, cfg: Settings | None = None) -> None:
        self._cfg = cfg or settings
        self._workdir = Path(self._cfg.backup_workdir)
        self._folder = self._cfg.cme_git_backup_folder
        self._lock = asyncio.Lock()

    # ── helpers ───────────────────────────────────────────────────────

    async def _git(self, *args: str, check: bool = True) -> str:
        """Run a git command inside the working directory."""
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = self._cfg.cme_git_author_name
        env["GIT_AUTHOR_EMAIL"] = self._cfg.cme_git_author_email
        env["GIT_COMMITTER_NAME"] = self._cfg.cme_git_author_name
        env["GIT_COMMITTER_EMAIL"] = self._cfg.cme_git_author_email

        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=str(self._workdir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()
        out = stdout.decode(errors="replace")
        err = stderr.decode(errors="replace")
        if check and proc.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {err}")
        log.debug("git.exec", args=args, rc=proc.returncode, out=out[:200])
        return out.strip()

    def _remote_url(self) -> str:
        """Build the remote URL, injecting HTTP creds if provided."""
        url = self._cfg.cme_git_remote_url
        user = self._cfg.cme_git_http_username
        token = self._cfg.cme_git_http_token
        if user and token and url.startswith("https://"):
            # https://user:token@host/path
            url = url.replace("https://", f"https://{user}:{token}@", 1)
        elif token and url.startswith("https://"):
            url = url.replace("https://", f"https://{token}@", 1)
        return url

    # ── init / ensure repo ────────────────────────────────────────────

    async def ensure_repo(self) -> None:
        """Clone or initialise the local git repository."""
        async with self._lock:
            self._workdir.mkdir(parents=True, exist_ok=True)
            git_dir = self._workdir / ".git"
            if not git_dir.exists():
                log.info("backup.clone", remote=self._cfg.cme_git_remote_url)
                try:
                    await self._git(
                        "clone", "--depth=1",
                        "-b", self._cfg.cme_git_branch,
                        self._remote_url(), ".",
                        check=True,
                    )
                except RuntimeError:
                    log.info("backup.init_fresh")
                    await self._git("init", check=True)
                    await self._git(
                        "remote", "add", "origin", self._remote_url(),
                        check=False,
                    )
                    await self._git(
                        "checkout", "-b", self._cfg.cme_git_branch,
                        check=False,
                    )
            # Ensure backup folder exists
            folder = self._workdir / self._folder
            folder.mkdir(parents=True, exist_ok=True)

    # ── public: take backup ───────────────────────────────────────────

    async def save_backup(
        self,
        config_text: str,
        reason: str = "manual",
        plan_summary: dict | None = None,
        router_meta: dict | None = None,
    ) -> tuple[str, str]:
        """Save a backup, commit, and push.

        Returns (filename, commit_sha).
        """
        async with self._lock:
            await self._pull()

            now = datetime.now(timezone.utc)
            prefix = now.strftime("%d-%m-%y__%H%M%S")
            safe_reason = reason.replace(" ", "-").replace("/", "-")[:40]
            base = f"{prefix}__{safe_reason}"
            cfg_name = f"{base}.cfg"
            json_name = f"{base}.json"

            folder = self._workdir / self._folder
            folder.mkdir(parents=True, exist_ok=True)

            cfg_path = folder / cfg_name
            cfg_path.write_text(config_text, encoding="utf-8")

            manifest: dict = {
                "timestamp": now.isoformat(),
                "reason": reason,
                "router_host": self._cfg.cme_router_host,
                "router_name": self._cfg.cme_router_name,
            }
            if router_meta:
                manifest["router"] = router_meta
            if plan_summary:
                manifest["plan"] = plan_summary

            json_path = folder / json_name
            json_path.write_text(
                json.dumps(manifest, indent=2, default=str),
                encoding="utf-8",
            )

            await self._git("add", str(cfg_path.relative_to(self._workdir)))
            await self._git("add", str(json_path.relative_to(self._workdir)))
            await self._git(
                "commit", "-m",
                f"backup: {reason} ({cfg_name})",
            )
            sha = await self._git("rev-parse", "HEAD")
            await self._push()

            log.info("backup.saved", file=cfg_name, sha=sha[:8])
            return cfg_name, sha

    # ── public: read backup from ref ──────────────────────────────────

    async def read_backup(
        self,
        ref: str,
        filename: str | None = None,
    ) -> str:
        """Retrieve a backup config by git ref.

        If *filename* is given, reads that file at the given ref.
        Otherwise looks for the first .cfg in the backup folder at that ref.
        """
        async with self._lock:
            await self._pull()
            if filename:
                path = f"{self._folder}/{filename}"
            else:
                # list cfg files at ref
                ls = await self._git(
                    "ls-tree", "--name-only", ref, f"{self._folder}/",
                    check=False,
                )
                cfgs = [
                    f for f in ls.splitlines() if f.endswith(".cfg")
                ]
                if not cfgs:
                    raise FileNotFoundError(
                        f"No .cfg files found at ref {ref}",
                    )
                path = cfgs[-1]  # latest by name (dd-mm-yy prefix)

            content = await self._git("show", f"{ref}:{path}")
            return content

    # ── public: list backups ──────────────────────────────────────────

    async def list_backups(self, limit: int = 20) -> list[dict]:
        """Return recent backup commits."""
        async with self._lock:
            log_out = await self._git(
                "log", f"--max-count={limit}",
                "--pretty=format:%H|%ai|%s",
                "--", f"{self._folder}/",
                check=False,
            )
            entries: list[dict] = []
            for line in log_out.splitlines():
                parts = line.split("|", 2)
                if len(parts) == 3:
                    entries.append({
                        "sha": parts[0],
                        "date": parts[1],
                        "message": parts[2],
                    })
            return entries

    # ── internal git helpers ──────────────────────────────────────────

    async def _pull(self) -> None:
        try:
            await self._git(
                "pull", "--rebase", "origin", self._cfg.cme_git_branch,
                check=False,
            )
        except Exception as exc:
            log.warning("backup.pull_failed", error=str(exc))

    async def _push(self) -> None:
        try:
            await self._git(
                "push", "origin", self._cfg.cme_git_branch,
                check=False,
            )
        except Exception as exc:
            log.warning("backup.push_failed", error=str(exc))


# Singleton
backup_service = BackupService()

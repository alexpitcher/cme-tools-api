"""Application settings loaded from environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configuration is driven by environment variables."""

    # Router connection
    cme_router_host: str = "10.20.102.11"
    cme_router_port: int = 22
    cme_router_username: str = "admin"
    cme_router_password: str = ""
    cme_router_ssh_key_path: str = ""
    cme_router_enable_secret: str = ""
    cme_router_name: str = "a14-con"

    # Session
    cme_session_idle_timeout_seconds: int = 30

    # API key
    cme_api_key: str = ""

    # Git backup
    cme_git_remote_url: str = "https://git.int.a14.io/a14/a14-cfg.git"
    cme_git_branch: str = "main"
    cme_git_backup_folder: str = "a14-con"
    cme_git_http_username: str = ""
    cme_git_http_token: str = ""
    cme_git_author_name: str = "CME Tools Bot"
    cme_git_author_email: str = "cme-tools-bot@local"

    # Maintenance mode widens the command allowlist
    cme_maintenance_mode: bool = False

    # Internal
    backup_workdir: str = Field(default="/data/backup-workdir")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Singleton – import this from anywhere
settings = Settings()

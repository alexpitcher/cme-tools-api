"""SSH session manager with connection reuse, idle timeout, and concurrency lock.

Uses scrapli IOSXEDriver (paramiko transport) run inside a single-thread executor
so the FastAPI async event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from scrapli.driver.core import IOSXEDriver
from scrapli.response import Response

from app.config import Settings, settings
from app.models.commands import CommandResult
from app.utils.logging import get_logger

log = get_logger(__name__)


class SSHSessionManager:
    """Singleton-style manager for a single Cisco IOS SSH session."""

    def __init__(self, cfg: Settings | None = None) -> None:
        self._cfg = cfg or settings
        self._driver: Optional[IOSXEDriver] = None
        self._lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ssh")
        self._idle_handle: Optional[asyncio.TimerHandle] = None
        self._last_used: float = 0.0

    # ── connection lifecycle ──────────────────────────────────────────

    def _build_driver(self) -> IOSXEDriver:
        transport = "paramiko"
        auth_kwargs: dict = dict(
            host=self._cfg.cme_router_host,
            port=self._cfg.cme_router_port,
            auth_username=self._cfg.cme_router_username,
            auth_password=self._cfg.cme_router_password,
            auth_strict_key=False,
            transport=transport,
            timeout_socket=15,
            timeout_transport=15,
            timeout_ops=30,
        )
        if self._cfg.cme_router_ssh_key_path:
            auth_kwargs["auth_private_key"] = self._cfg.cme_router_ssh_key_path
        return IOSXEDriver(**auth_kwargs)

    def _open_sync(self) -> IOSXEDriver:
        log.info("ssh.connecting", host=self._cfg.cme_router_host)
        driver = self._build_driver()
        driver.open()
        driver.send_command("terminal length 0")
        driver.send_command("terminal width 0")
        if self._cfg.cme_router_enable_secret:
            try:
                driver.send_command("enable")
                driver.send_interactive(
                    interact_events=[
                        ("enable", "assword:", False),
                        (self._cfg.cme_router_enable_secret, "#", True),
                    ],
                )
            except Exception:
                log.warning("ssh.enable_failed")
        log.info("ssh.connected")
        return driver

    def _close_sync(self) -> None:
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None
            log.info("ssh.closed")

    async def _ensure(self) -> IOSXEDriver:
        if self._driver is not None:
            try:
                if self._driver.isalive:
                    return self._driver
            except Exception:
                pass
            await self._run(_close_sync_wrapper, self)
        self._driver = await self._run(SSHSessionManager._open_sync, self)
        return self._driver

    # ── idle timeout ──────────────────────────────────────────────────

    def _reset_idle(self) -> None:
        self._last_used = time.monotonic()
        if self._idle_handle is not None:
            self._idle_handle.cancel()
        try:
            loop = asyncio.get_running_loop()
            self._idle_handle = loop.call_later(
                self._cfg.cme_session_idle_timeout_seconds,
                lambda: asyncio.ensure_future(self._idle_close()),
            )
        except RuntimeError:
            pass

    async def _idle_close(self) -> None:
        async with self._lock:
            elapsed = time.monotonic() - self._last_used
            if elapsed >= self._cfg.cme_session_idle_timeout_seconds:
                log.info("ssh.idle_timeout", elapsed=elapsed)
                await self._run(_close_sync_wrapper, self)

    # ── helpers ───────────────────────────────────────────────────────

    async def _run(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, fn, *args)

    # ── public: exec-mode commands ────────────────────────────────────

    async def send_show(self, command: str) -> CommandResult:
        async with self._lock:
            driver = await self._ensure()
            self._reset_idle()
            resp: Response = await self._run(
                _send_command_wrapper, driver, command,
            )
            return CommandResult(
                command=command,
                output=resp.result,
                failed=resp.failed,
                elapsed_time=resp.elapsed_time,
            )

    # ── public: config-mode commands ──────────────────────────────────

    async def send_configs(
        self,
        configs: list[str],
        *,
        stop_on_failed: bool = False,
    ) -> list[CommandResult]:
        """Send a list of config commands (scrapli handles conf t / end)."""
        async with self._lock:
            driver = await self._ensure()
            self._reset_idle()
            results = await self._run(
                _send_configs_wrapper, driver, configs, stop_on_failed,
            )
            return results

    # ── public: raw channel write (for ? probing) ─────────────────────

    async def probe_help(self, text: str, wait: float = 2.0) -> str:
        """Send *text* directly to the channel (no newline) and read back.

        Used for IOS ``?`` inline help probing.  After reading, the line
        is cleared with Ctrl-U so the router returns to a clean prompt.
        """
        async with self._lock:
            driver = await self._ensure()
            self._reset_idle()
            return await self._run(
                _probe_help_wrapper, driver, text, wait,
            )

    # ── public: lifecycle helpers ─────────────────────────────────────

    async def close(self) -> None:
        async with self._lock:
            if self._idle_handle is not None:
                self._idle_handle.cancel()
            await self._run(_close_sync_wrapper, self)

    @property
    def is_connected(self) -> bool:
        if self._driver is None:
            return False
        try:
            return self._driver.isalive
        except Exception:
            return False


# ── module-level sync wrappers (picklable / executor-friendly) ────────────

def _close_sync_wrapper(mgr: SSHSessionManager) -> None:
    mgr._close_sync()


def _send_command_wrapper(driver: IOSXEDriver, command: str) -> Response:
    return driver.send_command(command, timeout_ops=30)


def _send_configs_wrapper(
    driver: IOSXEDriver,
    configs: list[str],
    stop_on_failed: bool,
) -> list[CommandResult]:
    results: list[CommandResult] = []
    multi = driver.send_configs(configs, stop_on_failed=stop_on_failed)
    for resp in multi:
        results.append(
            CommandResult(
                command=resp.channel_input,
                output=resp.result,
                failed=resp.failed,
                elapsed_time=resp.elapsed_time,
            ),
        )
    return results


def _probe_help_wrapper(driver: IOSXEDriver, text: str, wait: float) -> str:
    """Low-level ? probe using the paramiko channel underneath scrapli."""
    transport = driver.transport
    try:
        # Drain any pending output first
        if hasattr(transport, "session") and transport.session is not None:
            chan = transport.session
            while chan.recv_ready():
                chan.recv(65535)

            # Send the probe text (e.g. "max-ephones ?")
            chan.sendall(text.encode())
            time.sleep(wait)

            # Read response
            output = b""
            while chan.recv_ready():
                output += chan.recv(65535)

            # Clear line: Ctrl-U then Enter
            chan.sendall(b"\x15\r\n")
            time.sleep(0.5)
            while chan.recv_ready():
                chan.recv(65535)

            return output.decode("utf-8", errors="replace")
    except Exception as exc:
        log.warning("ssh.probe_help_failed", error=str(exc))
    return ""


# ── Singleton instance ────────────────────────────────────────────────────

ssh_manager = SSHSessionManager()

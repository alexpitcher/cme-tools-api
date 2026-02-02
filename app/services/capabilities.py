"""IOS capability detection (configure replace, archive, etc.)."""

from __future__ import annotations

from app.models.responses import CapabilitiesResponse
from app.services.ssh_manager import SSHSessionManager, ssh_manager
from app.utils.ios_parser import parse_show_version
from app.utils.logging import get_logger

log = get_logger(__name__)


async def detect_capabilities(
    *,
    mgr: SSHSessionManager | None = None,
) -> CapabilitiesResponse:
    """Probe the router for available features."""
    _mgr = mgr or ssh_manager

    caps = CapabilitiesResponse()

    # ── show version ──────────────────────────────────────────────────
    try:
        result = await _mgr.send_show("show version")
        info = parse_show_version(result.output)
        caps.ios_version = info.get("ios_version", "")
        caps.hostname = info.get("hostname", "")
        caps.model = info.get("model", "")
    except Exception as exc:
        log.warning("capabilities.version_failed", error=str(exc))

    # ── configure replace ? ───────────────────────────────────────────
    try:
        result = await _mgr.send_show("configure replace ?")
        output = result.output.lower()
        if "invalid" not in output and "unrecognized" not in output:
            caps.configure_replace_available = True
            caps.detected_features["configure_replace"] = True
        else:
            caps.detected_features["configure_replace"] = False
    except Exception:
        caps.detected_features["configure_replace"] = False

    # ── archive ───────────────────────────────────────────────────────
    try:
        result = await _mgr.send_show("show archive")
        output = result.output.lower()
        if "invalid" not in output and "not been configured" not in output:
            caps.archive_available = True
            caps.detected_features["archive"] = True
        else:
            caps.detected_features["archive"] = False
    except Exception:
        caps.detected_features["archive"] = False

    # ── file system ───────────────────────────────────────────────────
    try:
        result = await _mgr.send_show("show flash: | include bytes")
        caps.detected_features["flash_available"] = not result.failed
    except Exception:
        caps.detected_features["flash_available"] = False

    log.info("capabilities.detected", features=caps.detected_features)
    return caps

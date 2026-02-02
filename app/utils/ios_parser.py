"""Utilities for parsing Cisco IOS CLI output."""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Error detection
# ---------------------------------------------------------------------------

IOS_ERROR_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"% Invalid input detected", re.IGNORECASE),
    re.compile(r"% Incomplete command", re.IGNORECASE),
    re.compile(r"% Ambiguous command", re.IGNORECASE),
    re.compile(r"% Unrecognized command", re.IGNORECASE),
    re.compile(r"% Bad IP address", re.IGNORECASE),
    re.compile(r"% Invalid range", re.IGNORECASE),
    re.compile(r"% Cannot", re.IGNORECASE),
    re.compile(r"% Error", re.IGNORECASE),
]


def detect_ios_error(output: str) -> str | None:
    """Return the first IOS error string found, or None."""
    for pat in IOS_ERROR_PATTERNS:
        match = pat.search(output)
        if match:
            # Return the full line containing the match
            for line in output.splitlines():
                if pat.search(line):
                    return line.strip()
    return None


def is_ios_error(output: str) -> bool:
    return detect_ios_error(output) is not None


# ---------------------------------------------------------------------------
# show version parsing
# ---------------------------------------------------------------------------

def parse_show_version(output: str) -> dict[str, str]:
    """Extract key fields from 'show version' output."""
    info: dict[str, str] = {}
    for line in output.splitlines():
        line_s = line.strip()
        if "Cisco IOS Software" in line_s or "IOS (tm)" in line_s:
            info["ios_line"] = line_s
            m = re.search(r"Version\s+([\S]+)", line_s)
            if m:
                info["ios_version"] = m.group(1).rstrip(",")
        if line_s.lower().startswith("cisco") and (
            "processor" in line_s.lower()
            or "bytes of memory" in line_s.lower()
        ):
            info["model_line"] = line_s
            m = re.match(r"[Cc]isco\s+(\S+)", line_s)
            if m:
                info["model"] = m.group(1)
        m = re.match(r"^(\S+)\s+uptime is", line_s)
        if m:
            info["hostname"] = m.group(1)
    return info


# ---------------------------------------------------------------------------
# telephony-service parsing
# ---------------------------------------------------------------------------

def parse_telephony_service(output: str) -> dict[str, Any]:
    """Parse 'show telephony-service' into key-value pairs."""
    data: dict[str, Any] = {}
    for line in output.splitlines():
        line_s = line.strip()
        if not line_s:
            continue
        m = re.match(r"^([\w\s\-]+?)\s*[:=]\s*(.+)$", line_s)
        if m:
            key = re.sub(r"\s+", "_", m.group(1).strip().lower())
            data[key] = m.group(2).strip()
        # Max ephones / dn
        m = re.match(r"^max-ephones\s+(\d+)", line_s, re.IGNORECASE)
        if m:
            data["max_ephones"] = int(m.group(1))
        m = re.match(r"^max-dn\s+(\d+)", line_s, re.IGNORECASE)
        if m:
            data["max_dn"] = int(m.group(1))
    return data


# ---------------------------------------------------------------------------
# ephone parsing
# ---------------------------------------------------------------------------

_EPHONE_HEADER_RE = re.compile(r"^ephone-(\d+)", re.IGNORECASE)
# Match both "Mac:XXXX" and "MacAddress:XXXX" / "Mac-Addr XXXX" forms
_MAC_RE = re.compile(
    r"Mac(?:[- ]?Addr(?:ess)?)?\s*[:=]\s*([\da-fA-F.:-]+)", re.IGNORECASE,
)
_REG_RE = re.compile(r"\b(REGISTERED|UNREGISTERED|DECEASED)\b")
_IP_RE = re.compile(r"\bIP:([\d.]+)")
_TYPE_RE = re.compile(
    r"(?:Telecaster\s+)?(\d{4}[A-Za-z]*)\s+keepalive", re.IGNORECASE,
)
_DN_RE = re.compile(r"primary_dn:\s*(\d+)", re.IGNORECASE)


def parse_ephone_summary(output: str) -> list[dict[str, Any]]:
    """Parse 'show ephone summary' or 'show ephone' into a list of phones."""
    phones: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in output.splitlines():
        line_s = line.strip()
        hm = _EPHONE_HEADER_RE.match(line_s)
        if hm:
            if current:
                phones.append(current)
            current = {"ephone_id": int(hm.group(1))}
        if current is None:
            continue
        mm = _MAC_RE.search(line_s)
        if mm:
            current["mac"] = mm.group(1)
        rm = _REG_RE.search(line_s)
        if rm:
            current["status"] = rm.group(1).lower()
        im = _IP_RE.search(line_s)
        if im and im.group(1) != "0.0.0.0":
            current["ip"] = im.group(1)
        tm = _TYPE_RE.search(line_s)
        if tm:
            current["type"] = tm.group(1)
        dm = _DN_RE.search(line_s)
        if dm:
            current["primary_dn"] = int(dm.group(1))

    if current:
        phones.append(current)
    return phones


# ---------------------------------------------------------------------------
# Help-probe output parsing
# ---------------------------------------------------------------------------

def parse_help_output(output: str) -> dict[str, Any]:
    """Parse the output of a '?' help probe.

    Returns {"valid": bool, "completions": [...], "error": str | None}
    """
    error = detect_ios_error(output)
    if error:
        return {"valid": False, "completions": [], "error": error}

    completions: list[str] = []
    for line in output.splitlines():
        line_s = line.strip()
        if not line_s:
            continue
        # IOS help lines look like: "  <cr>", "  WORD  description", "  <1-240>  desc"
        m = re.match(r"^\s{2,}(\S+)\s+(.*)$", line)
        if m:
            completions.append(f"{m.group(1)}  {m.group(2).strip()}")
    return {"valid": True, "completions": completions, "error": None}


# ---------------------------------------------------------------------------
# Running-config section extraction
# ---------------------------------------------------------------------------

def extract_config_section(full_config: str, section_keyword: str) -> str:
    """Extract a named section from running-config output.

    Works for sections that begin with a keyword line and end when
    indentation returns to column 0 (or a '!' separator).
    """
    lines = full_config.splitlines()
    capturing = False
    captured: list[str] = []

    for line in lines:
        if not capturing:
            if line.strip().lower().startswith(section_keyword.lower()):
                capturing = True
                captured.append(line)
        else:
            if line and not line[0].isspace() and line.strip() != "!":
                break
            captured.append(line)

    return "\n".join(captured)

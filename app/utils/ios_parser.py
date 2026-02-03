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


# ---------------------------------------------------------------------------
# ephone detail parsing  (show ephone {id} or filtered from show ephone)
# ---------------------------------------------------------------------------

# "button 1: cw:1" followed by "  dn 1  number 4002" on next line
_DETAIL_DN_RE = re.compile(r"^\s+dn\s+(\d+)\s+number\s+(\S+)", re.IGNORECASE)
# "speed dial 2:4001 Zoe Bedroom" (show ephone output format)
_SHOW_SPEED_DIAL_RE = re.compile(
    r"speed\s+dial\s+(\d+):(\S+)\s*(.*)", re.IGNORECASE,
)
# "speed-dial 2 4001 label ..." (running-config format, also used in some outputs)
_CFG_SPEED_DIAL_INLINE_RE = re.compile(
    r"speed-dial\s+(\d+)\s+(\S+)(?:\s+label\s+(.+))?", re.IGNORECASE,
)
_DETAIL_TYPE_RE = re.compile(r"phone\s+type\s+is\s+(?:Telecaster\s+)?(\S+)", re.IGNORECASE)


def _extract_ephone_block(full_output: str, ephone_id: int) -> str:
    """Extract a single ephone's block from 'show ephone' output."""
    pattern = re.compile(rf"^ephone-{ephone_id}\b", re.IGNORECASE | re.MULTILINE)
    m = pattern.search(full_output)
    if not m:
        return ""
    start = m.start()
    # Find the next ephone header or end of output
    next_hdr = re.search(r"^ephone-\d+\b", full_output[m.end():], re.MULTILINE)
    if next_hdr:
        end = m.end() + next_hdr.start()
    else:
        # Stop at summary lines like "Max 10, Registered 4"
        summary = re.search(r"^Max\s+\d+,\s+Registered", full_output[m.end():], re.MULTILINE)
        end = (m.end() + summary.start()) if summary else len(full_output)
    return full_output[start:end].rstrip()


def parse_ephone_detail(output: str) -> dict[str, Any]:
    """Parse a single ephone block from 'show ephone' output."""
    result: dict[str, Any] = {}
    if not output.strip():
        return result

    # MAC
    m = _MAC_RE.search(output)
    if m:
        result["mac"] = m.group(1)

    # Type – prefer the "phone type is ..." line, fallback to keepalive line
    m = _DETAIL_TYPE_RE.search(output)
    if m:
        result["type"] = m.group(1)
    elif _TYPE_RE.search(output):
        result["type"] = _TYPE_RE.search(output).group(1)  # type: ignore[union-attr]

    # Status
    m = _REG_RE.search(output)
    if m:
        result["status"] = m.group(1).lower()

    # IP
    m = _IP_RE.search(output)
    if m and m.group(1) != "0.0.0.0":
        result["ip"] = m.group(1)

    # Buttons / DNs – parse "dn N  number XXXX" lines
    buttons: list[dict[str, Any]] = []
    for i, line in enumerate(output.splitlines()):
        dm = _DETAIL_DN_RE.match(line)
        if dm:
            buttons.append({
                "button_number": len(buttons) + 1,
                "dn": int(dm.group(1)),
                "number": dm.group(2),
            })
    result["buttons"] = buttons

    # Speed dials – handle both "speed dial N:NUMBER LABEL" and
    # "speed-dial N NUMBER label LABEL" formats
    speed_dials: list[dict[str, Any]] = []
    for sm in _SHOW_SPEED_DIAL_RE.finditer(output):
        speed_dials.append({
            "position": int(sm.group(1)),
            "number": sm.group(2),
            "label": sm.group(3).strip(),
        })
    if not speed_dials:
        for sm in _CFG_SPEED_DIAL_INLINE_RE.finditer(output):
            speed_dials.append({
                "position": int(sm.group(1)),
                "number": sm.group(2),
                "label": (sm.group(3) or "").strip().strip('"'),
            })
    result["speed_dials"] = speed_dials

    return result


# ---------------------------------------------------------------------------
# ephone-dn summary parsing
# ---------------------------------------------------------------------------

_DN_SUMMARY_LINE_RE = re.compile(
    r"ephone-dn\s+(\d+)\s+number\s+(\S+)", re.IGNORECASE,
)
_DN_STATE_RE = re.compile(r"\b(IDLE|RINGING|IN-USE|BUSY|ALERTING)\b", re.IGNORECASE)
# Config-based DN header: "ephone-dn  1  dual-line" or "ephone-dn 1"
_DN_CFG_HEADER_RE = re.compile(r"^ephone-dn\s+(\d+)", re.IGNORECASE)


def parse_ephone_dn_summary(output: str) -> list[dict[str, Any]]:
    """Parse ephone-dn info from either summary or running-config output.

    Handles both the tabular ``show ephone-dn summary`` format and the
    running-config section format (``show run | section ephone-dn``).
    """
    dns: list[dict[str, Any]] = []
    if not output.strip():
        return dns

    # Try tabular format first
    for line in output.splitlines():
        line_s = line.strip()
        m = _DN_SUMMARY_LINE_RE.match(line_s)
        if not m:
            continue
        entry: dict[str, Any] = {
            "dn_id": int(m.group(1)),
            "number": m.group(2),
        }
        sm = _DN_STATE_RE.search(line_s)
        if sm:
            entry["state"] = sm.group(1).upper()
        em = re.search(r"ephone\s+(\d+)\s*$", line_s, re.IGNORECASE)
        if em:
            entry["ephone_id"] = int(em.group(1))
        dns.append(entry)

    if dns:
        return dns

    # Fallback: parse config-style sections (from show run | section ephone-dn)
    current: dict[str, Any] | None = None
    for line in output.splitlines():
        line_s = line.strip()
        hm = _DN_CFG_HEADER_RE.match(line_s)
        if hm:
            if current:
                dns.append(current)
            current = {"dn_id": int(hm.group(1))}
            continue
        if current is None:
            continue
        nm = re.match(r"number\s+(\S+)", line_s, re.IGNORECASE)
        if nm:
            current["number"] = nm.group(1)
        lm = re.match(r"label\s+(.+)", line_s, re.IGNORECASE)
        if lm:
            current["label"] = lm.group(1).strip()
    if current:
        dns.append(current)

    return dns


def extract_ephone_config_section(full_output: str, ephone_id: int) -> str:
    """Extract one 'ephone N' block from bulk 'show run | section ephone' output."""
    pattern = re.compile(rf"^ephone\s+{ephone_id}\b", re.IGNORECASE | re.MULTILINE)
    m = pattern.search(full_output)
    if not m:
        return ""
    start = m.start()
    # Next top-level section (ephone N, ephone-dn N, ephone-template N, etc.)
    rest = full_output[m.end():]
    nxt = re.search(r"^(?:ephone(?:-dn|-template|-hunt)?)\s+\d", rest, re.MULTILINE)
    end = (m.end() + nxt.start()) if nxt else len(full_output)
    return full_output[start:end].rstrip()


def extract_ephone_dn_config_section(full_output: str, dn_id: int) -> str:
    """Extract one 'ephone-dn N' block from bulk section output."""
    pattern = re.compile(rf"^ephone-dn\s+{dn_id}\b", re.IGNORECASE | re.MULTILINE)
    m = pattern.search(full_output)
    if not m:
        return ""
    start = m.start()
    rest = full_output[m.end():]
    nxt = re.search(r"^(?:ephone(?:-dn|-template|-hunt)?)\s+\d", rest, re.MULTILINE)
    end = (m.end() + nxt.start()) if nxt else len(full_output)
    return full_output[start:end].rstrip()


# ---------------------------------------------------------------------------
# Running-config ephone section parsing
# ---------------------------------------------------------------------------

_CFG_MAC_RE = re.compile(r"^\s*mac-address\s+([\da-fA-F.:-]+)", re.IGNORECASE)
_CFG_TYPE_RE = re.compile(r"^\s*type\s+(\S+)", re.IGNORECASE)
_CFG_BUTTON_RE = re.compile(r"^\s*button\s+(.+)", re.IGNORECASE)
# speed-dial 2 4001 label "Zoe Bedroom"  (label may be quoted)
_CFG_SPEED_DIAL_RE = re.compile(
    r'^\s*speed-dial\s+(\d+)\s+(\S+)(?:\s+label\s+"?([^"]*)"?)?', re.IGNORECASE,
)


def parse_config_ephone(config_text: str) -> dict[str, Any]:
    """Parse a running-config ephone section into a structured dict."""
    result: dict[str, Any] = {}
    if not config_text.strip():
        return result

    lines = config_text.splitlines()
    hm = re.match(r"ephone\s+(\d+)", lines[0].strip(), re.IGNORECASE)
    if hm:
        result["ephone_id"] = int(hm.group(1))

    for line in lines[1:]:
        m = _CFG_MAC_RE.match(line)
        if m:
            result["mac"] = m.group(1)
            continue
        m = _CFG_TYPE_RE.match(line)
        if m:
            result["type"] = m.group(1)
            continue
        m = _CFG_BUTTON_RE.match(line)
        if m:
            result.setdefault("buttons", [])
            for pair in re.finditer(r"(\d+):(\d+)", m.group(1)):
                result["buttons"].append({
                    "button_number": int(pair.group(1)),
                    "dn": int(pair.group(2)),
                })
            continue
        m = _CFG_SPEED_DIAL_RE.match(line)
        if m:
            result.setdefault("speed_dials", [])
            result["speed_dials"].append({
                "position": int(m.group(1)),
                "number": m.group(2),
                "label": (m.group(3) or "").strip(),
            })

    return result


# ---------------------------------------------------------------------------
# Running-config ephone-dn section parsing
# ---------------------------------------------------------------------------

_CFG_DN_NUMBER_RE = re.compile(r"^\s*number\s+(\S+)", re.IGNORECASE)
_CFG_DN_NAME_RE = re.compile(r"^\s*name\s+(.+)", re.IGNORECASE)
_CFG_DN_LABEL_RE = re.compile(r"^\s*label\s+(.+)", re.IGNORECASE)
_CFG_DN_PREFERENCE_RE = re.compile(r"^\s*preference\s+(\d+)", re.IGNORECASE)
_CFG_DN_CALLFWD_RE = re.compile(r"^\s*call-forward\s+(.+)", re.IGNORECASE)


def parse_config_ephone_dn(config_text: str) -> dict[str, Any]:
    """Parse a running-config ephone-dn section into a structured dict."""
    result: dict[str, Any] = {}
    if not config_text.strip():
        return result

    lines = config_text.splitlines()
    hm = re.match(r"ephone-dn\s+(\d+)", lines[0].strip(), re.IGNORECASE)
    if hm:
        result["dn_id"] = int(hm.group(1))

    for line in lines[1:]:
        m = _CFG_DN_NUMBER_RE.match(line)
        if m:
            result["number"] = m.group(1)
            continue
        m = _CFG_DN_NAME_RE.match(line)
        if m:
            result["name"] = m.group(1).strip()
            continue
        m = _CFG_DN_LABEL_RE.match(line)
        if m:
            result["label"] = m.group(1).strip()
            continue
        m = _CFG_DN_PREFERENCE_RE.match(line)
        if m:
            result["preference"] = int(m.group(1))
            continue
        m = _CFG_DN_CALLFWD_RE.match(line)
        if m:
            result.setdefault("call_forward", []).append(m.group(1).strip())

    return result

"""Mock SSH session manager for testing without a real router.

Provides canned IOS outputs so that validate/apply flows can be tested.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from app.models.commands import CommandResult

# ── Canned IOS outputs ────────────────────────────────────────────────────

SHOW_VERSION = """\
Cisco IOS Software, C2900 Software (C2900-UNIVERSALK9-M), Version 15.7(3)M8, RELEASE SOFTWARE (fc1)
Technical Support: http://www.cisco.com/techsupport
Copyright (c) 1986-2021 by Cisco Systems, Inc.

ROM: System Bootstrap, Version 15.0(1r)M16, RELEASE SOFTWARE (fc1)

Router uptime is 14 days, 3 hours, 22 minutes
System returned to ROM by power-on
System image file is "flash:c2900-universalk9-mz.SPA.157-3.M8.bin"

Cisco CISCO2901/K9 (revision 1.0) with 491520K/32768K bytes of memory.
Processor board ID FTX1234A5BC
2 Gigabit Ethernet interfaces
1 terminal line
1 Virtual Private Network (VPN) Module
DRAM configuration is 64 bits wide with parity disabled.
255K bytes of non-volatile configuration memory.
250880K bytes of ATA System CompactFlash 0 (Read/Write)

Configuration register is 0x2102
"""

SHOW_TELEPHONY_SERVICE = """\
CONFIG (Version=4.8(1))
=====================
Cisco Unified Communications Manager Express

For different models different limit is applicable. Verify using show telephony-service all.
ip source-address 10.20.102.11 port 2000
max-ephones 48
max-dn 144
max-conferences 8 gain -6
transfer-system full-consult
create cnf-files version-stamp Jan 01 2023 00:00:00
"""

SHOW_EPHONE_SUMMARY = """\
ephone-1[0] Mac:000D.2932.22A0 TCP socket:[4] activeLine:0 whisperLine:0 REGISTERED in SCCP ver 11/9
mediaActive:0 whisper_mediaActive:0 startMedia:0 offhook:0 ringing:0 reset:0 reset_sent:0 debug:0  primary_dn: 1*
IP:10.20.102.20 * Telecaster 7960  keepalive 8052 max_line 6

ephone-2[1] Mac:64D9.8969.51A0 TCP socket:[3] activeLine:0 whisperLine:0 REGISTERED in SCCP ver 20/17
mediaActive:0 whisper_mediaActive:0 startMedia:0 offhook:0 ringing:0 reset:0 reset_sent:0 debug:0  primary_dn: 2*
IP:10.20.102.21 * 7945  keepalive 8023 max_line 6

ephone-3[2] Mac:1234.5678.9AB2 TCP socket:[-1] activeLine:0 whisperLine:0 UNREGISTERED
mediaActive:0 whisper_mediaActive:0 startMedia:0 offhook:0 ringing:0 reset:0 reset_sent:0 debug:0  primary_dn: 3
IP:0.0.0.0* Unknown 0  keepalive 0
"""

SHOW_RUNNING_CONFIG = """\
Building configuration...

Current configuration : 8192 bytes
!
version 15.7
service timestamps debug datetime msec
service timestamps log datetime msec
no service password-encryption
!
hostname Router
!
telephony-service
 max-ephones 48
 max-dn 144
 ip source-address 10.20.102.11 port 2000
 create cnf-files version-stamp Jan 01 2023 00:00:00
!
ephone-dn 1
 number 1001
 name Phone 1
!
ephone 1
 mac-address 1234.5678.9AB0
 type 7945
 button 1:1
!
end
"""

SHOW_ARCHIVE = "% Archive has not been configured"

CONFIGURE_REPLACE_HELP = """\
  flash:       Configuration file in flash
  ftp:         Configuration file on ftp
  http:        Configuration file on http
  https:       Configuration file on https
  nvram:       Configuration file in nvram
  rcp:         Configuration file on rcp
  scp:         Configuration file on scp
  tftp:        Configuration file on tftp
"""

HELP_MAX_EPHONES = """\
  <1-240>  Maximum number of ephones supported
"""

HELP_INVALID = "% Unrecognized command"

# Full "show ephone" detail output (used by GET /cme/ephone/{id})
SHOW_EPHONE_DETAIL = """\
ephone-1[0] Mac:000D.2932.22A0 TCP socket:[4] activeLine:0 whisperLine:0 REGISTERED in SCCP ver 11/9
IP:10.20.102.20 * 50406 Telecaster 7960  keepalive 8642 max_line 6 available_line 1
button 1: cw:1 ccw:(0 0)
  dn 1  number 4002 CH1   IDLE         CH2   IDLE
speed dial 2:4001 Zoe Bedroom
speed dial 3:4003 Alex Bedroom
Preferred Codec: g711ulaw

ephone-2[1] Mac:64D9.8969.51A0 TCP socket:[3] activeLine:0 whisperLine:0 REGISTERED in SCCP ver 20/17
IP:10.20.102.21 * 52434 7965  keepalive 8610 max_line 6 available_line 1
button 1: cw:1 ccw:(0 0)
  dn 2  number 4001 CH1   IDLE         CH2   IDLE
speed dial 2:4003 Alex Bedroom
Preferred Codec: g711ulaw

Max 10, Registered 2, Unregistered 0, Deceased 0
"""

SHOW_EPHONE_DN_SUMMARY = """\
ephone-dn 1  number 1001  CH1  IDLE         ephone 1
ephone-dn 2  number 1002  CH1  IDLE         ephone 1
ephone-dn 3  number 1003  CH1  IDLE         ephone 2
"""

SHOW_RUN_SECTION_TELEPHONY = """\
telephony-service
 max-ephones 48
 max-dn 144
 ip source-address 10.20.102.11 port 2000
 url services http://10.20.102.1/services
 create cnf-files version-stamp Jan 01 2023 00:00:00
"""

# Bulk "show run | section ephone" output (contains all ephone/ephone-dn sections)
SHOW_RUN_SECTION_EPHONE = """\
 no auto-reg-ephone
 max-ephones 48
ephone-dn  1  dual-line
 number 4002
 label Rack Phone
ephone-dn  2  dual-line
 number 4001
 label Zoe Bedroom
ephone  1
 device-security-mode none
 mac-address 000D.2932.22A0
 speed-dial 2 4001 label "Zoe Bedroom"
 speed-dial 3 4003 label "Alex Bedroom"
 type 7960
 button  1:1
ephone  2
 device-security-mode none
 mac-address 64D9.8969.51A0
 speed-dial 2 4003 label "Alex Bedroom"
 type 7965
 button  1:2
"""

SHOW_RUN_SECTION_EPHONE_DN = """\
ephone-dn  1  dual-line
 number 4002
 label Rack Phone
ephone-dn  2  dual-line
 number 4001
 label Zoe Bedroom
"""


# ── Canned response map ──────────────────────────────────────────────────

_CANNED: dict[str, str] = {
    "show version": SHOW_VERSION,
    "show telephony-service": SHOW_TELEPHONY_SERVICE,
    "show ephone summary": SHOW_EPHONE_SUMMARY,
    "show ephone": SHOW_EPHONE_DETAIL,
    "show ephone-dn summary": SHOW_EPHONE_DN_SUMMARY,
    "show running-config": SHOW_RUNNING_CONFIG,
    "show running-config | include hostname": "hostname Router",
    "show running-config | section telephony-service": SHOW_RUN_SECTION_TELEPHONY,
    "show running-config | section ephone-dn": SHOW_RUN_SECTION_EPHONE_DN,
    "show running-config | section ephone": SHOW_RUN_SECTION_EPHONE,
    "show archive": SHOW_ARCHIVE,
    "configure replace ?": CONFIGURE_REPLACE_HELP,
    "show flash: | include bytes": "250880K bytes of ATA System CompactFlash 0 (Read/Write)",
    "terminal length 0": "",
    "terminal width 0": "",
}


# ── Mock manager ─────────────────────────────────────────────────────────


class MockSSHManager:
    """Drop-in replacement for SSHSessionManager using canned outputs."""

    def __init__(self) -> None:
        self.is_connected = True
        self.sent_commands: list[str] = []
        self.sent_configs: list[list[str]] = []
        self._extra: dict[str, str] = {}

    def add_response(self, command: str, output: str) -> None:
        """Add or override a canned response."""
        self._extra[command] = output

    def _lookup(self, command: str) -> str:
        if command in self._extra:
            return self._extra[command]
        if command in _CANNED:
            return _CANNED[command]
        # Partial match
        for key, val in _CANNED.items():
            if command.lower().startswith(key.lower()):
                return val
        return ""

    async def send_show(self, command: str) -> CommandResult:
        self.sent_commands.append(command)
        output = self._lookup(command)
        return CommandResult(
            command=command,
            output=output,
            failed=False,
            elapsed_time=0.01,
        )

    async def send_configs(
        self,
        configs: list[str],
        *,
        stop_on_failed: bool = False,
    ) -> list[CommandResult]:
        self.sent_configs.append(configs)
        results: list[CommandResult] = []
        for cmd in configs:
            output = self._lookup(cmd)
            failed = "% Invalid" in output
            results.append(
                CommandResult(
                    command=cmd,
                    output=output,
                    failed=failed,
                    elapsed_time=0.01,
                ),
            )
            if failed and stop_on_failed:
                break
        return results

    async def probe_help(self, text: str, wait: float = 0.0) -> str:
        self.sent_commands.append(f"PROBE:{text}")
        # If text ends with ?, look up the base command
        base = text.rstrip("? ").strip()
        if base in self._extra:
            return self._extra[base]
        if "max-ephones" in base:
            return HELP_MAX_EPHONES
        if "blahblah" in base or "invalid" in base.lower():
            return HELP_INVALID
        return f"  <cr>\n"

    async def close(self) -> None:
        self.is_connected = False

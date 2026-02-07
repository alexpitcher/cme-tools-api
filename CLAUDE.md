# CME Tools API

FastAPI service for managing Cisco Unified CME on a Cisco 2901 router running IOS 15.7(3)M8.

## Quick Start

```bash
# Run with Docker (pulls from GHCR)
docker compose up -d

# Run tests
python -m pytest -v

# Run locally
uvicorn app.main:app --reload
```

The API runs on `http://localhost:8000`. Swagger docs at `/docs`.

## Environment

Config is in `.env` (not committed). Required vars:

| Variable | Description | Example |
|---|---|---|
| `CME_ROUTER_HOST` | Router IP | `10.20.102.11` |
| `CME_ROUTER_PORT` | SSH port | `22` |
| `CME_ROUTER_USERNAME` | SSH user | `admin` |
| `CME_ROUTER_PASSWORD` | SSH password | (secret) |
| `CME_ROUTER_NAME` | Router hostname | `a14-con` |
| `CME_API_KEY` | API key (empty = no auth) | |
| `CME_GIT_REMOTE_URL` | Git backup remote | |
| `CME_GIT_BRANCH` | Backup branch | `main` |
| `CME_GIT_BACKUP_FOLDER` | Backup subfolder | `a14-con` |

## Architecture

```
app/
  main.py              # FastAPI app, router registration
  auth.py              # API key middleware
  routers/
    cme.py             # CME read + write endpoints (ephones, DNs, speed-dials, URLs)
    config.py          # PLAN -> VALIDATE -> APPLY workflow
    show.py            # Generic show command proxy
    backup.py          # Backup/restore endpoints
    health.py          # Health checks
    capabilities.py    # IOS feature detection
  models/
    cme.py             # CME Pydantic models (ephones, speed-dials, intents)
    plan.py            # ConfigPlan, ValidationResult, ApplyResult
    commands.py        # Command models
    responses.py       # Generic response models
  services/
    ssh_manager.py     # Scrapli SSH session management (paramiko transport)
    plan_service.py    # In-memory plan store
    intent_service.py  # Intent-to-ConfigPlan mapping
    command_filter.py  # Allowlist/denylist for IOS commands
    validate.py        # Plan validation
    apply.py           # Plan application (backup -> apply -> verify -> backup)
    backup.py          # Git-backed config backup
    restore.py         # Config restore from git
    capabilities.py    # IOS feature detection
  utils/
    ios_parser.py      # Regex parsers for IOS show command output
    logging.py         # Structured logging
tests/
    conftest.py        # Fixtures, mock SSH patching
    mock_ssh.py        # Canned IOS command outputs
    test_cme.py        # CME endpoint + parser tests
    test_*.py          # Other test modules
```

## Core Workflow: PLAN -> VALIDATE -> APPLY

All config changes follow this three-step pattern. Nothing is applied to the router without an explicit apply call.

### 1. Create a Plan

Plans can be created via intent shortcuts or raw plan bodies.

**Using intents (recommended for common operations):**
```bash
# Via CME shortcut endpoints
curl -X POST http://localhost:8000/cme/speed-dial \
  -H "Content-Type: application/json" \
  -d '{"ephone_id": 3, "position": 4, "number": "4004", "label": "Ollie"}'

# Via generic intent payload
curl -X POST http://localhost:8000/config/plan \
  -H "Content-Type: application/json" \
  -d '{"intent": "set_speed_dial", "params": {"ephone_id": 3, "position": 4, "number": "4004", "label": "Ollie"}}'
```

**Using raw plan body (for anything not covered by intents):**
```bash
curl -X POST http://localhost:8000/config/plan \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Restart ephone 3",
    "mode_path": ["configure terminal", "ephone 3"],
    "commands": ["restart"],
    "verification": ["show ephone"],
    "affected_entities": ["ephone 3"],
    "risk_level": "low"
  }'
```

All plan creation calls return a `ConfigPlan` with a `plan_id`.

### 2. Validate (optional but recommended)
```bash
curl -X POST http://localhost:8000/config/validate \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "<plan_id>"}'
```

### 3. Apply
```bash
curl -X POST http://localhost:8000/config/apply \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "<plan_id>"}'
```

Apply does: pre-backup -> enter mode_path -> run commands -> exit -> run verification -> post-backup. Returns `ApplyResult` with `success`, `executed_commands`, backup SHAs, and verification output.

## API Endpoints

### Health
| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Liveness probe |
| GET | `/router/health` | Yes | Router reachability + CME status |

### CME Read
| Method | Path | Description |
|--------|------|-------------|
| GET | `/cme/ephones` | All ephones (parsed summary) |
| GET | `/cme/ephone/{id}` | Single ephone detail (buttons, speed-dials, status) |
| GET | `/cme/ephone-dns` | All ephone-DNs |
| GET | `/cme/telephony-service` | Telephony-service config (parsed) |
| GET | `/cme/config/section?anchor=X` | Raw running-config section by keyword |
| GET | `/cme/config/ephone/{id}` | Ephone running-config + parsed dict |
| GET | `/cme/config/ephone-dn/{id}` | Ephone-dn running-config + parsed dict |

### CME Write (plan generation only, no direct changes)
| Method | Path | Body | Description |
|--------|------|------|-------------|
| POST | `/cme/speed-dial` | `{ephone_id, position, number, label}` | Plan to set speed-dial |
| DELETE | `/cme/speed-dial` | `{ephone_id, position}` | Plan to remove speed-dial |
| POST | `/cme/telephony/url` | `{url_type, url, idle_timeout?}` | Plan to set URL |
| DELETE | `/cme/telephony/url` | `{url_type}` | Plan to clear URL |

`url_type` is one of: `services`, `directories`, `idle`.

### Config Workflow
| Method | Path | Description |
|--------|------|-------------|
| POST | `/config/plan` | Create plan (intent payload or raw body) |
| GET | `/config/plan/{plan_id}` | Get a plan |
| GET | `/config/plans` | List all plans |
| POST | `/config/validate` | Validate a plan (`{plan_id}`) |
| POST | `/config/apply` | Apply a plan (`{plan_id}`) |

### Show / Backup
| Method | Path | Description |
|--------|------|-------------|
| POST | `/show` | Run an allowlisted show command |
| POST | `/backup` | Take config backup |
| POST | `/restore` | Restore from git ref |
| GET | `/backups` | List recent backups |
| GET | `/capabilities` | Detect IOS features |

## Available Intents

| Intent | Params | Description |
|--------|--------|-------------|
| `set_speed_dial` | `ephone_id, position, number, label` | Add/update speed-dial |
| `delete_speed_dial` | `ephone_id, position` | Remove speed-dial |
| `set_url_services` | `url` | Set telephony url services |
| `set_url_directories` | `url` | Set telephony url directories |
| `set_url_idle` | `url, idle_timeout?` | Set telephony url idle |
| `clear_url_services` | (none) | Remove url services |
| `clear_url_directories` | (none) | Remove url directories |
| `clear_url_idle` | (none) | Remove url idle |

## IOS Quirks (Cisco 2901 / IOS 15.7)

These are critical to understand when extending the codebase:

- **`show ephone {id}` does not exist.** Use `show ephone` (all phones) and filter by ID with `_extract_ephone_block()` in `ios_parser.py`.
- **`show ephone-dn summary` returns a voice port table, not DN info.** The code falls back to parsing `show running-config | section ephone-dn`.
- **`show run | section ^ephone 1` returns empty.** IOS regex anchoring in pipe filters doesn't work reliably. Use `show run | section ephone` (bulk) and filter in Python with `extract_ephone_config_section()` / `extract_ephone_dn_config_section()`.
- **Speed-dial format differs between show and config:**
  - Show output: `speed dial 2:4001 Zoe Bedroom` (space, colon, no "label" keyword)
  - Running-config: `speed-dial 2 4001 label "Zoe Bedroom"` (hyphen, spaces, quoted label)
  - The parser handles both via `_SHOW_SPEED_DIAL_RE` and `_CFG_SPEED_DIAL_RE`.
- **7975 phones use `ephone-template` for button-layout mapping.** Speed-dials only appear on the phone if the template has `button-layout N speed-dial` slots for them. Check `show running-config | section ephone-template` if speed-dials don't show on the phone.
- **Ephone restart:** Use raw plan with `mode_path: ["configure terminal", "ephone {id}"]`, `commands: ["restart"]`. The phone will re-register after a few seconds.
- **`show ephone` verification in intents uses `show ephone {id}` which fails.** For post-apply verification, prefer `show ephone` (full) or check via the API endpoint instead.

## Ephones on the Router

| Ephone | MAC | Type | DN | Extension | Name |
|--------|-----|------|----|-----------|------|
| 1 | 000D.2932.22A0 | 7960 | 1 | 4002 | Rack Phone |
| 2 | 64D9.8969.51A0 | 7965 | 2 | 4001 | Zoe Bedroom |
| 3 | 001E.F7C2.214E | 7975 | 3 | 4003 | Alex Bedroom |
| 4 | 58AC.788C.DE96 | 7925 | 3 | 4003 | (shared DN, often unregistered) |
| 5 | 9CAF.CA84.6FA0 | 7945 | 4 | 4004 | Ollie |

Ephone 3 (7975) uses `ephone-template 10` with button-layout slots for line (1), speed-dials (2-6), and URL buttons (7-8).

## Testing

```bash
# All tests
python -m pytest -v

# Just CME tests
python -m pytest tests/test_cme.py -v

# With coverage
python -m pytest --cov=app --cov-report=term-missing
```

Tests use mock SSH (`tests/mock_ssh.py`) with canned IOS outputs. The canned outputs match real Cisco 2901 output format. When adding new commands, add canned output to `mock_ssh.py` and patch the SSH manager in `conftest.py`.

## Docker

```bash
# Pull and run from GHCR (built by CI on every push to main)
docker compose up -d

# Check logs
docker compose logs -f

# Stop
docker compose down
```

Image: `ghcr.io/alexpitcher/cme-tools-api:latest` (linux/amd64, runs under emulation on Apple Silicon).

## Adding New Features

1. **New parser:** Add to `app/utils/ios_parser.py`. Test with canned output in `tests/mock_ssh.py`.
2. **New endpoint:** Add to the appropriate router in `app/routers/`. CME-specific endpoints go in `cme.py`.
3. **New intent:** Add enum value to `IntentName` in `app/models/cme.py`, add builder function and dispatch entry in `app/services/intent_service.py`.
4. **New IOS command:** Ensure it matches the allowlist in `app/services/command_filter.py`. Add to denylist if it should be blocked.
5. **Always test against real router.** IOS output format varies by version and platform. The mock data should be updated to match real output.

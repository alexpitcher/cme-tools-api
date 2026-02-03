# CME Tools API

A production-ready REST API for managing Cisco Unified CME configuration on a Cisco 2901 (IOS 15.7). Designed as a backend for an AI agent that follows a **PLAN -> VALIDATE -> APPLY** workflow with automatic backups and rollback.

## Features

- **Safe command execution** with allowlist/denylist enforcement
- **Plan/Validate/Apply workflow** for structured configuration changes
- **Automatic git backups** before and after every change (pushed to Gitea)
- **Rollback support** with capability detection (`configure replace`, line-by-line)
- **SSH session reuse** with idle timeout and concurrency locking
- **Router health checks** (telephony-service, registered phones)
- **API key authentication**
- **Structured logging**

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/alexpitcher/cme-tools-api.git
cd cme-tools-api
cp .env.example .env
# Edit .env with your router credentials and API key
```

### 2. Run with Docker Compose

```bash
docker compose up -d
```

Or build locally:

```bash
docker compose up -d --build
```

### 3. Run without Docker

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CME_ROUTER_HOST` | yes | `10.20.102.11` | Router SSH host |
| `CME_ROUTER_PORT` | no | `22` | Router SSH port |
| `CME_ROUTER_USERNAME` | yes | `admin` | SSH username |
| `CME_ROUTER_PASSWORD` | yes | *(empty)* | SSH password |
| `CME_ROUTER_SSH_KEY_PATH` | no | *(empty)* | Path to SSH private key |
| `CME_ROUTER_ENABLE_SECRET` | no | *(empty)* | Enable secret (if needed) |
| `CME_ROUTER_NAME` | no | `a14-con` | Router identifier for backups |
| `CME_SESSION_IDLE_TIMEOUT_SECONDS` | no | `30` | SSH idle timeout |
| `CME_API_KEY` | recommended | *(empty)* | API key for X-API-Key header |
| `CME_GIT_REMOTE_URL` | yes | *(see .env.example)* | Gitea backup remote |
| `CME_GIT_BRANCH` | no | `main` | Git branch for backups |
| `CME_GIT_BACKUP_FOLDER` | no | `a14-con` | Folder inside the backup repo |
| `CME_GIT_HTTP_USERNAME` | no | *(empty)* | Git HTTPS auth username |
| `CME_GIT_HTTP_TOKEN` | no | *(empty)* | Git HTTPS auth token |
| `CME_GIT_AUTHOR_NAME` | no | `CME Tools Bot` | Git commit author name |
| `CME_GIT_AUTHOR_EMAIL` | no | `cme-tools-bot@local` | Git commit author email |
| `CME_MAINTENANCE_MODE` | no | `false` | Widens command allowlist |

## API Endpoints

### Health

```bash
# Service health (no auth)
curl http://localhost:8000/health

# Router health
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/router/health
```

### Show Commands

```bash
# Run a show command
curl -X POST http://localhost:8000/show \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"command": "show telephony-service"}'
```

### CME Read Endpoints

```bash
# List all ephones (parsed summary)
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/cme/ephones

# Get detailed ephone info (buttons, speed-dials, status)
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/cme/ephone/1

# List all ephone-dns
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/cme/ephone-dns

# Get telephony-service config
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/cme/telephony-service

# Get a running-config section
curl -H "X-API-Key: YOUR_KEY" "http://localhost:8000/cme/config/section?anchor=telephony-service"

# Get ephone running-config
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/cme/config/ephone/1

# Get ephone-dn running-config
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/cme/config/ephone-dn/1
```

### CME Write Endpoints (Plan Generation)

These endpoints generate `ConfigPlan` objects -- they do **not** apply changes directly.
Use `/config/validate` and `/config/apply` with the returned `plan_id` to execute.

```bash
# Set a speed-dial on an ephone
curl -X POST http://localhost:8000/cme/speed-dial \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"ephone_id": 1, "position": 1, "label": "IT", "number": "5001"}'

# Remove a speed-dial
curl -X DELETE http://localhost:8000/cme/speed-dial \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"ephone_id": 1, "position": 1}'

# Set a telephony URL (services, directories, or idle)
curl -X POST http://localhost:8000/cme/telephony/url \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url_type": "idle", "url": "http://10.0.0.1/idle", "idle_timeout": 60}'

# Clear a telephony URL
curl -X DELETE http://localhost:8000/cme/telephony/url \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url_type": "services"}'

# Create a plan via intent (alternative to dedicated endpoints)
curl -X POST http://localhost:8000/config/plan \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"intent": "set_speed_dial", "params": {"ephone_id": 1, "position": 1, "label": "IT", "number": "5001"}}'
```

**Supported intents:** `set_speed_dial`, `delete_speed_dial`, `set_url_services`,
`set_url_directories`, `set_url_idle`, `clear_url_services`, `clear_url_directories`,
`clear_url_idle`

### Plan / Validate / Apply

```bash
# 1. Create a plan
curl -X POST http://localhost:8000/config/plan \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Add ephone 5",
    "mode_path": ["configure terminal", "ephone 5"],
    "commands": ["mac-address 1111.2222.3333", "type 7945", "button 1:5"],
    "verification": ["show ephone 5"],
    "affected_entities": ["ephone 5"],
    "risk_level": "low"
  }'

# 2. Validate the plan (returns per-command status)
curl -X POST http://localhost:8000/config/validate \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "PLAN_ID_FROM_STEP_1"}'

# 3. Apply the plan (backup -> apply -> verify -> backup)
curl -X POST http://localhost:8000/config/apply \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "PLAN_ID_FROM_STEP_1"}'
```

### Backups

```bash
# Take a backup
curl -X POST http://localhost:8000/backup \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"reason": "before-maintenance"}'

# List backups
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/backups

# Restore from backup
curl -X POST http://localhost:8000/restore \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"ref": "COMMIT_SHA"}'
```

### Capabilities

```bash
curl -H "X-API-Key: YOUR_KEY" http://localhost:8000/capabilities
```

## Command Safety

By default, only CME-related and read-only commands are allowed:

**Allowed (always):**
- All `show` commands
- `telephony-service`, `ephone`, `ephone-dn`, and sub-commands
- `dial-peer voice`, `voice register`, `voice translation-*`
- `ping`, `traceroute`, `write memory`

**Denied (always, even in maintenance mode):**
- `reload`, `erase`, `format`, `write erase`, `delete`
- `crypto key zeroize`, `username`, `enable secret/password`
- `debug all`, `boot system`, `config-register`

**Maintenance mode** (`CME_MAINTENANCE_MODE=true`) additionally allows:
- `interface`, `ip route`, `router`, `aaa`, `access-list`
- `crypto` (except `key zeroize`), `line`, `ntp`, `logging`

## Running Tests

```bash
pip install -r requirements.txt
pytest -v
```

## GHCR Publishing

The GitHub Actions workflow automatically pushes to GHCR on:
- **Push to main**: tags `latest` and `sha-<short>`
- **Tags `v*`**: tags with the version (e.g. `v1.0.0`)

### Making the GHCR package public

After the first push, the package defaults to private. To make it public:

1. Go to https://github.com/alexpitcher/cme-tools-api/packages
2. Click the package name
3. Click **Package settings**
4. Under **Danger Zone**, click **Change visibility** -> **Public**

## Optional: Bootstrap `configure replace`

For the safest rollback, enable `configure replace` on the router:

```
configure terminal
 archive
  path flash:archive
  maximum 5
  write-memory
 end
write memory
```

This allows the `/restore` endpoint to use `configure replace` instead of
line-by-line replay. The `/capabilities` endpoint detects whether this is
available.

## License

MIT

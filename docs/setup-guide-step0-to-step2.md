# Email Platform — Setup Guide (Step 0 to Step 2)

**Project:** Self-hosted Email Sending Platform + CRM  
**Date:** 2026-06-23  
**Environment:** Windows 11 Pro, WSL2 + Ubuntu, Docker Desktop  

---

## Table of Contents

1. [Pre-Setup: Environment Configuration (.env)](#1-pre-setup-environment-configuration)
2. [Step 0: Prerequisites (Windows)](#2-step-0-prerequisites-windows)
3. [Step 1: Project Skeleton](#3-step-1-project-skeleton)
4. [Step 2: Local Stack via Docker Compose](#4-step-2-local-stack-via-docker-compose)
5. [Postal UI Setup](#5-postal-ui-setup)
6. [Python Virtual Environment Setup](#6-python-virtual-environment-setup)
7. [Errors Encountered & Solutions](#7-errors-encountered--solutions)
8. [Tools & Commands Reference](#8-tools--commands-reference)
9. [Service Access Guide](#9-service-access-guide)
10. [Final Status & Verification](#10-final-status--verification)

---

## 1. Pre-Setup: Environment Configuration

### Why do this first?

Before installing any software, we created `.env` configuration files so that when moving from localhost to a live server, only environment values change — no code modifications needed.

### Files created

| File | Purpose | Committed to Git? |
|------|---------|-------------------|
| `.env.example` | Template with every config variable + comments explaining localhost vs production values | Yes |
| `.env` | Actual local values — working config | **No** (git-ignored) |
| `.gitignore` | Protects `.env`, `__pycache__/`, logs, IDE folders from being committed | Yes |

### Configuration categories in .env

| Category | Key Variables | What they control |
|----------|--------------|-------------------|
| General | `APP_ENV`, `APP_DEBUG`, `APP_SECRET_KEY` | App mode, debug toggle, encryption key |
| FastAPI | `API_HOST`, `API_PORT`, `API_WORKERS` | Web server binding and concurrency |
| MongoDB | `MONGO_URI`, `MONGO_DB` | Application database connection |
| Redis | `REDIS_URI` | Queue broker + counter store |
| Celery | `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Background task queue config |
| Postal | `POSTAL_API_URL`, `POSTAL_API_KEY` | Mail engine connection |
| Postal Internals | `POSTAL_MARIADB_*`, `POSTAL_RABBITMQ_*` | Postal's own database + broker |
| Mailpit | `MAILPIT_SMTP_PORT`, `MAILPIT_UI_PORT` | Local mail catcher (dev only) |
| Streams | `STREAM_OPTIN_DOMAIN`, `STREAM_ENGAGED_DOMAIN`, `STREAM_COLD_DOMAIN` | Per-stream subdomain routing |
| Warmup | `WARMUP_*_DAILY_CAP`, `WARMUP_RAMP_PERCENT` | IP warmup schedule |
| Suppression | `SUPPRESSION_HARD_BOUNCE`, etc. | Auto-suppress toggles |
| Claude API | `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` | Intelligence layer |
| CRM/Team | `JWT_SECRET_KEY`, `JWT_EXPIRY_HOURS` | Authentication |
| Logging | `LOG_LEVEL`, `LOG_FORMAT` | Log verbosity |

### What changes when moving to production

| Variable | Localhost | Production |
|----------|-----------|------------|
| `APP_ENV` | `localhost` | `production` |
| `APP_DEBUG` | `true` | `false` |
| `APP_SECRET_KEY` | `local-dev-secret-key...` | Random 64-char string |
| `MONGO_URI` | `mongodb://localhost:27017/email_platform` | `mongodb://user:pass@server:27017/email_platform` |
| `POSTAL_API_URL` | `http://localhost:5000` | `https://postal.yourdomain.com` |
| `STREAM_OPTIN_DOMAIN` | `mail.localhost` | `mail.yourdomain.com` |
| `LOG_LEVEL` | `DEBUG` | `INFO` |
| `API_WORKERS` | `2` | `4-8` |
| Mailpit vars | Present | Removed entirely |

---

## 2. Step 0: Prerequisites (Windows)

### 2.1 Check existing software

**Commands used:**
```powershell
# In PowerShell
wsl --version                    # Check WSL
docker --version                 # Check Docker
code --version                   # Check VS Code
```

**Tool:** `PowerShell`

**Initial state found:**
| Software | Status |
|----------|--------|
| WSL2 | Not installed |
| Docker Desktop | Not installed |
| VS Code | Already installed (v1.125.1) |

### 2.2 Verify hardware virtualization

**Command:**
```powershell
Get-ComputerInfo | Select-Object HyperVisorPresent
```
**Result:** `True` — virtualization is enabled (required for WSL2)

**Manual check (if False):** Enable Intel VT-x / AMD-V in BIOS settings.

### 2.3 Install WSL2

**Requires:** Administrator PowerShell

**Command:**
```powershell
# Open PowerShell as Admin (right-click Start → Terminal (Admin))
wsl --install
```

**What it does:** Enables the WSL2 engine on Windows. May require a reboot.

**Verification:**
```powershell
wsl --list --verbose
```

**Query raised:** After `wsl --install`, running `wsl --list --verbose` showed "no installed distributions" — the WSL2 engine was installed but no Linux distro was added.

### 2.4 Install Ubuntu on WSL2

**Command (Admin PowerShell):**
```powershell
wsl --install -d Ubuntu
```

**Manual configuration required:** Ubuntu asks you to create a Linux username and password on first launch. Pick something simple you'll remember — this is your `sudo` password.

**Verification:**
```powershell
wsl --list --verbose
```
**Expected output:**
```
  NAME      STATE     VERSION
* Ubuntu    Running   2
```

### 2.5 Install Docker Desktop

**Command (via winget — no browser needed):**
```powershell
winget install Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
```

**Alternative:** Download manually from https://docs.docker.com/desktop/setup/install/windows-install/

**Manual configuration required:**
1. Restart PC after install (PATH update)
2. Launch Docker Desktop from Start menu
3. Accept terms of service
4. Go to **Settings → Resources → WSL Integration** → Toggle **Ubuntu** to **ON** → Apply & restart

**Error found:** After install, `docker --version` returned "not recognized" — PATH wasn't updated yet.  
**Solution:** Restart PC or log out/in.

**Error found:** `docker --version` worked in PowerShell but not inside WSL.  
**Solution:** Enable WSL Integration in Docker Desktop Settings → Resources → WSL Integration → toggle Ubuntu ON.

**Verification:**
```powershell
# PowerShell
docker --version

# Inside WSL
wsl -- bash -c "docker --version"
```

### 2.6 Install VS Code WSL Extension

**Command:**
```powershell
code --install-extension ms-vscode-remote.remote-wsl
```
**Result:** Extension `ms-vscode-remote.remote-wsl` v0.104.3 installed.

### 2.7 Verify Python in WSL

**Command:**
```powershell
wsl -- bash -c "python3 --version"
```
**Result:** Python 3.14.4 (comes pre-installed with Ubuntu)

### Step 0 — Final verification checklist

| Check | Command | Result |
|-------|---------|--------|
| WSL2 + Ubuntu | `wsl --list --verbose` | Ubuntu, Running, Version 2 |
| Python3 in WSL | `wsl -- bash -c "python3 --version"` | Python 3.14.4 |
| Docker (PowerShell) | `docker --version` | Docker 29.5.3 |
| Docker (WSL) | `wsl -- bash -c "docker --version"` | Docker 29.5.3 |
| VS Code | `code --version` | 1.125.1 |
| VS Code WSL ext | `code --list-extensions` | ms-vscode-remote.remote-wsl |

---

## 3. Step 1: Project Skeleton

### Directory structure created

```
D:\OVH\
├── .env                          # local config (git-ignored)
├── .env.example                  # committable template
├── .gitignore                    # protects secrets from git
├── docker-compose.yml            # brings up entire local stack
├── requirements.txt              # Python dependencies
├── email-platform-blueprint.md   # architecture reference
├── api/
│   ├── __init__.py
│   └── main.py                   # FastAPI app + /health endpoint
├── worker/
│   ├── __init__.py
│   ├── celery_app.py             # Celery app definition
│   └── tasks.py                  # send_to_recipient task (stub)
├── models/
│   └── __init__.py               # MongoDB schemas (Step 3)
├── core/
│   ├── __init__.py
│   └── config.py                 # Settings loaded from .env via Pydantic
└── postal/
    └── postal.yml                # Postal engine config
```

**Command to create directories:**
```powershell
New-Item -ItemType Directory -Force -Path "d:\OVH\api", "d:\OVH\worker", "d:\OVH\models", "d:\OVH\core", "d:\OVH\postal"
```

**Git initialized:**
```powershell
git init d:\OVH
```

### Key files explained

| File | Role |
|------|------|
| `docker-compose.yml` | Defines 8 services: MongoDB, Redis, Mailpit, MariaDB, RabbitMQ, Postal (web + worker + smtp) |
| `core/config.py` | Single `Settings` class using Pydantic — reads `.env`, used everywhere in the app |
| `api/main.py` | FastAPI skeleton with `/health` endpoint |
| `worker/celery_app.py` | Celery app wired to Redis broker |
| `worker/tasks.py` | `send_to_recipient` task stub (implemented in Step 5) |
| `postal/postal.yml` | Postal config: connects to MariaDB + RabbitMQ, relays outbound to Mailpit |
| `requirements.txt` | Python deps: fastapi, uvicorn, pydantic, motor, redis, celery, httpx |

---

## 4. Step 2: Local Stack via Docker Compose

### 4.1 Start the stack

**Command:**
```powershell
docker compose -f d:\OVH\docker-compose.yml up -d
```

**What it does:** Pulls all Docker images (first time takes several minutes) and starts every service in detached (background) mode.

**Tool:** `docker compose`

### 4.2 Errors encountered during startup

#### Error 1: Postal image tag not found

**Error:**
```
Error response from daemon: failed to resolve reference "ghcr.io/postalserver/postal:3": not found
```

**Cause:** Tag `:3` does not exist on the GitHub Container Registry.

**Solution:** Changed image tag to `:latest` in docker-compose.yml.
```yaml
# Before (broken)
image: ghcr.io/postalserver/postal:3

# After (fixed)
image: ghcr.io/postalserver/postal:latest
```

**Verification command:**
```powershell
docker manifest inspect ghcr.io/postalserver/postal:latest
```

#### Error 2: postal-cron container kept restarting

**Error:** Container `ep-postal-cron` status: `Restarting (0)`

**Diagnosis command:**
```powershell
docker logs ep-postal-cron --tail 20
```

**Cause:** `postal cron` is not a valid Postal command. Valid commands are: `web-server`, `smtp-server`, `worker`, `initialize`, `make-user`, `version`.

**Solution:** Removed the `postal-cron` service entirely from `docker-compose.yml`.

```powershell
# Remove the stuck container
docker stop ep-postal-cron
docker rm ep-postal-cron
```

#### Error 3: Postal web UI unreachable (connection closed)

**Diagnosis:**
```powershell
# Test from host
Invoke-WebRequest -Uri http://localhost:5000 -UseBasicParsing -TimeoutSec 5
# Result: "The underlying connection was closed"

# Check what Postal is listening on
docker logs ep-postal-web --tail 5
# Result: "Listening on http://127.0.0.1:5000"
```

**Cause:** Puma (Postal's web server) was binding to `127.0.0.1` (loopback) inside the container. Port mapping only works if the process listens on `0.0.0.0`.

**Investigation — finding the correct env var:**
```powershell
docker exec ep-postal-web cat /opt/postal/app/config/puma.rb
```
Revealed: `bind_address = ENV.fetch("BIND_ADDRESS", ...)`

**Solution:** Added `BIND_ADDRESS: 0.0.0.0` to the postal service in docker-compose.yml:
```yaml
postal:
  environment:
    BIND_ADDRESS: 0.0.0.0
```

**Verification:** Logs now show `Listening on http://0.0.0.0:5000`

#### Error 4: Postal returning 403 Forbidden

**Diagnosis:**
```powershell
docker logs ep-postal-web --tail 15
# Showed: GET / HTTP/1.1" 403
```

**Cause:** Postal checks the HTTP `Host` header against its configured hostname. We had `web.host: postal.localhost` but were accessing via `localhost:5000`.

**Investigation — finding correct config format:**
```powershell
# Check Postal's config schema
docker exec ep-postal-web grep -A3 'web_hostname' /opt/postal/app/lib/postal/config_schema.rb

# Check example config
docker exec ep-postal-web cat /opt/postal/app/config/examples/development.yml
```

**Root cause:** The v2 config format uses `postal.web_hostname`, NOT `web.host`. Our initial config used the wrong key.

**Solution:** Rewrote `postal.yml` to correct v2 format:
```yaml
# Before (wrong structure)
web:
  host: postal.localhost

# After (correct v2 structure)
postal:
  web_hostname: localhost
  web_protocol: http
  smtp_hostname: postal.localhost
```

**Verification:**
```powershell
docker compose -f d:\OVH\docker-compose.yml restart postal postal-worker postal-smtp
Invoke-WebRequest -Uri http://localhost:5000 -UseBasicParsing -TimeoutSec 5
# Result: HTTP 200 — OK!
```

### 4.3 Initialize Postal database

**Command:**
```powershell
docker compose -f d:\OVH\docker-compose.yml run --rm postal postal initialize
```

**What it does:** Creates Postal's database schema in MariaDB. Must be run before Postal can function.

### 4.4 Create Postal admin user

**Command (interactive — run in terminal):**
```powershell
docker compose -f d:\OVH\docker-compose.yml run --rm postal postal make-user
```

**Manual input required:**
```
E-Mail Address      : admin@localhost
First Name          : Admin
Last Name           : (press Enter)
Initial Password    : postal-admin-123
```

**Note:** This command is interactive and requires keyboard input. It cannot be easily automated from a script.

### 4.5 Verify all services

**Check container statuses:**
```powershell
docker compose -f d:\OVH\docker-compose.yml ps
```

**Individual service checks:**
```powershell
# Redis
docker exec ep-redis redis-cli ping
# Expected: PONG

# MongoDB
docker exec ep-mongodb mongosh --quiet --eval "db.runCommand({ping: 1})"
# Expected: { ok: 1 }

# MariaDB (Postal's DB)
docker exec ep-mariadb mariadb -uroot -ppostal_root_pass -e "SHOW DATABASES;"
# Expected: 'postal' in the list

# Web UIs — open in browser
# Mailpit:  http://localhost:8025
# Postal:   http://localhost:5000
# RabbitMQ: http://localhost:15672
```

### 4.6 Useful Docker commands

```powershell
# View logs for any container
docker logs ep-postal-web --tail 30

# Restart a specific service
docker compose -f d:\OVH\docker-compose.yml restart postal

# Stop everything
docker compose -f d:\OVH\docker-compose.yml down

# Stop everything AND delete all data (fresh start)
docker compose -f d:\OVH\docker-compose.yml down -v

# Open a shell inside a container
docker exec -it ep-mongodb mongosh email_platform
docker exec -it ep-redis redis-cli
```

---

## 5. Postal UI Setup

### Manual steps in browser

1. **Open** http://localhost:5000
2. **Login:** `admin@localhost` / `postal-admin-123`
3. **Create Organization:**
   - Click "Create the first organization"
   - Name: `DevOrg`
4. **Create Mail Server:**
   - Inside org, click "Add a new mail server"
   - Name: `DevServer`
5. **Create API Credential:**
   - Inside mail server → Credentials → Add new credential
   - Type: **API**
   - Name: `DevServer`
   - Hold: **Unchecked** (let messages flow through)
   - Click Create
   - Copy the generated API key
6. **Update .env:**
   ```
   POSTAL_API_KEY=j1mUFF9Q8nm2mpEHg6DnqhD7
   ```

---

## 6. Python Virtual Environment Setup

### WSL path mapping

Windows `D:\OVH` maps to WSL `/mnt/d/OVH`.

### Steps to set up

**Open WSL and navigate:**
```bash
wsl
cd /mnt/d/OVH
```

#### Error: DNS resolution failure in WSL

**Error:**
```
Temporary failure resolving 'archive.ubuntu.com'
```

**Solution:**
```bash
echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
```

#### Error: python3-venv not available

**Error:**
```
The virtual environment was not created successfully because ensurepip is not available.
```

**Solution:**
```bash
sudo apt update
sudo apt install python3-venv -y
```

**Note:** Needed `sudo` — requires the Linux password set during Ubuntu first-launch setup.

#### Error: Python 3.14 too new for pydantic-core

**Error:**
```
error: the configured Python interpreter version (3.14) is newer than PyO3's maximum supported version (3.13)
```

**Cause:** Python 3.14 is too new — pydantic-core (required by FastAPI) has no pre-built wheel and cannot compile for 3.14 yet.

**Solution:** Install Python 3.12 alongside 3.14 (both coexist safely — no uninstall needed):
```bash
sudo apt install software-properties-common -y
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install python3.12 python3.12-venv -y
```

**Create venv with Python 3.12:**
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Result:** All packages install successfully with pre-built wheels — no compilation needed.

### Running the application

**Terminal 1 — FastAPI:**
```bash
cd /mnt/d/OVH
source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — Celery worker:**
```bash
cd /mnt/d/OVH
source .venv/bin/activate
celery -A worker.celery_app:celery worker --loglevel=info
```

**Note:** Access the API at `http://localhost:8000/health` (NOT `http://0.0.0.0:8000` — that's a server-side bind address, not a browsable URL).

#### Error: Celery loglevel typo

**Error:**
```
Error: Invalid value for '-l' / '--loglevel': 'INF' is not one of 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL', 'FATAL'.
```

**Cause:** Typo — `inf` instead of `info`.

**Solution:**
```bash
celery -A worker.celery_app:celery worker --loglevel=info
```

---

## 7. Errors Encountered & Solutions — Summary

| # | Error | Cause | Solution |
|---|-------|-------|----------|
| 1 | `wsl --install` failed | Not running as admin | Open PowerShell as Administrator |
| 2 | `docker --version` not recognized after install | PATH not updated | Restart PC |
| 3 | Docker not found inside WSL | WSL integration not enabled | Docker Desktop → Settings → Resources → WSL Integration → Ubuntu ON |
| 4 | Postal image `:3` not found | Tag doesn't exist | Use `:latest` tag |
| 5 | `postal-cron` container restarting | `cron` is not a valid Postal command | Remove the service from docker-compose.yml |
| 6 | Postal web unreachable | Puma bound to `127.0.0.1` inside container | Add `BIND_ADDRESS: 0.0.0.0` env var |
| 7 | Postal returns 403 Forbidden | Wrong config key for hostname | Use `postal.web_hostname` (v2 format) instead of `web.host` |
| 8 | WSL DNS failure | WSL default DNS resolver broken | `echo "nameserver 8.8.8.8" \| sudo tee /etc/resolv.conf` |
| 9 | `python3-venv` not available | Package not installed | `sudo apt install python3-venv -y` |
| 10 | pydantic-core won't compile | Python 3.14 too new for PyO3 | Install Python 3.12 via deadsnakes PPA, use for venv |
| 11 | `cc` linker not found (Rust compile) | Build tools missing | `sudo apt install build-essential -y` |
| 12 | Celery `--loglevel=inf` rejected | Typo | Use `--loglevel=info` |

---

## 8. Tools & Commands Reference

### PowerShell commands used

| Command | Purpose |
|---------|---------|
| `wsl --install` | Install WSL2 engine |
| `wsl --install -d Ubuntu` | Install Ubuntu distribution |
| `wsl --list --verbose` | List WSL distros with state and version |
| `wsl -u root passwd <user>` | Reset WSL user password |
| `Get-ComputerInfo \| Select HyperVisorPresent` | Check virtualization status |
| `winget install Docker.DockerDesktop` | Install Docker Desktop |
| `code --install-extension <ext>` | Install VS Code extension |

### Docker commands used

| Command | Purpose |
|---------|---------|
| `docker compose up -d` | Start all services in background |
| `docker compose ps` | List container statuses |
| `docker compose restart <service>` | Restart specific service |
| `docker compose down` | Stop and remove all containers |
| `docker compose down -v` | Stop, remove containers AND delete data volumes |
| `docker compose run --rm <svc> <cmd>` | Run a one-off command in a service container |
| `docker logs <container> --tail N` | View last N lines of container logs |
| `docker exec <container> <cmd>` | Run command inside running container |
| `docker exec -it <container> <shell>` | Open interactive shell inside container |
| `docker stop <container>` | Stop a container |
| `docker rm <container>` | Remove a stopped container |
| `docker manifest inspect <image>` | Check if a Docker image/tag exists |

### Linux (WSL) commands used

| Command | Purpose |
|---------|---------|
| `sudo apt update` | Refresh package lists |
| `sudo apt install <pkg> -y` | Install a package |
| `sudo add-apt-repository ppa:deadsnakes/ppa` | Add Python versions repository |
| `echo "nameserver 8.8.8.8" \| sudo tee /etc/resolv.conf` | Fix DNS resolution |
| `python3.12 -m venv .venv` | Create virtual environment |
| `source .venv/bin/activate` | Activate virtual environment |
| `deactivate` | Deactivate virtual environment |
| `pip install -r requirements.txt` | Install Python dependencies |
| `rm -rf .venv` | Delete virtual environment |

### Application commands

| Command | Purpose |
|---------|---------|
| `uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload` | Start FastAPI dev server |
| `celery -A worker.celery_app:celery worker --loglevel=info` | Start Celery background worker |

---

## 9. Service Access Guide

### Web UIs (open in browser)

| Service | URL | Login |
|---------|-----|-------|
| **FastAPI** | http://localhost:8000/health | No auth |
| **Postal** | http://localhost:5000 | `admin@localhost` / `postal-admin-123` |
| **Mailpit** | http://localhost:8025 | No auth |
| **RabbitMQ** | http://localhost:15672 | `postal` / `postal_pass` |

### Internal service ports

| Service | Port | Used by |
|---------|------|---------|
| MongoDB | `localhost:27017` | Your app (contacts, campaigns, events) |
| Redis | `localhost:6379` | Celery broker + warmup counters |
| MariaDB | `3306` (internal only) | Postal's private database |
| Postal SMTP | `localhost:2525` | Postal's SMTP server |
| Mailpit SMTP | `localhost:1025` | Catches all outbound email |

### How services connect

```
Your Code (FastAPI + Celery)
    │
    ├── reads/writes ───→ MongoDB (your data)
    ├── enqueues tasks ──→ Redis (Celery broker)
    └── sends mail via ──→ Postal API (HTTP, port 5000)
                              │
                              ├── stores in ──→ MariaDB (Postal's data)
                              ├── queues in ──→ RabbitMQ (Postal's broker)
                              └── delivers to → Mailpit (local catch-all)
                                                   │
                                                   └── View at http://localhost:8025
```

**Your code only talks to 3 things:** MongoDB, Redis, and Postal's API. Everything else is internal plumbing.

---

## 10. Final Status & Verification

### Services running (8 containers)

| Container | Image | Status | Port |
|-----------|-------|--------|------|
| ep-mongodb | mongo:7 | Up | 27017 |
| ep-redis | redis:7-alpine | Up | 6379 |
| ep-mailpit | axllent/mailpit:latest | Up (healthy) | 1025, 8025 |
| ep-mariadb | mariadb:11 | Up | 3306 (internal) |
| ep-rabbitmq | rabbitmq:3-management | Up | 15672 |
| ep-postal-web | ghcr.io/postalserver/postal:latest | Up | 5000 |
| ep-postal-worker | ghcr.io/postalserver/postal:latest | Up | — |
| ep-postal-smtp | ghcr.io/postalserver/postal:latest | Up | 2525 |

### Application stack

| Component | Status |
|-----------|--------|
| FastAPI | Running on http://localhost:8000 |
| Celery | Running with Redis broker |
| Python venv | Python 3.12 with all deps installed |

### Postal configuration

| Setting | Value |
|---------|-------|
| Organization | DevOrg |
| Mail Server | DevServer |
| API Key | `j1mUFF9Q8nm2mpEHg6DnqhD7` (saved in .env) |
| Outbound relay | Mailpit (localhost:1025) — no real email leaves machine |

### What's next

**Step 3 — MongoDB Data Model:** Design core document schemas (contact, list, campaign, event, suppression) with proper indexes for hot paths.

---

*Document generated: 2026-06-23*  
*Next session: Continue from Step 3*

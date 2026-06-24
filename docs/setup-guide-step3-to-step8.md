# Email Platform — Setup Guide (Step 3 to Step 8)

**Project:** Self-hosted Email Sending Platform + CRM  
**Date:** 2026-06-24  
**Environment:** Windows 11 Pro, WSL2 + Ubuntu (Python 3.12), Docker Desktop  
**Continues from:** [setup-guide-step0-to-step2.md](setup-guide-step0-to-step2.md)

---

## Table of Contents

1. [Step 3: MongoDB Data Model](#1-step-3-mongodb-data-model)
2. [Step 4: FastAPI Endpoints](#2-step-4-fastapi-endpoints)
3. [Step 5: Celery Worker Pipeline](#3-step-5-celery-worker-pipeline)
4. [Step 6: Wire Postal Locally](#4-step-6-wire-postal-locally)
5. [Step 7: Prove the Core Loop End-to-End](#5-step-7-prove-the-core-loop-end-to-end)
6. [Step 8: Layer in Capabilities](#6-step-8-layer-in-capabilities)
7. [Errors Encountered & Solutions — Summary](#7-errors-encountered--solutions--summary)
8. [Complete API Reference](#8-complete-api-reference)
9. [Final Project Structure](#9-final-project-structure)
10. [Final Status & Verification](#10-final-status--verification)

---

## 1. Step 3: MongoDB Data Model

### What was built

5 core document schemas (Pydantic models) with indexes for hot paths, plus a database connection module.

### Files created

| File | Purpose |
|------|---------|
| `models/contact.py` | Contact schema with email, stream, status, engagement stats |
| `models/campaign.py` | Campaign schema with target, template, stats |
| `models/list.py` | List/segment schema with filter rules |
| `models/event.py` | Per-recipient event tracking (sent/delivered/opened/clicked/bounced) |
| `models/suppression.py` | Suppression list (hard bounce, complaint, unsubscribe, role, spam trap) |
| `models/database.py` | Async MongoDB connection (Motor) + index creation |

### Document schemas

#### Contact
```python
{
    "email": "alice@test.com",          # unique index
    "first_name": "Alice",
    "last_name": "Smith",
    "attributes": {},                    # custom key-value data
    "stream": "cold",                    # optin | engaged | cold
    "status": "active",                  # active | unsubscribed | bounced | complained | suppressed
    "source": "import",                  # import | api | signup | manual
    "list_ids": ["64a..."],             # which lists this contact belongs to
    "engagement": {
        "last_sent_at": null,
        "last_opened_at": null,
        "last_clicked_at": null,
        "total_sent": 0,
        "total_opened": 0,
        "total_clicked": 0
    },
    "created_at": "2026-06-24T...",
    "updated_at": "2026-06-24T..."
}
```

#### Campaign
```python
{
    "name": "Welcome Campaign",
    "subject": "Hello {{first_name}}!",   # supports template variables
    "from_name": "Dev Team",
    "from_email": "hello@mail.localhost",
    "html_body": "<h1>Hi {{first_name}}!</h1>",
    "text_body": null,
    "stream": "cold",                      # determines which IP pool / subdomain
    "target_list_id": "64a...",
    "status": "draft",                     # draft | scheduled | sending | paused | completed | cancelled
    "stats": {
        "total_recipients": 0,
        "sent": 0, "delivered": 0, "opened": 0,
        "clicked": 0, "bounced": 0, "complained": 0, "unsubscribed": 0
    },
    "started_at": null,
    "completed_at": null,
    "created_at": "2026-06-24T..."
}
```

#### Event
```python
{
    "campaign_id": "64a...",
    "contact_id": "64a...",
    "email": "alice@test.com",
    "event_type": "sent",                  # sent | delivered | opened | clicked | bounced | complained | unsubscribed
    "stream": "cold",
    "bounce_type": null,                   # hard | soft (only for bounces)
    "bounce_message": null,
    "click_url": null,                     # only for clicks
    "postal_message_id": "abc123",
    "created_at": "2026-06-24T..."
}
```

#### Suppression
```python
{
    "email": "bob@test.com",               # unique index — the hottest lookup (checked every send)
    "reason": "hard_bounce",               # hard_bounce | complaint | unsubscribe | role_address | spam_trap | manual
    "source": "postal_webhook",
    "campaign_id": "64a...",
    "created_at": "2026-06-24T..."
}
```

#### ContactList
```python
{
    "name": "Test List",                   # unique index
    "description": "First test list",
    "list_type": "static",                 # static | segment
    "segment_rules": [],                   # filter rules for dynamic segments
    "segment_match": "all",                # "all" = AND, "any" = OR
    "contact_count": 5,
    "created_at": "2026-06-24T..."
}
```

### Indexes created

| Collection | Index | Why |
|------------|-------|-----|
| contacts | `email` (unique) | Lookup by email on every import/send |
| contacts | `status + stream` | Filter contacts by stream for campaign targeting |
| contacts | `list_ids` | Find all contacts in a list |
| contacts | `stream + engagement.last_opened_at` | Identify engaged contacts per stream |
| campaigns | `status` | Query active/sending campaigns |
| campaigns | `stream` | Per-stream campaign list |
| campaigns | `created_at` (desc) | Recent campaigns first |
| lists | `name` (unique) | Prevent duplicate list names |
| events | `campaign_id + event_type` | Campaign stats aggregation |
| events | `contact_id + created_at` | Contact event history |
| events | `email + event_type` | Suppression trigger lookup |
| suppressions | `email` (unique) | **Hottest path** — checked before every single send |
| suppressions | `reason` | Breakdown by suppression reason |

### Verification

**Command to verify indexes:**
```powershell
docker exec ep-mongodb mongosh email_platform --quiet --eval "db.getCollectionNames().forEach(c => { print('--- ' + c); db[c].getIndexes().forEach(i => print('  ' + i.name)) })"
```

**Health endpoint updated** to confirm MongoDB connection:
```json
{"status":"ok","env":"localhost","mongodb":"connected"}
```

### Dependencies added

| Package | Version | Purpose |
|---------|---------|---------|
| `email-validator` | 2.2.0 | Pydantic `EmailStr` validation |

**Install command:**
```bash
pip install email-validator==2.2.0
```

---

## 2. Step 4: FastAPI Endpoints

### What was built

16 API endpoints across 5 route modules, all validated and writing to MongoDB.

### Files created

| File | Purpose |
|------|---------|
| `api/routes/__init__.py` | Package init |
| `api/routes/contacts.py` | Import, list, get, update, delete contacts |
| `api/routes/campaigns.py` | Create, list, get, launch, pause campaigns |
| `api/routes/lists.py` | Create lists, add contacts to lists |
| `api/routes/events.py` | Query events, campaign stats aggregation |
| `api/routes/suppressions.py` | Add/remove/check suppressions |

### Endpoint reference

| Route | Method | Purpose |
|-------|--------|---------|
| `/health` | GET | System health + MongoDB status |
| `/contacts/import` | POST | Bulk import contacts (skips duplicates) |
| `/contacts` | GET | List contacts (filter by stream, status, pagination) |
| `/contacts/{email}` | GET | Get single contact by email |
| `/contacts/{email}` | PATCH | Update contact fields |
| `/contacts/{email}` | DELETE | Delete contact |
| `/campaigns` | POST | Create campaign (starts as draft) |
| `/campaigns` | GET | List campaigns (filter by status) |
| `/campaigns/{id}` | GET | Get campaign details + stats |
| `/campaigns/{id}/launch` | POST | Launch campaign → enqueues Celery tasks per recipient |
| `/campaigns/{id}/pause` | POST | Pause a sending campaign |
| `/lists` | POST | Create list or segment |
| `/lists` | GET | List all lists |
| `/lists/{id}` | GET | Get list details |
| `/lists/{id}/contacts` | POST | Add contacts to list by email |
| `/events` | GET | Query events (filter by campaign, contact, type) |
| `/events/stats/{id}` | GET | Aggregated event counts per campaign |
| `/suppressions` | POST | Add email to suppression list |
| `/suppressions` | GET | List suppressions (filter by reason) |
| `/suppressions/check/{email}` | GET | Check if email is suppressed |
| `/suppressions/{email}` | DELETE | Remove from suppression list |

### How launch works

The `/campaigns/{id}/launch` endpoint:
1. Validates campaign is in `draft` status
2. Counts matching active contacts (by `target_list_id` if set)
3. Updates campaign status to `sending`
4. Iterates contacts and calls `send_to_recipient.delay(campaign_id, contact_id)` for each
5. Returns enqueued count

**Key:** FastAPI enqueues work but **never sends email itself**. Celery workers do the actual sending.

### Verification

**Test commands used:**
```powershell
# Import contacts
$body = '{"contacts":[{"email":"alice@test.com","first_name":"Alice","stream":"optin"}]}'
Invoke-WebRequest -Uri http://localhost:8000/contacts/import -Method POST -Body $body -ContentType "application/json"

# Create campaign
$body = '{"name":"Test","subject":"Hello","from_name":"Dev","from_email":"hello@mail.localhost","html_body":"<h1>Hi</h1>","stream":"cold"}'
Invoke-WebRequest -Uri http://localhost:8000/campaigns -Method POST -Body $body -ContentType "application/json"

# Check suppression
Invoke-WebRequest -Uri http://localhost:8000/suppressions/check/alice@test.com
```

**Interactive API docs:** http://localhost:8000/docs (Swagger UI auto-generated by FastAPI)

---

## 3. Step 5: Celery Worker Pipeline

### What was built

The complete per-recipient send pipeline: suppression → warmup → routing → render → Postal API → event recording.

### Files created

| File | Purpose |
|------|---------|
| `models/sync_db.py` | Synchronous MongoDB client (Celery tasks are sync, not async) |
| `core/suppression.py` | `is_suppressed(email)` check + `add_suppression()` |
| `core/warmup.py` | Daily caps per stream via Redis counters |
| `core/routing.py` | Stream → sending domain mapping |
| `core/render.py` | `{{variable}}` template rendering with dot notation support |
| `core/postal_client.py` | HTTP client for Postal API |
| `worker/tasks.py` | Full `send_to_recipient` task |
| `worker/celery_app.py` | Updated with `sys.path` fix + `autodiscover_tasks` |

### Pipeline flow (per recipient)

```
send_to_recipient(campaign_id, contact_id)
    │
    ├─ 1. Suppression check      → skip if email is suppressed (MongoDB lookup)
    ├─ 2. Warmup quota check     → requeue if daily cap reached (Redis counter)
    ├─ 3. Stream routing          → map stream → sending domain
    │       optin  → mail.localhost
    │       engaged → eng.localhost
    │       cold   → out.localhost
    ├─ 4. Render template         → replace {{first_name}}, {{last_name}}, etc.
    ├─ 5. Send via Postal API     → HTTP POST (retries 3x on failure)
    ├─ 6. Increment warmup count  → Redis INCR warmup:{stream}:{date}
    ├─ 7. Record event            → MongoDB events collection (type: "sent")
    ├─ 8. Update contact          → engagement.last_sent_at, total_sent +1
    └─ 9. Update campaign stats   → stats.sent +1
```

### Warmup system

| Stream | Default daily cap | Stored in |
|--------|-------------------|-----------|
| optin | 500 | Redis key: `warmup:optin:2026-06-24` |
| engaged | 200 | Redis key: `warmup:engaged:2026-06-24` |
| cold | 100 | Redis key: `warmup:cold:2026-06-24` |

- Caps are configurable via `.env` (`WARMUP_OPTIN_DAILY_CAP`, etc.)
- Counter auto-expires after 48 hours
- If cap reached, task is requeued with retry (up to 3 retries)
- Configurable ramp percentage (`WARMUP_RAMP_PERCENT=20`)

### Template rendering

Supports simple variable substitution:
- `{{first_name}}` → contact's first_name
- `{{email}}` → contact's email
- `{{engagement.total_sent}}` → nested dot notation

### Postal API client

```python
# Sends via HTTP POST to Postal's API
POST {POSTAL_API_URL}/api/v1/send/message
Headers: X-Server-API-Key: {POSTAL_API_KEY}
Body: {to, from, subject, html_body, plain_body, tag, headers}
```

Includes `List-Unsubscribe` and `List-Unsubscribe-Post` headers for Gmail/Yahoo compliance.

### Error: Celery "unregistered task"

**Error:**
```
Received unregistered task of type 'send_to_recipient'.
Did you remember to import the module containing this task?
```

**Cause:** Celery didn't know about `worker.tasks` module — autodiscovery wasn't configured.

**Solution:** Added to `worker/celery_app.py`:
```python
celery.autodiscover_tasks(["worker"])
```

### Error: ModuleNotFoundError for 'models'

**Error:**
```
ModuleNotFoundError: No module named 'models'
```

**Cause:** Project root (`/mnt/d/OVH`) wasn't in Python's import path when Celery started.

**Solution:** Added to top of `worker/celery_app.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

### Running Celery

```bash
# In WSL terminal
cd /mnt/d/OVH
source .venv/bin/activate
celery -A worker.celery_app:celery worker --loglevel=info
```

**Note:** Must restart Celery (`Ctrl+C` + re-run) after any code changes to `worker/tasks.py` or `core/` modules. Unlike FastAPI with `--reload`, Celery doesn't auto-reload.

---

## 4. Step 6: Wire Postal Locally

### What was done

Connected the full chain: your code → Postal API → Postal Worker → SMTP relay → Mailpit inbox.

### Manual steps in Postal UI (http://localhost:5000)

#### Already completed in Step 2:
1. Organization created: **DevOrg**
2. Mail Server created: **DevServer**
3. API credential created: key `j1mUFF9Q8nm2mpEHg6DnqhD7`

#### New in Step 6:

**4. Add sending domains:**
- Go to DevOrg → DevServer → **Domains**
- Add three domains (one per stream):
  - `mail.localhost` (optin)
  - `eng.localhost` (engaged)
  - `out.localhost` (cold)
- Skip DNS verification (localhost has no real DNS)

**5. Switch to Live mode:**
- Go to DevOrg → DevServer → **Overview** or **Settings**
- Change server mode from **Development** to **Live**
- Development mode holds all messages; Live mode delivers them

### Errors encountered and fixed

#### Error 1: UnauthenticatedFromAddress

**Error response from Postal API:**
```json
{"status":"error","data":{"message":"The From address is not authorised to send mail from this server"}}
```

**Cause:** Sending domain `mail.localhost` was not registered in Postal's mail server.

**Solution:** Added `mail.localhost`, `eng.localhost`, `out.localhost` as domains in Postal UI → DevServer → Domains.

#### Error 2: smtp_relays config not working (wrong YAML format)

**Symptom:** Postal accepted messages (API returned success) but Mailpit inbox stayed empty. Messages in Postal were "requeued for trying later."

**Investigation commands:**
```bash
# Check Postal worker logs
docker logs ep-postal-worker --tail 30

# Check delivery details in Postal's MariaDB
docker exec ep-mariadb sh -c "mariadb -uroot -ppostal_root_pass 'postal-server-1' -e 'SELECT id, status, details, output FROM deliveries ORDER BY id DESC LIMIT 5;'"
```

**Cause:** The `smtp_relays` config used an object format, but Postal v2 expects URI format.

**Before (broken):**
```yaml
smtp_relays:
  - hostname: mailpit
    port: 1025
    ssl_mode: none
```

**After (fixed):**
```yaml
postal:
  smtp_relays:
    - smtp://mailpit:1025?ssl_mode=None
```

**How we found the correct format:**
```bash
# Read Postal's config schema source code
docker exec ep-postal-worker sh -c "grep -B2 -A15 'smtp_relay' /opt/postal/app/lib/postal/config_schema.rb"
```
This revealed the `transform` block that parses URI format.

#### Error 3: Missing signing.key (DKIM)

**Error in delivery table:**
```
Errno::ENOENT: No such file or directory @ rb_sysopen - /config/signing.key
```

**Cause:** Postal needs an RSA signing key for DKIM signatures on outgoing mail. No key was generated.

**Solution:**
1. Generated RSA key:
   ```bash
   openssl genrsa -out postal/signing.key 2048
   ```
2. Updated `docker-compose.yml` to mount it:
   ```yaml
   volumes:
     - ./postal/signing.key:/config/signing.key
   ```
3. Added `postal/signing.key` to `.gitignore`
4. Removed the unused `postal_signing_key` Docker volume

#### Error 4: Messages held in Development mode

**Symptom:** Messages showed status "Held" with detail "Server is in development mode."

**Investigation:**
```bash
docker exec ep-mariadb sh -c "mariadb -uroot -ppostal_root_pass 'postal-server-1' -e 'SELECT id, message_id, status, details FROM deliveries ORDER BY id DESC LIMIT 5;'"
```

**Cause:** Postal mail server was in Development mode (default), which holds all messages for manual review.

**Solution:** Switched to **Live** mode in Postal UI → DevServer settings. Released held messages, which then flowed to Mailpit.

### Final postal.yml configuration

```yaml
version: 2

postal:
  web_hostname: localhost
  web_protocol: http
  smtp_hostname: postal.localhost
  smtp_relays:
    - smtp://mailpit:1025?ssl_mode=None

main_db:
  host: mariadb
  port: 3306
  username: root
  password: postal_root_pass
  database: postal

message_db:
  host: mariadb
  port: 3306
  username: root
  password: postal_root_pass
  prefix: postal

rabbitmq:
  host: rabbitmq
  port: 5672
  username: postal
  password: postal_pass
  vhost: /postal

smtp_server:
  port: 25

dns:
  mx_records:
    - mx.postal.localhost
  smtp_server_hostname: postal.localhost
  spf_include: spf.postal.localhost
  return_path_domain: rp.postal.localhost
  track_domain: track.postal.localhost

logging:
  stdout: true
```

### Verification

**Test direct Postal API send:**
```powershell
$headers = @{"X-Server-API-Key" = "j1mUFF9Q8nm2mpEHg6DnqhD7"}
$body = @{to = @("test@example.com"); from = "Dev Team <hello@mail.localhost>"; subject = "Test"; html_body = "<h1>Hello!</h1>"} | ConvertTo-Json
Invoke-WebRequest -Uri "http://localhost:5000/api/v1/send/message" -Method POST -Headers $headers -Body $body -ContentType "application/json"
```

**Check Mailpit inbox:**
```powershell
Invoke-WebRequest -Uri "http://localhost:8025/api/v1/messages" | ConvertFrom-Json
```

---

## 5. Step 7: Prove the Core Loop End-to-End

### The milestone

This is the **single most important step** in the blueprint. It proves the entire system works as one unit.

### Pipeline tested

```
Import contacts → Create list → Add contacts → Create campaign → Launch
    → FastAPI enqueues to Redis
        → Celery picks up tasks
            → Suppression check (MongoDB)
            → Warmup quota check (Redis)
            → Stream routing (config)
            → Template rendering ({{first_name}})
            → Postal API call (HTTP)
                → Postal worker delivers
                    → Mailpit catches email
    → Events recorded (MongoDB)
    → Campaign stats updated (MongoDB)
    → Contact engagement updated (MongoDB)
    → Warmup counter incremented (Redis)
```

### Step-by-step commands

**1. Clear old data for clean test:**
```powershell
# Clear Mailpit
Invoke-WebRequest -Uri "http://localhost:8025/api/v1/messages" -Method DELETE

# Clear MongoDB
docker exec ep-mongodb mongosh email_platform --quiet --eval "db.contacts.deleteMany({}); db.campaigns.deleteMany({}); db.events.deleteMany({}); db.suppressions.deleteMany({}); db.lists.deleteMany({})"
```

**2. Import 5 test contacts:**
```powershell
$body = @{contacts = @(
    @{email="alice@test.com"; first_name="Alice"; last_name="Smith"; stream="cold"},
    @{email="bob@test.com"; first_name="Bob"; last_name="Jones"; stream="cold"},
    @{email="carol@test.com"; first_name="Carol"; last_name="Davis"; stream="cold"},
    @{email="dave@test.com"; first_name="Dave"; last_name="Wilson"; stream="cold"},
    @{email="eve@test.com"; first_name="Eve"; last_name="Brown"; stream="cold"}
)} | ConvertTo-Json -Depth 3
Invoke-WebRequest -Uri http://localhost:8000/contacts/import -Method POST -Body $body -ContentType "application/json"
# Result: {"imported":5,"skipped":0,"errors":[]}
```

**3. Create list + add contacts:**
```powershell
# Create list
$body = '{"name":"Test List","description":"First end-to-end test list"}'
$r = Invoke-WebRequest -Uri http://localhost:8000/lists -Method POST -Body $body -ContentType "application/json"
$listId = ($r.Content | ConvertFrom-Json).id

# Add contacts
$emails = '["alice@test.com","bob@test.com","carol@test.com","dave@test.com","eve@test.com"]'
Invoke-WebRequest -Uri "http://localhost:8000/lists/$listId/contacts" -Method POST -Body $emails -ContentType "application/json"
# Result: {"matched":5,"modified":5}
```

**4. Create campaign:**
```powershell
$body = @{
    name="First E2E Campaign"
    subject="Hello {{first_name}}, welcome!"
    from_name="Dev Team"
    from_email="hello@mail.localhost"
    html_body="<h1>Hi {{first_name}} {{last_name}}!</h1><p>This is your first email from the platform.</p>"
    stream="cold"
    target_list_id=$listId
} | ConvertTo-Json
Invoke-WebRequest -Uri http://localhost:8000/campaigns -Method POST -Body $body -ContentType "application/json"
# Result: {"id":"...","name":"First E2E Campaign","status":"draft"}
```

**5. Launch campaign:**
```powershell
Invoke-WebRequest -Uri "http://localhost:8000/campaigns/$campaignId/launch" -Method POST
# Result: {"campaign_id":"...","status":"sending","total_recipients":5,"enqueued":5}
```

### Results verified

| Check | Command | Result |
|-------|---------|--------|
| MongoDB events | `db.events.find({},{email:1,event_type:1})` | 5 "sent" events |
| Campaign stats | `db.campaigns.findOne().stats` | `sent: 5, total_recipients: 5` |
| Contact engagement | `db.contacts.find({},{email:1,"engagement.total_sent":1})` | `total_sent: 1` for each |
| Warmup counter | `redis-cli GET warmup:cold:2026-06-24` | `5` |
| Mailpit inbox | `GET http://localhost:8025/api/v1/messages` | 5 personalized emails |

**Mailpit emails received:**
- "Hello Alice, welcome!" — template rendered with first name
- "Hello Bob, welcome!"
- "Hello Carol, welcome!"
- "Hello Dave, welcome!"
- "Hello Eve, welcome!"

### Q&A during Step 7

**Q: Where are MongoDB collections and email tracking updates?**

Two separate databases track activity:

| Database | What it stores | How to access |
|----------|---------------|---------------|
| MongoDB `email_platform` | Your app data: contacts, campaigns, events, suppressions | `docker exec -it ep-mongodb mongosh email_platform` |
| Postal's MariaDB `postal-server-1` | Postal's internal: message metadata, delivery attempts, SMTP responses | `docker exec -it ep-mariadb mariadb -uroot -ppostal_root_pass postal-server-1` |

**Important:** Don't run Docker commands inside `mongosh` — exit with `exit` first, then run in your regular terminal.

---

## 6. Step 8: Layer in Capabilities

### What was built

4 new capability modules added on top of the working core loop.

### 8.1 Postal Webhook — Event Ingestion

**File:** `api/routes/webhooks.py`

**Endpoint:** `POST /webhooks/postal`

Receives events from Postal when emails are delivered, bounced, opened, or clicked. Updates MongoDB events, campaign stats, contact engagement, and auto-suppresses on hard bounces.

**Event mapping:**

| Postal Event | Mapped To | Action |
|-------------|-----------|--------|
| `MessageSent` / `MessageDelivered` | `delivered` | Record event, increment campaign stats |
| `MessageBounced` / `MessageDeliveryFailed` | `bounced` | Record event, auto-suppress if hard bounce |
| `MessageLoaded` | `opened` | Record event, update contact `last_opened_at` |
| `MessageLinkClicked` | `clicked` | Record event, update contact `last_clicked_at` |

**Auto-suppression flow:**
```
Hard bounce webhook → add to suppressions collection
                    → update contact status to "suppressed"
                    → future sends skip this contact
```

**Test — simulated hard bounce:**
```powershell
$body = @{event="MessageBounced"; payload=@{message=@{id=1; rcpt_to="bob@test.com"; tag="campaign_id"}; status="HardFail"; details="550 User not found"}} | ConvertTo-Json -Depth 4
Invoke-WebRequest -Uri "http://localhost:8000/webhooks/postal" -Method POST -Body $body -ContentType "application/json"
# Result: {"status":"processed","event":"bounced","email":"bob@test.com"}

# Verify suppression:
Invoke-WebRequest -Uri "http://localhost:8000/suppressions/check/bob@test.com"
# Result: {"email":"bob@test.com","suppressed":true,"reason":"hard_bounce"}
```

**Note:** To receive real webhooks from Postal, configure a webhook in Postal UI → DevServer → Webhooks → URL: `http://host.docker.internal:8000/webhooks/postal`. This is for production; locally we tested by sending simulated payloads.

### 8.2 One-Click Unsubscribe

**Files:** `api/routes/unsubscribe.py`, updated `core/postal_client.py`

**Endpoints:**

| Route | Method | Purpose |
|-------|--------|---------|
| `/unsubscribe/{email}` | GET | Landing page with unsubscribe button |
| `/unsubscribe/{email}` | POST | Confirms unsubscribe, adds to suppression |
| `/unsubscribe/one-click` | POST | RFC 8058 one-click (Gmail/Yahoo requirement) |

**Headers added to every outgoing email:**
```
List-Unsubscribe: <http://localhost:8000/unsubscribe/user@example.com>, <mailto:unsubscribe@mail.localhost>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

**Why this matters:** Gmail and Yahoo require `List-Unsubscribe` with one-click POST support for bulk senders (>5000 emails/day). Without it, emails are more likely to be flagged as spam.

**Flow:**
```
User clicks "Unsubscribe" in email client
    → GET /unsubscribe/{email} (shows confirmation page)
    → User clicks button
    → POST /unsubscribe/{email}
        → Email added to suppressions (reason: "unsubscribe")
        → Contact status set to "unsubscribed"
        → Shows "You've been unsubscribed" page
```

### 8.3 List Cleaning / Verification Pipeline

**File:** `core/cleaning.py`, `api/routes/cleaning.py`

**Endpoints:**

| Route | Method | Purpose |
|-------|--------|---------|
| `/cleaning/verify` | POST | Verify single email |
| `/cleaning/bulk` | POST | Bulk clean a list of emails |
| `/cleaning/clean-list/{list_id}` | POST | Clean all contacts in a specific list |

**Verification checks (in order):**

| Check | What it does | Example |
|-------|-------------|---------|
| **Syntax validation** | Regex check for valid email format | `bad@@email` → invalid |
| **Deduplication** | Detects duplicate emails in batch | Skipped on second occurrence |
| **Role address detection** | Checks against 30+ known role addresses | `admin@`, `postmaster@`, `noreply@` |
| **Disposable domain detection** | Checks against known throwaway domains | `mailinator.com`, `guerrillamail.com` |
| **MX record check** | DNS lookup to verify domain accepts email | `nonexistent.xyz` → no MX |

**Verdict categories:**

| Verdict | Meaning | Action |
|---------|---------|--------|
| `valid` | Passes all checks | Safe to send |
| `invalid_syntax` | Not a valid email format | Don't send |
| `no_mx` | Domain has no mail server | Don't send |
| `disposable` | Throwaway email service | Don't send |
| `role` | Generic role address (admin@, info@) | Send with caution |
| `duplicate` | Already seen in this batch | Skip |

**Test — bulk cleaning:**
```powershell
$body = '{"emails":["good@gmail.com","bad@@","admin@gmail.com","test@mailinator.com","user@nonexistent99999.com"]}'
Invoke-WebRequest -Uri "http://localhost:8000/cleaning/bulk" -Method POST -Body $body -ContentType "application/json"
# Result:
# {"summary":{"valid":1,"invalid_syntax":1,"no_mx":1,"disposable":1,"role":1,"duplicate":0}}
```

**Test — single email verification:**
```powershell
$body = '{"email":"shubham.srivastava@vedsu.com"}'
Invoke-WebRequest -Uri "http://localhost:8000/cleaning/verify" -Method POST -Body $body -ContentType "application/json"
# Result:
# {"email":"shubham.srivastava@vedsu.com","valid_syntax":true,"is_role":false,"is_disposable":false,"has_mx":true,"mx_record":"alt4.aspmx.l.google.com.","verdict":"valid"}
```

### 8.4 Dashboard Stats

**File:** `api/routes/dashboard.py`

**Endpoints:**

| Route | Method | Purpose |
|-------|--------|---------|
| `/dashboard/overview` | GET | Total contacts, campaigns, events, by-stream breakdown |
| `/dashboard/stream/{stream}` | GET | Per-stream: active contacts, event counts, campaign totals |
| `/dashboard/suppression-breakdown` | GET | Suppressions grouped by reason |

**Test — overview:**
```powershell
Invoke-WebRequest -Uri "http://localhost:8000/dashboard/overview"
# Result:
# {"contacts":{"total":5,"active":5,"suppressed":0,"by_stream":{"cold":5}},
#  "campaigns":{"total":1},"events":{"total":5}}
```

**Test — stream stats:**
```powershell
Invoke-WebRequest -Uri "http://localhost:8000/dashboard/stream/cold"
# Result:
# {"stream":"cold","active_contacts":5,"events":{"sent":5},
#  "campaigns":{"total":1,"sent":5,"delivered":0,"opened":0,"clicked":0,"bounced":0}}
```

**Test — suppression breakdown:**
```powershell
Invoke-WebRequest -Uri "http://localhost:8000/dashboard/suppression-breakdown"
# Result:
# {"total":1,"by_reason":{"hard_bounce":1}}
```

### Dependencies added

| Package | Version | Purpose |
|---------|---------|---------|
| `dnspython` | 2.7.0 | MX record lookup for email cleaning |
| `python-multipart` | 0.0.20 | Form data parsing for one-click unsubscribe |

**Install command:**
```bash
pip install dnspython==2.7.0 python-multipart==0.0.20
```

### Personal email test

Tested with real email `shubham.srivastava@vedsu.com`:
- Cleaning verified: valid syntax, not role, not disposable, has MX (Google Workspace)
- Imported as optin contact
- Campaign sent through full pipeline
- Email rendered with personalization: "Hello Shubham, your platform is live!"
- Landed in Mailpit (not real inbox — localhost can't deliver externally)

---

## 7. Errors Encountered & Solutions — Summary

| # | Step | Error | Cause | Solution |
|---|------|-------|-------|----------|
| 1 | 6 | `UnauthenticatedFromAddress` from Postal API | Sending domain not registered | Added `mail.localhost`, `eng.localhost`, `out.localhost` in Postal UI |
| 2 | 6 | Messages accepted but never reach Mailpit | `smtp_relays` config used wrong YAML format | Changed from object to URI: `smtp://mailpit:1025?ssl_mode=None` |
| 3 | 6 | `signing.key not found` error in deliveries | No DKIM signing key existed | Generated RSA key with `openssl genrsa`, mounted in docker-compose |
| 4 | 6 | Messages "Held" — "Server is in development mode" | Postal mail server in Development mode | Switched to **Live** mode in Postal UI |
| 5 | 7 | `Received unregistered task of type 'send_to_recipient'` | Celery didn't autodiscover task module | Added `celery.autodiscover_tasks(["worker"])` |
| 6 | 7 | `ModuleNotFoundError: No module named 'models'` | Project root not in Python path for Celery | Added `sys.path.insert(0, ...)` to `celery_app.py` |

---

## 8. Complete API Reference

### All 25 endpoints

| # | Route | Method | Tag | Purpose |
|---|-------|--------|-----|---------|
| 1 | `/health` | GET | health | System health + MongoDB status |
| 2 | `/contacts/import` | POST | contacts | Bulk import contacts |
| 3 | `/contacts` | GET | contacts | List contacts (filter, paginate) |
| 4 | `/contacts/{email}` | GET | contacts | Get single contact |
| 5 | `/contacts/{email}` | PATCH | contacts | Update contact |
| 6 | `/contacts/{email}` | DELETE | contacts | Delete contact |
| 7 | `/campaigns` | POST | campaigns | Create campaign (draft) |
| 8 | `/campaigns` | GET | campaigns | List campaigns |
| 9 | `/campaigns/{id}` | GET | campaigns | Get campaign + stats |
| 10 | `/campaigns/{id}/launch` | POST | campaigns | Launch → enqueue Celery tasks |
| 11 | `/campaigns/{id}/pause` | POST | campaigns | Pause sending campaign |
| 12 | `/lists` | POST | lists | Create list/segment |
| 13 | `/lists` | GET | lists | List all lists |
| 14 | `/lists/{id}` | GET | lists | Get list details |
| 15 | `/lists/{id}/contacts` | POST | lists | Add contacts to list |
| 16 | `/events` | GET | events | Query events |
| 17 | `/events/stats/{id}` | GET | events | Campaign event aggregation |
| 18 | `/suppressions` | POST | suppressions | Add suppression |
| 19 | `/suppressions` | GET | suppressions | List suppressions |
| 20 | `/suppressions/check/{email}` | GET | suppressions | Check if suppressed |
| 21 | `/suppressions/{email}` | DELETE | suppressions | Remove suppression |
| 22 | `/webhooks/postal` | POST | webhooks | Postal event ingestion |
| 23 | `/unsubscribe/{email}` | GET/POST | unsubscribe | Unsubscribe page + confirm |
| 24 | `/unsubscribe/one-click` | POST | unsubscribe | RFC 8058 one-click |
| 25 | `/cleaning/verify` | POST | cleaning | Verify single email |
| 26 | `/cleaning/bulk` | POST | cleaning | Bulk clean emails |
| 27 | `/cleaning/clean-list/{id}` | POST | cleaning | Clean all contacts in list |
| 28 | `/dashboard/overview` | GET | dashboard | Platform overview stats |
| 29 | `/dashboard/stream/{stream}` | GET | dashboard | Per-stream stats |
| 30 | `/dashboard/suppression-breakdown` | GET | dashboard | Suppressions by reason |

**Interactive docs:** http://localhost:8000/docs

---

## 9. Final Project Structure

```
D:\OVH\
├── .env                              # local config (git-ignored)
├── .env.example                      # committable template
├── .gitignore
├── docker-compose.yml                # 8 services
├── requirements.txt                  # 11 Python packages
├── email-platform-blueprint.md       # architecture reference
│
├── api/
│   ├── __init__.py
│   ├── main.py                       # FastAPI app + lifespan + route registration
│   └── routes/
│       ├── __init__.py
│       ├── contacts.py               # import, CRUD
│       ├── campaigns.py              # create, launch, pause
│       ├── lists.py                  # create, add contacts
│       ├── events.py                 # query, stats
│       ├── suppressions.py           # add, check, remove
│       ├── webhooks.py               # Postal event ingestion
│       ├── unsubscribe.py            # one-click unsubscribe
│       ├── cleaning.py               # verify, bulk clean
│       └── dashboard.py              # overview, stream stats
│
├── worker/
│   ├── __init__.py
│   ├── celery_app.py                 # Celery config + autodiscovery
│   └── tasks.py                      # send_to_recipient (full pipeline)
│
├── models/
│   ├── __init__.py
│   ├── contact.py                    # Contact schema + indexes
│   ├── campaign.py                   # Campaign schema + indexes
│   ├── list.py                       # List/Segment schema + indexes
│   ├── event.py                      # Event schema + indexes
│   ├── suppression.py                # Suppression schema + indexes
│   ├── database.py                   # Async MongoDB (Motor) connection
│   └── sync_db.py                    # Sync MongoDB (PyMongo) for Celery
│
├── core/
│   ├── __init__.py
│   ├── config.py                     # Pydantic Settings (reads .env)
│   ├── suppression.py                # is_suppressed() + add_suppression()
│   ├── warmup.py                     # Redis daily caps per stream
│   ├── routing.py                    # Stream → domain mapping
│   ├── render.py                     # {{variable}} template engine
│   ├── postal_client.py              # HTTP client for Postal API
│   └── cleaning.py                   # Email validation pipeline
│
├── postal/
│   ├── postal.yml                    # Postal engine config
│   └── signing.key                   # DKIM signing key (git-ignored)
│
└── docs/
    ├── setup-guide-step0-to-step2.md # Previous session documentation
    └── setup-guide-step3-to-step8.md # This document
```

---

## 10. Final Status & Verification

### Services running (8 containers)

| Container | Status | Port |
|-----------|--------|------|
| ep-mongodb | Up | 27017 |
| ep-redis | Up | 6379 |
| ep-mailpit | Up (healthy) | 1025, 8025 |
| ep-mariadb | Up | 3306 (internal) |
| ep-rabbitmq | Up | 15672 |
| ep-postal-web | Up | 5000 |
| ep-postal-worker | Up | — |
| ep-postal-smtp | Up | 2525 |

### Application stack

| Component | Status |
|-----------|--------|
| FastAPI | Running on http://localhost:8000 (30 endpoints) |
| Celery | Running with autodiscovery |
| Python venv | Python 3.12, 11 packages installed |

### End-to-end test results

| Metric | Value |
|--------|-------|
| Contacts imported | 6 (5 test + 1 real) |
| Campaigns sent | 2 |
| Emails delivered to Mailpit | 10+ |
| Events recorded | 5+ sent events |
| Warmup counter | `warmup:cold:2026-06-24 = 5` |
| Suppressions | 1 (hard bounce auto-suppression tested) |
| Email cleaning | Verified: syntax, role, disposable, MX all working |
| Unsubscribe | Page renders and processes |
| Template rendering | `{{first_name}}` personalization confirmed |

### Blueprint progress

| Phase | Status |
|-------|--------|
| Phase 1 — Local environment | ✅ Complete |
| Phase 2 — Core pipeline | ✅ Complete |
| Phase 3 — IP pools + warmup + routing | ✅ Built (config-level; real IPs at deploy) |
| Phase 4 — CRM UI + dashboards | ⏳ API endpoints ready, frontend not built |
| Phase 5 — Claude integration | ⏳ Not started |
| Phase 6 — Cleaning + verification | ✅ Complete |
| Phase 7 — Cloud deploy | ⏳ Awaiting server + IPs + DNS |
| Phase 8 — Warmup ramp + go-live | ⏳ Depends on Phase 7 |

### Restart commands (for next session)

```powershell
# 1. Start Docker Desktop (from Start menu)

# 2. Start Docker stack
docker compose -f d:\OVH\docker-compose.yml up -d

# 3. Start FastAPI (WSL Terminal 1)
cd /mnt/d/OVH && source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 4. Start Celery (WSL Terminal 2)
cd /mnt/d/OVH && source .venv/bin/activate
celery -A worker.celery_app:celery worker --loglevel=info

# 5. Fix WSL DNS if needed
echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf
```

---

*Document generated: 2026-06-24*  
*Covers: Steps 3–8 of the Email Platform build*

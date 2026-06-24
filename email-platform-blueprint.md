# Email Sending Platform + CRM — Build Blueprint

A self-hosted, high-volume email sending system (~1,000,000 / day) with a team CRM on top.
Built and proven on **localhost first**, then deployed to a **dedicated cloud server** (OVH / Hetzner).

> This is a design + build plan, not the code. It exists so the build order, the moving parts,
> and the reasoning behind each choice are clear before a single line is written.

---

## 1. The essence — what this system actually is

You are building a **mini-ESP (email service provider) with a CRM in front of it.** Two layers:

- **The Brain (your code):** decides *what* to send, *to whom*, *when*, *from which stream/IP*. Manages contacts, campaigns, team, suppression, warmup, cleaning, intelligence.
- **The Muscle (Postal):** does the *actual delivery* — queues messages, opens SMTP connections to Gmail/Outlook, retries, signs DKIM, rotates IPs, tracks opens/clicks, catches bounces.

The brain never talks SMTP directly. It prepares a finished message and hands it to the muscle over an HTTP API. This separation is the backbone of the whole design.

### Three guiding principles

1. **Permanent stream separation.** Opt-in, engaged, and cold mail live on *separate IPs and subdomains forever*. They never share infrastructure. This is enforced in code (the router physically cannot place a cold send on an opt-in IP), not by discipline.
2. **Build order over feature count.** A tiny end-to-end slice that works (small list → campaign → worker → Postal → events back) beats a half-built cathedral. Every capability bolts on *after* the previous one works.
3. **Single-instance until measured.** One MongoDB, one Redis, one worker box to start. Scale out only when a real bottleneck is measured — not in anticipation.

---

## 2. The three sending streams

The most important structural decision. Each send carries a **stream tag**, and routing is bound to that tag.

| Stream | Who | Infrastructure | Reputation strategy |
|---|---|---|---|
| **Opt-in** | People who asked for your mail | Own IP pool + subdomains | Warmed and *kept* warm by continuous opt-in traffic. Protected, permanent. Never touched by cold. |
| **Engaged** | Openers/clickers from the cold list | Separate good infra | Treated as near-opt-in. Ideally graduated via re-permission. Used to seed early positive signal on cold ramps. |
| **Cold** | Targeted, industry-specific, never-engaged | Isolated, semi-disposable IPs/subdomains | Own conservative ramp. Lowest expectations. When an IP gets listed (not if), blast radius is contained here. |

**Why this matters:** the cold stream can get blocklisted; separation guarantees that when it does, your legitimate opt-in mail (password resets, receipts, mail people actually want) keeps landing in inboxes.

---

## 3. Component reference

### Engine layer (Postal + its dependencies) — you run it, you don't write it

| Unit | What it is | Its job here |
|---|---|---|
| **Postal** | Open-source mail delivery platform (self-hosted SendGrid) | Queues + delivers mail, retries, DKIM signing, IP-pool rotation, open/click tracking, bounce + complaint capture. Your code's only delivery interface. |
| **MariaDB** | Relational database | *Postal's internal storage* — message metadata, delivery status, events, tracking. You don't touch it directly. |
| **RabbitMQ** | Message broker | *Postal's internal conveyor belt* — decouples "accept message" from "deliver message" so Postal can absorb bursts. |

### Orchestration / CRM layer (your Python app) — this is what you build

| Unit | What it is | Its job here |
|---|---|---|
| **FastAPI** | Python web/API framework | The front door. Accepts requests from the CRM UI/apps, validates input, enforces team permissions, hands heavy work to the queue. Never sends mail itself. |
| **Redis** | In-memory data store | The queue backing Celery + a fast counter store for warmup/rate-limit tallies ("how many has IP #7 sent today?") checked on every send. |
| **Celery** | Distributed task queue | The background workers. Per recipient: suppression check → warmup quota check → stream routing → render → call Postal. Scale throughput by adding workers. |
| **MongoDB** | Document database | *Your* data: contacts, lists, segments, campaigns, templates, per-recipient events, suppression list. Single instance to start. |
| **S3** | Object storage | Files: template assets, attachments, large list import/export CSVs, archived event logs. **Deferrable** — not needed to prove the core loop. |

### Intelligence layer

| Unit | Role | Guardrail |
|---|---|---|
| **Claude API** | Config assistant (generate SPF/DKIM/DMARC per subdomain, draft warmup ramps, explain deliverability reports), content drafting/personalization, bounce/complaint classification | **Human-approved before any volume send. Never autonomous mass-blasting.** Claude proposes; a person pulls the trigger. |

---

## 4. The data flow (one mental model)

```
CRM UI / app
    │  (launch campaign, import list, view dashboard)
    ▼
FastAPI  ──accept & validate──►  Redis (queue)
                                     │
                                     ▼
                              Celery workers  ── per recipient ──►
                                  • suppression check (MongoDB)
                                  • warmup quota check (Redis counters)
                                  • stream routing (opt-in / engaged / cold)
                                  • render template (+ S3 assets)
                                     │
                                     ▼
                                  Postal API
                                     │  (Postal: queue → DKIM sign → rotate IP → SMTP)
                                     ▼
                          Recipient mail servers (Gmail/Outlook/…)
                                     │
                       delivered / bounced / complained / opened / clicked
                                     ▼
                          Events sync back → MongoDB
                                     │
                          ┌──────────┴──────────┐
                          ▼                     ▼
                  Suppression update      Dashboards (per stream)
```

**Upstream of Postal = your decision-making. Downstream of Postal = delivery machinery.**

---

## 5. LOCALHOST build path (do all of this before renting any server)

You build and prove the *entire* system on your own machine. The only thing localhost can't do is deliver to real strangers (residential ISPs block port 25; no PTR; blocklisted home IP). You solve that for development with a **mail catcher** (Mailpit) that captures outgoing mail in a browser inbox instead of delivering it.

### Step 0 — Prerequisites (Windows)
- Install **WSL2** (`wsl --install` in PowerShell, then reboot) → gives you a real Ubuntu environment, identical to the server.
- Install **Docker Desktop** (with WSL2 backend) → runs all components as containers with one command.
- Install **VS Code** + the WSL extension → edit in a Windows GUI, run in Linux underneath.
- Confirm: `docker --version` and `python3 --version` both respond inside WSL.

### Step 1 — Project skeleton
```
email-platform/
├── docker-compose.yml        # brings up the whole local stack
├── api/                      # FastAPI app
├── worker/                   # Celery tasks
├── models/                   # MongoDB document schemas
├── core/                     # shared logic (routing, suppression, warmup)
├── postal/                   # Postal config
└── .env                      # local config (never committed)
```

### Step 2 — Local stack via Docker Compose
One `docker-compose.yml` brings up these services together:
- `mongodb` — your database
- `redis` — queue + counters
- `mailpit` — fake SMTP server with a web inbox (the dev-mode mail catcher)
- `postal` + `mariadb` + `rabbitmq` — the engine and its deps
- (later) `api`, `worker` — your own containers

Bring it up, then verify each piece is reachable (Mongo connects, Redis pings, Mailpit UI loads in browser, Postal web UI loads).

### Step 3 — MongoDB data model
Design the core documents *first* — everything else reads/writes these:
- **contact** — email, attributes, source, stream, status, engagement history
- **list / segment** — grouping + filter rules
- **campaign** — template ref, target segment, stream, schedule, status
- **event** — per-recipient: sent / delivered / opened / clicked / bounced / complained
- **suppression** — email + reason (hard bounce / complaint / unsubscribe / role / trap) + timestamp

Index for the hot paths: suppression lookup by email (every send), events by campaign, contacts by stream + engagement.

### Step 4 — FastAPI skeleton
Minimal endpoints: health check, import contacts, create campaign, launch campaign, view events. Validates input, writes to Mongo, enqueues work. Sends nothing itself.

### Step 5 — Celery worker skeleton
One task that handles **one recipient**: check suppression → check warmup quota → route by stream → render → call Postal. Start simple and serial-correct; optimize batching only when volume demands it.

### Step 6 — Wire Postal locally
Configure Postal, create an org + mail server in its UI, generate an API key, point Postal's outbound at **Mailpit** (so nothing leaves your machine). Your worker calls Postal's API.

### Step 7 — Prove the core loop end-to-end
Import a tiny list (a handful of addresses) → launch a campaign → watch it flow FastAPI → Redis → Celery → Postal → **Mailpit catches it** → inspect the rendered email, headers, DKIM signature → confirm events are recorded back in Mongo. **This working slice is the milestone. Everything else is addition.**

### Step 8 — Layer in capabilities (each only after the prior works)
1. Suppression enforcement at enqueue
2. Bounce/complaint event ingestion → suppression update
3. Stream separation + IP-pool routing logic (pools are config locally; real IPs come at deploy)
4. Per-stream warmup scheduler (daily caps in Redis counters)
5. List cleaning/verification pipeline (syntax → dedupe → MX check → role/disposable flag)
6. One-click unsubscribe endpoint (required by Gmail/Yahoo for bulk)
7. CRM UI + team roles (admin / sender / viewer) + dashboards
8. Claude integration (config helper, content, bounce classification) — with human-approval gate

### Optional local realism
Send a *few* real test emails to **your own inbox** through a relay to confirm true rendering/delivery — without needing the IP-pool infrastructure.

---

## 6. OVH (or Hetzner) CLOUD deployment path

Only after the localhost system works. The same containers deploy to the server (minus Mailpit); Postal now talks to *real* mail servers over *real* IPs. **Code doesn't change — only configuration does** (SMTP target, IPs, domain, DNS).

> Provider note: **Hetzner** (dedicated) is the consensus best value for self-hosted sending — clean IPs, cheaper than OVH (which raised prices ~30% in March 2026). OVH is a solid runner-up with self-serve PTR. Either works; the code is identical. At this volume the box price is noise — optimize for clean IPs, no sending throttle, and an available IP block.

### Infrastructure checklist (do in this order)
1. **Order a dedicated server** (Bare Metal / Dedicated — not a budget VPS; those throttle sending).
2. **Order an IP block** for the sending pool (start modest, e.g. a handful, expand as you warm). Budget toward 10–30 IPs across all streams over time.
3. **Set up the sending domain + per-stream subdomains** with DNS access:
   - opt-in → e.g. `mail.yourdomain.com`
   - engaged → e.g. `eng.yourdomain.com`
   - cold → e.g. `out.yourdomain.com` (kept entirely separate)
4. **Create A records** for each mail hostname → each IP. Let them propagate.
5. **Set PTR (reverse DNS)** for each IP to its mail hostname (only after the A record exists/propagates). Script via the provider's API across many IPs.
6. **Open a support ticket to unblock outbound port 25** (needed for direct-to-MX delivery). Do this early — it can take time and they may ask your use case.
7. **Publish per-subdomain SPF + DKIM, and DMARC at the org domain.** Each stream gets its own DKIM selector so reputation is isolated.
8. **Register feedback loops:** Microsoft SNDS + JMRP, plus others, with an `abuse@`/`postmaster@` address, so complaints flow into suppression.

### Deploy the application
9. Put the **same Docker Compose stack** on the server (drop Mailpit; Postal now delivers for real).
10. Configure **IP pools in Postal** and tag each IP's role (dedicated vs shared, and which stream).
11. Point your **CRM/workers at the server's Postal API**.
12. Verify a controlled real send to seed/test inboxes lands correctly (SPF/DKIM/DMARC all pass).

### Go live — gradually
13. **Warming begins.** Per-IP daily caps start low and ramp over ~4–8 weeks, increasing only while bounce + complaint rates stay under threshold (complaints < ~0.3%).
14. **Opt-in stream** warms first on its own IPs (continuous real engagement).
15. **Cold stream** warms on its *own* separate ramp — seeded with the *engaged* segment for early positive signal. Never on opt-in IPs.
16. Monitor blocklists (e.g. MXToolbox), SNDS, and per-stream dashboards continuously. Treat cold IPs as semi-disposable.

---

## 7. Compliance & risk — read before going live

- **The list is mixed opt-in + purchased.** The purchased origin is the single biggest risk and is almost certainly why AWS SES was declined. Self-hosting removes the gatekeeper, not the problem — Gmail/Outlook apply the same judgment as blocklisting.
- **Spam traps** are seeded into purchased lists and *cannot* be removed by validation. Targeting reduces human complaints; it does nothing about traps. This is why the cold stream must stay isolated and semi-disposable.
- **Re-permission is the professional play** for the purchased portion: a small honest confirm-you-want-this campaign from isolated infra; keep only responders, drop the rest. Low conversion, but what remains is safe forever.
- **Legal exposure** (not legal advice — consult a qualified person for your markets): GDPR (any EU recipient — prior opt-in required), Canada CASL (consent-based), US CAN-SPAM (honest headers + working unsubscribe), India DPDP Act (consent-oriented). "We bought the list" is the fact pattern these penalize.
- **Mandatory hygiene regardless of stream:** honest headers + identity, working one-click unsubscribe, hard bounces + complaints + unsubscribes suppressed instantly, suppression checked at enqueue so nothing slips through.

### What this build will and won't include
- ✅ Full opt-in sending system, stream separation, warmup, suppression, cleaning, dashboards, Claude-assisted config/content/classification with human approval.
- ✅ A defensible cold path built on isolation + conservative ramp + re-permission.
- ❌ No spam-evasion layer (rotating domains to dodge blocklists, hiding sender identity, trap evasion). It doesn't work for long and converts a deliverability problem into a legal one.

---

## 8. Build phases at a glance

| Phase | What | Where | Depends on |
|---|---|---|---|
| 1 | Local environment (Docker stack + Mailpit) | localhost | — |
| 2 | **Core pipeline**: data model → API → Celery → Postal → suppression → events | localhost | 1 |
| 3 | IP pools + per-stream warmup + multi-subdomain routing | localhost (config) | 2 |
| 4 | CRM UI + team/roles + campaigns + dashboards | localhost | 2 |
| 5 | Claude integration (config / content / classification) | localhost | 2 |
| 6 | Cleaning + verification + engagement pruning | localhost | 2 |
| 7 | **Cloud deploy**: server, IPs, DNS, PTR, port 25, Postal, FBLs | OVH / Hetzner | 2–6 done & proven |
| 8 | Warmup ramp + go-live monitoring | cloud | 7 |

**Phase 2 is the heart.** It's the first thing to build once the environment is up, and everything else hangs off it.

---

## 9. Immediate next step

The first *buildable* thing is **Phase 1 — the local Docker environment** (FastAPI + Celery + Redis + MongoDB + Postal + Mailpit, one `docker-compose up`). Right behind it is **the MongoDB data model** (Phase 2's foundation, pure design, no infra needed).

Nothing here requires a server, an IP, or a domain yet. You build and prove the system locally, then deploy something already working — instead of debugging on a live box that's costing money.

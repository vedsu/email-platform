# IT Team — Server & Infrastructure Setup Guide

**Project:** Self-hosted Email Sending Platform  
**Prepared:** 2026-06-24  
**Target volume:** ~1,000,000 emails/day  
**Estimated setup time:** 2-3 days (excluding IP warmup period)

---

## Table of Contents

1. [Overview — What We Need](#1-overview--what-we-need)
2. [Option A: OVH Setup](#2-option-a-ovh-setup)
3. [Option B: Hetzner Setup](#3-option-b-hetzner-setup)
4. [Domain & DNS Configuration](#4-domain--dns-configuration)
5. [IP Address Setup](#5-ip-address-setup)
6. [Port 25 — Unblock SMTP](#6-port-25--unblock-smtp)
7. [SSL Certificates](#7-ssl-certificates)
8. [Feedback Loop Registration](#8-feedback-loop-registration)
9. [Server Software Requirements](#9-server-software-requirements)
10. [Handoff Checklist](#10-handoff-checklist)
11. [Cost Estimates](#11-cost-estimates)

---

## 1. Overview — What We Need

We are deploying a self-hosted email sending platform. The IT team needs to procure and configure:

| Item | Quantity | Purpose |
|------|----------|---------|
| **Dedicated server** | 1 | Runs all application containers (not a VPS — we need unthrottled sending) |
| **IP addresses** | 5-10 to start (up to 30 later) | Sending IPs for email delivery, separated by stream |
| **Domain** | 1 root domain (with multiple subdomains) | Sending identity (SPF, DKIM, DMARC) |
| **Port 25 outbound** | Must be unblocked | Required for direct-to-MX email delivery |
| **SSL certificate** | 1 (Let's Encrypt wildcard or per-subdomain) | HTTPS for web UI + tracking |

### Server specifications (minimum)

| Spec | Minimum | Recommended |
|------|---------|-------------|
| CPU | 4 cores | 8 cores |
| RAM | 16 GB | 32 GB |
| Storage | 200 GB SSD | 500 GB NVMe |
| Bandwidth | 1 Gbps unmetered | 1 Gbps unmetered |
| OS | Ubuntu 22.04 / 24.04 LTS | Ubuntu 24.04 LTS |

**Critical:** Must be a **dedicated server** (bare metal), NOT a budget VPS. Budget VPS providers throttle outbound SMTP and share IPs.

---

## 2. Option A: OVH Setup

### 2.1 Create OVH Account

1. Go to https://www.ovhcloud.com
2. Create a business account (not personal — needed for IP blocks)
3. Verify identity (may require business documents)
4. Add payment method

### 2.2 Order Dedicated Server

1. Navigate to **Bare Metal Cloud** → **Dedicated Servers**
2. Select a server matching our specs:
   - Recommended: **Advance** tier or higher
   - Location: Choose based on target audience geography
   - **Avoid Rise/Essential tiers** — limited bandwidth
3. Select **Ubuntu 24.04** as the OS
4. Complete order

**Note down:**
- Server IP (main IP)
- Server hostname
- Root SSH credentials

### 2.3 Order IP Block

1. In OVH Manager → **Bare Metal Cloud** → your server → **IP**
2. Click **"Order additional IPs"**
3. Order a **/29 block** (5 usable IPs) to start
   - Or individual IPs if blocks aren't available
4. Later scale to **/28** (13 usable IPs) or **/27** (29 usable IPs)

**Important:** Select IPs from the **same datacenter** as your server.

### 2.4 Set PTR Records (Reverse DNS)

For **each** IP address:

1. OVH Manager → **Bare Metal Cloud** → **IP** → find the IP
2. Click the **gear icon** → **"Modify reverse DNS"**
3. Set the reverse DNS to match the A record hostname:

| IP | PTR Record (Reverse DNS) |
|----|--------------------------|
| 1st IP | `mail.yourdomain.com` |
| 2nd IP | `mail.yourdomain.com` (or `mail2.yourdomain.com`) |
| 3rd IP | `eng.yourdomain.com` |
| 4th IP | `out.yourdomain.com` |
| 5th IP | `out2.yourdomain.com` |

**Rule:** The PTR record MUST match the A record. Set A records first (Section 4), wait for propagation, then set PTR.

### 2.5 OVH API (optional — for automation)

OVH provides an API for managing IPs and PTR records:
- API console: https://api.ovh.com/console/
- Useful for bulk PTR setup across many IPs
- Credentials: Application Key + Application Secret + Consumer Key

---

## 3. Option B: Hetzner Setup

### 3.1 Create Hetzner Account

1. Go to https://www.hetzner.com
2. Create account → verify identity
3. Add payment method

### 3.2 Order Dedicated Server

1. Navigate to **Dedicated** → **Server Auction** (best value) or **Configurator**
2. Recommended specs:
   - **AX42** or similar (AMD Ryzen, 64GB RAM, NVMe)
   - Location: Falkenstein or Helsinki
3. Select **Ubuntu 24.04**
4. Complete order

### 3.3 Order IP Block

1. Hetzner Robot → **Server** → **IPs** → **Order additional IPs/subnets**
2. Request a **/29 subnet** (5 usable IPs)
3. Hetzner may ask for justification — respond:
   > "We are setting up a self-hosted email sending platform. We need separate IPs for different mail streams (transactional, marketing, cold outreach) to maintain reputation isolation."

### 3.4 Set PTR Records

1. Hetzner Robot → **Server** → **IPs**
2. Click each IP → **"Edit reverse DNS"**
3. Set PTR to match A records (same table as OVH section above)

**Note:** Hetzner's clean IP reputation is a major advantage. Their IPs are generally less abused than OVH's.

---

## 4. Domain & DNS Configuration

### 4.1 Subdomains to Create

We use **separate subdomains per sending stream** for reputation isolation:

| Subdomain | Stream | Purpose |
|-----------|--------|---------|
| `mail.yourdomain.com` | Opt-in | Legitimate subscriber emails |
| `eng.yourdomain.com` | Engaged | Openers/clickers from cold list |
| `out.yourdomain.com` | Cold | Never-engaged, cold outreach |
| `postal.yourdomain.com` | — | Postal web UI |
| `track.yourdomain.com` | — | Open/click tracking |

### 4.2 A Records

Create these A records at your domain registrar (GoDaddy, Cloudflare, etc.):

| Type | Hostname | Value | TTL |
|------|----------|-------|-----|
| A | `mail.yourdomain.com` | `IP_ADDRESS_1` | 3600 |
| A | `eng.yourdomain.com` | `IP_ADDRESS_3` | 3600 |
| A | `out.yourdomain.com` | `IP_ADDRESS_4` | 3600 |
| A | `postal.yourdomain.com` | `SERVER_MAIN_IP` | 3600 |
| A | `track.yourdomain.com` | `SERVER_MAIN_IP` | 3600 |

**Create A records FIRST, wait 1-2 hours for propagation, THEN set PTR records.**

### 4.3 SPF Records

One SPF record per sending subdomain:

| Type | Hostname | Value |
|------|----------|-------|
| TXT | `mail.yourdomain.com` | `v=spf1 ip4:IP_ADDRESS_1 ip4:IP_ADDRESS_2 ~all` |
| TXT | `eng.yourdomain.com` | `v=spf1 ip4:IP_ADDRESS_3 ~all` |
| TXT | `out.yourdomain.com` | `v=spf1 ip4:IP_ADDRESS_4 ip4:IP_ADDRESS_5 ~all` |

**Include all IPs that will send from each subdomain.**

### 4.4 DKIM Records

DKIM public keys will be generated by the Postal mail server during setup. After Postal is deployed:

1. Log into Postal UI → each mail server → Domain → DKIM
2. Copy the DKIM public key
3. Create TXT record:

| Type | Hostname | Value |
|------|----------|-------|
| TXT | `postal-optin._domainkey.mail.yourdomain.com` | `v=DKIM1; k=rsa; p=GENERATED_PUBLIC_KEY` |
| TXT | `postal-engaged._domainkey.eng.yourdomain.com` | `v=DKIM1; k=rsa; p=GENERATED_PUBLIC_KEY` |
| TXT | `postal-cold._domainkey.out.yourdomain.com` | `v=DKIM1; k=rsa; p=GENERATED_PUBLIC_KEY` |

### 4.5 DMARC Record

One DMARC record at the **org domain level**:

| Type | Hostname | Value |
|------|----------|-------|
| TXT | `_dmarc.yourdomain.com` | `v=DMARC1; p=quarantine; rua=mailto:dmarc@yourdomain.com; pct=100` |

**Start with `p=quarantine`. Move to `p=reject` after monitoring shows clean results.**

### 4.6 MX Records (for receiving bounces)

| Type | Hostname | Value | Priority |
|------|----------|-------|----------|
| MX | `mail.yourdomain.com` | `mail.yourdomain.com` | 10 |
| MX | `eng.yourdomain.com` | `eng.yourdomain.com` | 10 |
| MX | `out.yourdomain.com` | `out.yourdomain.com` | 10 |

### 4.7 DNS Propagation

- A records: 1-4 hours
- TXT records (SPF/DKIM/DMARC): 1-4 hours
- PTR records: Usually instant at OVH/Hetzner, up to 24 hours elsewhere

**Verify with:**
```bash
# Check A record
dig mail.yourdomain.com A +short

# Check SPF
dig mail.yourdomain.com TXT +short

# Check DMARC
dig _dmarc.yourdomain.com TXT +short

# Check PTR
dig -x IP_ADDRESS +short

# Full email auth check
# Use https://mxtoolbox.com/SuperTool.aspx
```

---

## 5. IP Address Setup

### 5.1 IP Allocation Plan

| IP | Stream | Type | Subdomain | Daily Cap (warmup start) |
|----|--------|------|-----------|-------------------------|
| IP #1 | Opt-in | Dedicated | mail.yourdomain.com | 500 |
| IP #2 | Opt-in | Dedicated | mail.yourdomain.com | 500 |
| IP #3 | Engaged | Dedicated | eng.yourdomain.com | 200 |
| IP #4 | Cold | Semi-disposable | out.yourdomain.com | 100 |
| IP #5 | Cold | Semi-disposable | out.yourdomain.com | 100 |

### 5.2 Shared vs Dedicated

| Type | Meaning | When to use |
|------|---------|-------------|
| **Dedicated** | One IP per domain/stream, protected | Opt-in stream (most valuable) |
| **Shared** | Multiple domains on one IP | Only if running multiple brands |
| **Semi-disposable** | Expect occasional blocklisting | Cold stream — isolated from opt-in |

### 5.3 IP Configuration Checklist (per IP)

- [ ] IP purchased and assigned to server
- [ ] A record created pointing subdomain → IP
- [ ] PTR record set matching A record hostname
- [ ] IP registered in CRM → IP Pools
- [ ] IP assigned to correct stream and pool
- [ ] Daily warmup cap configured

---

## 6. Port 25 — Unblock SMTP

**By default, most providers block outbound port 25** to prevent spam from compromised servers.

### OVH

1. Log into OVH Manager
2. Go to **Bare Metal Cloud** → your server
3. Check if port 25 is open: **Network** → **Firewall**
4. If blocked, open a **support ticket**:
   - Subject: "Request to unblock outbound port 25 for email sending"
   - Body:
   > We are setting up a legitimate email marketing platform on server [SERVER_NAME]. We need outbound port 25 unblocked for direct-to-MX email delivery. We will implement proper authentication (SPF, DKIM, DMARC), feedback loops, and unsubscribe handling. Our sending domains are: mail.yourdomain.com, eng.yourdomain.com, out.yourdomain.com.

**Typical response time: 1-3 business days. Do this early.**

### Hetzner

1. Hetzner **does not block port 25 on dedicated servers** by default
2. Verify: SSH into server and run:
   ```bash
   telnet gmail-smtp-in.l.google.com 25
   ```
   If it connects, port 25 is open.
3. If blocked (rare for dedicated), open a support ticket with same justification.

### Verification

From the server, test connectivity:
```bash
# Test connection to Gmail
telnet gmail-smtp-in.l.google.com 25

# Test connection to Outlook
telnet outlook-com.olc.protection.outlook.com 25

# Expected: "220" greeting from the remote server
# If timeout: port 25 is blocked
```

---

## 7. SSL Certificates

### What needs SSL

| Service | Domain | Why |
|---------|--------|-----|
| Postal Web UI | `postal.yourdomain.com` | Admin interface HTTPS |
| Tracking | `track.yourdomain.com` | Open/click tracking links |
| CRM | `crm.yourdomain.com` (optional) | Your CRM frontend |

### Using Let's Encrypt (free)

```bash
# Install certbot on the server
sudo apt install certbot

# Generate certificates
sudo certbot certonly --standalone -d postal.yourdomain.com -d track.yourdomain.com

# Certificates will be at:
# /etc/letsencrypt/live/postal.yourdomain.com/fullchain.pem
# /etc/letsencrypt/live/postal.yourdomain.com/privkey.pem

# Auto-renewal is configured automatically
```

---

## 8. Feedback Loop Registration

Register for feedback loops so spam complaints flow back to our system for automatic suppression.

### Microsoft SNDS (Smart Network Data Services)

1. Go to https://sendersupport.olc.protection.outlook.com/snds/
2. Sign in with a Microsoft account
3. Add your sending IPs
4. Verify ownership (they check PTR records)
5. This gives you visibility into how Microsoft views your IPs

### Microsoft JMRP (Junk Mail Reporting Program)

1. Go to https://sendersupport.olc.protection.outlook.com/snds/JMRP.aspx
2. Register your IPs
3. Complaints from Outlook/Hotmail users will be sent to your `abuse@yourdomain.com`

### Google Postmaster Tools

1. Go to https://postmaster.google.com
2. Add and verify your sending domain
3. Monitor: spam rate, authentication, IP reputation, delivery errors

### Required email addresses

Create these mailboxes (or forwarding addresses):

| Address | Purpose |
|---------|---------|
| `abuse@yourdomain.com` | Receives spam complaints from feedback loops |
| `postmaster@yourdomain.com` | Required by RFC, receives delivery issues |
| `dmarc@yourdomain.com` | Receives DMARC aggregate reports |

---

## 9. Server Software Requirements

The development team will handle deployment, but the server needs these pre-installed:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose (included with modern Docker)
docker compose version

# Install useful tools
sudo apt install -y htop iotop net-tools dnsutils telnet
```

**That's all the IT team needs to install.** The application runs entirely in Docker containers — the dev team deploys using `docker compose up -d`.

---

## 10. Handoff Checklist

When the IT team is done, provide the dev team with:

| Item | Details |
|------|---------|
| **Server SSH access** | IP, username, SSH key or password |
| **Server main IP** | The primary IP of the server |
| **IP block** | List of all sending IPs (e.g., 192.168.1.10-14) |
| **Domain** | The root domain being used |
| **DNS access** | Credentials for the domain registrar (or delegate a zone) |
| **Port 25 status** | Confirmed open or ticket number if pending |
| **SSL certs** | Path to certificates on server |
| **Provider login** | OVH/Hetzner panel credentials for IP/PTR management |
| **Feedback loop status** | SNDS, JMRP, Postmaster Tools — registered or pending |

### Verification commands the dev team will run

```bash
# Check Docker
docker --version
docker compose version

# Check port 25
telnet gmail-smtp-in.l.google.com 25

# Check DNS
dig mail.yourdomain.com A +short
dig mail.yourdomain.com TXT +short
dig _dmarc.yourdomain.com TXT +short
dig -x SENDING_IP +short

# Check disk/RAM
free -h
df -h
```

---

## 11. Cost Estimates

### OVH (monthly)

| Item | Cost (approx) |
|------|---------------|
| Dedicated server (Advance) | €60-90/month |
| IP block (/29 = 5 IPs) | €10-15/month |
| Additional IPs (each) | €2-3/month |
| **Total (starting)** | **~€75-110/month** |

### Hetzner (monthly)

| Item | Cost (approx) |
|------|---------------|
| Dedicated server (AX42) | €49-65/month |
| IP block (/29 = 5 IPs) | €5-10/month |
| Additional IPs (each) | €1-2/month |
| **Total (starting)** | **~€55-80/month** |

**Hetzner is typically 20-30% cheaper with cleaner IPs.** Either works — the software is identical.

---

*Document prepared for IT team. Contact the development team for deployment after infrastructure is ready.*

# Testing Team — Component Testing Guide

**Project:** Email Sending Platform + CRM  
**Date:** 2026-06-24  
**CRM URL:** http://localhost:8000  
**API Docs:** http://localhost:8000/docs  
**Mailpit (email viewer):** http://localhost:8025  
**Postal (mail engine):** http://localhost:5000

---

## Table of Contents

1. [Test Accounts](#1-test-accounts)
2. [Pre-Test Setup](#2-pre-test-setup)
3. [Test 1: Authentication](#3-test-1-authentication)
4. [Test 2: Contact Management](#4-test-2-contact-management)
5. [Test 3: Lists](#5-test-3-lists)
6. [Test 4: Templates](#6-test-4-templates)
7. [Test 5: Campaigns](#7-test-5-campaigns)
8. [Test 6: Email Delivery (End-to-End)](#8-test-6-email-delivery-end-to-end)
9. [Test 7: Suppressions](#9-test-7-suppressions)
10. [Test 8: Email Cleaning](#10-test-8-email-cleaning)
11. [Test 9: Reports & Dashboard](#11-test-9-reports--dashboard)
12. [Test 10: CSV Import/Export](#12-test-10-csv-importexport)
13. [Test 11: AI Assistant](#13-test-11-ai-assistant)
14. [Test 12: Domain Management](#14-test-12-domain-management)
15. [Test 13: IP Pools](#15-test-13-ip-pools)
16. [Test 14: Admin Panel](#16-test-14-admin-panel)
17. [Test 15: A/B Testing](#17-test-15-ab-testing)
18. [Test 16: Unsubscribe Flow](#18-test-16-unsubscribe-flow)
19. [Test 17: Webhook Events](#19-test-17-webhook-events)
20. [Bug Report Template](#20-bug-report-template)

---

## 1. Test Accounts

| Email | Password | Role | Use for testing |
|-------|----------|------|-----------------|
| `admin@platform.local` | `admin123` | Admin | Admin features, user management, system health |
| `developer@vedsu.com` | `admin123` | Admin | Second admin, verify multi-admin works |
| `shubham@vedsu.com` | `member123` | Member | Member features, campaigns, templates |
| `vivek@vedsu.com` | `member123` | Member | Member isolation testing |
| `shashikant@vedsu.com` | `member123` | Member | Member isolation testing |
| `tester@vedsu.com` | `member123` | Member | Primary testing account |

---

## 2. Pre-Test Setup

### Verify services are running

Before starting tests, confirm all services are up:

1. **CRM loads:** Open http://localhost:8000 → login page appears
2. **Mailpit loads:** Open http://localhost:8025 → empty inbox
3. **Postal loads:** Open http://localhost:5000 → Postal login page
4. **API docs load:** Open http://localhost:8000/docs → Swagger UI

### How to restart services if something is down

```bash
# Start Docker containers
docker compose -f d:\OVH\docker-compose.yml up -d

# Start FastAPI (WSL Terminal 1)
cd /mnt/d/OVH && source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# Start Celery (WSL Terminal 2)
cd /mnt/d/OVH && source .venv/bin/activate
celery -A worker.celery_app:celery worker --loglevel=info
```

---

## 3. Test 1: Authentication

### What it does
JWT-based login system with admin and member roles.

### Test steps

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 1.1 | Go to http://localhost:8000 | Login page displays | |
| 1.2 | Enter wrong password, click Login | Error message: "Invalid email or password" | |
| 1.3 | Login as `tester@vedsu.com` / `member123` | Dashboard loads, sidebar shows "Tester (member)" | |
| 1.4 | Check sidebar | No "Users" or "System" links visible (member only) | |
| 1.5 | Click Logout | Returns to login page | |
| 1.6 | Login as `admin@platform.local` / `admin123` | Dashboard loads, sidebar shows "Admin (admin)" | |
| 1.7 | Check sidebar | "Users" and "System" links visible under Admin section | |
| 1.8 | Close browser, reopen http://localhost:8000 | Still logged in (token stored in localStorage) | |

---

## 4. Test 2: Contact Management

### What it does
Import, search, filter, view, and manage email contacts.

### Test steps

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 2.1 | Go to Contacts page | Contact list displays with existing contacts | |
| 2.2 | Click "Import" → paste JSON: `[{"email":"test1@example.com","first_name":"Test","stream":"cold"}]` → Import | Toast: "1 contacts imported" | |
| 2.3 | Import same email again | Toast: "0 imported, 1 skipped" (deduplication) | |
| 2.4 | Type "test1" in search bar | Only test1@example.com shows | |
| 2.5 | Select "Cold" from stream filter | Only cold stream contacts show | |
| 2.6 | Select "Active" from status filter | Only active contacts show | |
| 2.7 | Click "Export CSV" | CSV file downloads with all contacts | |
| 2.8 | Open downloaded CSV | Contains headers: email, first_name, last_name, stream, status, etc. | |

### CSV Import test

1. Create a file `test-contacts.csv`:
```csv
email,first_name,last_name
csvtest1@example.com,CSV,Test1
csvtest2@example.com,CSV,Test2
csvtest3@example.com,CSV,Test3
```

2. Contacts → Import → switch to "CSV Upload" tab
3. Select the file, choose stream "Cold", click Import
4. **Expected:** Toast: "3 contacts imported"

---

## 5. Test 3: Lists

### What it does
Group contacts into named lists for campaign targeting.

### Test steps

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 3.1 | Go to Lists page | Existing lists display | |
| 3.2 | Click "Create List" → Name: "Test List A" → Create | Toast: "List created", appears in table | |
| 3.3 | Create another: "Test List B" | Second list appears | |
| 3.4 | Try creating "Test List A" again | Error: "List name already exists" | |
| 3.5 | Click "Delete List" on Test List B | List removed, contacts kept | |
| 3.6 | Click "Delete + Contacts" on a test list | List removed AND exclusive contacts deleted | |

### Adding contacts to a list (via API docs)

1. Open http://localhost:8000/docs
2. Find `POST /lists/{list_id}/contacts`
3. Enter list ID and email array: `["test1@example.com", "csvtest1@example.com"]`
4. Execute
5. Go to Contacts page → filter by this list → verify contacts appear

---

## 6. Test 4: Templates

### What it does
Save reusable email templates with subject, preheader, and HTML body.

### Test steps

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 4.1 | Go to Templates page | Template list displays | |
| 4.2 | Click "Create Template" | Modal opens with fields | |
| 4.3 | Fill in: Name="Test Template", Category="Promotional", Subject="Hi {{first_name}}!", Preheader="Check this out", HTML Body=`<h1>Hello {{first_name}}!</h1><p>This is a test.</p>` | Fields accept input | |
| 4.4 | Click "Preview" | Preview panel shows "Hello John!" (variables replaced with sample data) | |
| 4.5 | Click "Save Template" | Toast: "Template created", appears in list | |
| 4.6 | Click "Clone" on the template | Prompt for new name → creates a copy | |
| 4.7 | Click "Del" on the cloned template | Template deleted after confirmation | |

### Template variables to test

| Variable | Renders as (in preview) |
|----------|------------------------|
| `{{first_name}}` | John |
| `{{last_name}}` | Doe |
| `{{email}}` | john.doe@example.com |

---

## 7. Test 5: Campaigns

### What it does
Create email campaigns using templates, target specific lists, send immediately or schedule.

### Test steps

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 5.1 | Go to Campaigns page | Campaign list displays | |
| 5.2 | Click "Create Campaign" | Modal opens with all fields | |
| 5.3 | Select a template from dropdown | Subject, preheader, and HTML body auto-fill from template | |
| 5.4 | Fill in: Name, From Name, From Email="hello@mail.localhost", Stream="cold" | Fields accept input | |
| 5.5 | Select target lists (multi-select checkbox dropdown) | Selected lists shown in dropdown display | |
| 5.6 | Leave schedule empty → Click "Create" | Toast: "Campaign created", status shows "draft" | |
| 5.7 | Create another with schedule set to future time | Status shows "scheduled" | |
| 5.8 | Click "Launch" on draft campaign | Confirmation dialog → Toast: "X emails enqueued" | |
| 5.9 | Watch campaign status | Changes from "draft" → "sending" → "completed" | |
| 5.10 | Click "Pause" on a sending campaign | Status changes to "paused" | |
| 5.11 | Click "Resume" on paused campaign | Remaining unsent contacts are enqueued | |
| 5.12 | (Member) Click "Archive" on a campaign | Campaign disappears from member view | |
| 5.13 | (Admin) Verify archived campaign is still visible | Shows with "archived" badge | |
| 5.14 | (Admin) Click "Delete" on archived campaign | Permanently removed with all events | |

---

## 8. Test 6: Email Delivery (End-to-End)

### What it does
Proves the full pipeline: CRM → Celery → Postal → Mailpit.

### Test steps

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 6.1 | Clear Mailpit: open http://localhost:8025, delete all messages | Empty inbox | |
| 6.2 | Import 3 test contacts with unique emails | Imported successfully | |
| 6.3 | Create a list, add the 3 contacts to it | Contacts added | |
| 6.4 | Create a template with `{{first_name}}` in subject and body | Template saved | |
| 6.5 | Create a campaign using the template, targeting the list | Campaign in draft | |
| 6.6 | Launch the campaign | Toast: "3 emails enqueued" | |
| 6.7 | Wait 10-15 seconds | Celery processes the tasks | |
| 6.8 | Open http://localhost:8025 | **3 personalized emails appear in Mailpit** | |
| 6.9 | Click an email in Mailpit | HTML renders correctly, {{first_name}} replaced with actual name | |
| 6.10 | Check email headers in Mailpit | List-Unsubscribe header present | |
| 6.11 | Go to Reports → select the campaign | Stats show sent: 3 | |
| 6.12 | Go to Dashboard | Events count increased | |

### What to check in each email (Mailpit)

- [ ] Subject line has personalized name
- [ ] HTML body renders correctly
- [ ] From name and email are correct
- [ ] `List-Unsubscribe` header is present
- [ ] `List-Unsubscribe-Post` header is present (one-click)
- [ ] No raw `{{variable}}` text visible

---

## 9. Test 7: Suppressions

### What it does
Prevents sending to bad/unwanted addresses. Auto-suppresses on hard bounce, complaint, unsubscribe.

### Test steps

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 7.1 | Go to Suppressions page | List of suppressed emails (if any) | |
| 7.2 | Click "Add One" → enter email, reason "manual" → Suppress | Email added to suppression list | |
| 7.3 | Check the suppressed email in Contacts page | Status changed to "suppressed" | |
| 7.4 | Launch a campaign that includes the suppressed email | Suppressed email is SKIPPED (check Celery logs) | |
| 7.5 | Click "Remove" on a suppressed email | Email removed from suppression list, contact status back to "active" | |
| 7.6 | Click "Bulk Upload" → upload CSV with email column → Suppress All | All emails suppressed at once (fast, server-side) | |
| 7.7 | Click "Export" | CSV of all suppressions downloads | |

### CSV for bulk suppression test

Create `suppress-test.csv`:
```csv
email
suppress1@example.com
suppress2@example.com
suppress3@example.com
```

---

## 10. Test 8: Email Cleaning

### What it does
Validates emails before sending — catches invalid syntax, dead domains, disposable/role addresses.

### Test steps

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 8.1 | Go to Email Cleaning page | Verify and Bulk Clean sections visible | |
| 8.2 | Verify: enter `good@gmail.com` → Verify | Verdict: "valid", MX: gmail-smtp-in..., Role: No | |
| 8.3 | Verify: enter `bad@@email` | Verdict: "invalid_syntax" | |
| 8.4 | Verify: enter `admin@gmail.com` | Verdict: "role" (admin is a role address) | |
| 8.5 | Verify: enter `test@mailinator.com` | Verdict: "disposable" | |
| 8.6 | Verify: enter `test@nonexistentdomain99999.com` | Verdict: "no_mx" (domain has no mail server) | |
| 8.7 | Bulk Clean (paste tab): paste 5 emails of different types → Clean | Summary shows counts per category | |
| 8.8 | Bulk Clean (CSV tab): upload CSV with email column → Clean CSV | Same summary with counts | |

### Why it matters

| Verdict | Risk if you send anyway |
|---------|------------------------|
| invalid_syntax | 100% bounce — hurts sender reputation |
| no_mx | 100% bounce — domain can't receive email |
| disposable | Throwaway address — wasted send, possible spam trap |
| role | High complaint risk — monitored by postmasters |

---

## 11. Test 9: Reports & Dashboard

### What it does
Shows sending statistics at global, per-campaign, and per-contact level.

### Test steps

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 9.1 | Go to Dashboard | Stats cards show: total contacts, active, suppressed, campaigns, events | |
| 9.2 | Stream breakdown shows contact counts per stream | Table with optin/engaged/cold counts | |
| 9.3 | Go to Reports | Global stats: total sent, open rate, bounce rate, complaint rate | |
| 9.4 | Select a campaign from dropdown | Campaign detail: sent, delivered, opened, clicked, bounced counts + rates | |
| 9.5 | Click "Export CSV" on campaign report | CSV downloads with per-recipient event data | |
| 9.6 | Enter an email in Contact Lookup → click Lookup | Contact details: stream, status, engagement stats, event timeline | |
| 9.7 | Look up a suppressed email | Shows "SUPPRESSED" badge with reason | |

---

## 12. Test 10: CSV Import/Export

### What it does
Bulk data operations — import contacts via CSV, export any data as CSV.

### Test steps

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 10.1 | Contacts → Import → CSV Upload tab → upload CSV | Contacts imported with correct fields | |
| 10.2 | Contacts → Export CSV | CSV downloads with all contact data + engagement stats | |
| 10.3 | Campaigns → click CSV on a completed campaign | Campaign event report downloads | |
| 10.4 | Suppressions → Export | Full suppression list CSV | |
| 10.5 | Import CSV with duplicate emails | Duplicates skipped, count shown | |
| 10.6 | Import CSV with missing fields | Contacts created with empty fields for missing columns | |

### Test CSV format

```csv
email,first_name,last_name
john@example.com,John,Doe
jane@example.com,Jane,Smith
```

**Must have an `email` column.** Other columns are optional.

---

## 13. Test 11: AI Assistant

### What it does
Uses Claude AI to help with email drafting, bounce classification, and campaign analysis.

### Test steps

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 11.1 | Go to AI Assistant page | Three sections: Draft Email, Classify Bounce, Analyze Campaign | |
| 11.2 | Draft Email: Purpose="Welcome new users", Audience="SaaS users", Tone="friendly" → Generate | AI generates subject, HTML body, text body (takes 5-10 seconds) | |
| 11.3 | Verify the draft has `{{first_name}}` variables | Template variables present for personalization | |
| 11.4 | Classify Bounce: Message="550 5.1.1 User not found", Code="550" → Classify | AI returns: type=hard, should_suppress=true, explanation | |
| 11.5 | Classify Bounce: Message="452 4.2.2 Mailbox full", Code="452" → Classify | AI returns: type=soft, should_retry=true | |
| 11.6 | Analyze Campaign: select a completed campaign → Analyze | AI provides health assessment, issues, recommendations (takes 5-15 seconds) | |

### Notes
- AI features require `ANTHROPIC_API_KEY` in `.env` — if not set, endpoints return 503
- Each AI call costs a small amount (fractions of a cent)
- AI generates drafts that need **human approval** before sending — never auto-sends

---

## 14. Test 12: Domain Management

### What it does
Manages sending domains. Auto-generates DNS records. Verifies DNS configuration.

### Test steps

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 12.1 | Go to Domains page | Domain list (may be empty) | |
| 12.2 | Click "Add Domain" → domain: `testdomain.com`, stream: "Opt-in" | Domain added with full_domain: `mail.testdomain.com` | |
| 12.3 | Click "DNS Records" on the domain | Shows 6 DNS records: TXT (SPF), TXT (DKIM), TXT (DMARC), MX, A, PTR | |
| 12.4 | Click "Verify" | Shows check results — all will fail on localhost (no real DNS) | |
| 12.5 | Each record shows "Pending" or "DNS lookup failed" | Expected on localhost — real verification works with real domains | |
| 12.6 | Click "Del" on the domain | Domain removed after confirmation | |

### Note for testers
Domain verification uses **real DNS lookups**. On localhost with fake domains, verification will correctly report "DNS lookup failed." This is expected behavior — it proves the verification logic works. With real domains and real DNS records, it will show "Verified."

---

## 15. Test 13: IP Pools

### What it does
Manages IP addresses for sending. Organizes IPs into pools assigned to streams and domains.

### Test steps

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 13.1 | Go to IP Pools page | Stats cards + pools table + IPs table | |
| 13.2 | Click "Create Pool" → Name: "Test Pool", Stream: "Opt-in" → Create | Pool appears in pools table | |
| 13.3 | Click "Add IP" → IP: "10.0.0.1", Type: "Dedicated", Stream: "Opt-in", Cap: 500, Pool: "Test Pool" → Add | IP appears in IPs table with pool assignment | |
| 13.4 | Add another IP: "10.0.0.2", Type: "Shared", Stream: "Cold" | Second IP appears with different stream | |
| 13.5 | Stats cards update | Shows total IPs: 2, by status and stream | |
| 13.6 | Delete an IP | IP removed, pool updated | |
| 13.7 | Delete a pool | Pool removed, IPs unassigned (not deleted) | |

### Note for testers
IP pools on localhost are **configuration only** — they don't affect actual sending (Postal handles delivery locally via Mailpit). In production, these IPs map to real Postal IP pools that determine which IP sends each email.

---

## 16. Test 14: Admin Panel

### What it does
System-wide administration — user management, health monitoring, audit log.

**Requires admin login.** Members cannot access these features.

### Test steps

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 14.1 | Login as admin → go to "Users" page | All 6 users listed with roles | |
| 14.2 | Click "Create User" → fill form → Create | New user created, appears in list | |
| 14.3 | Click "Reset PW" on a user | Alert shows new temporary password | |
| 14.4 | Login with the new password in another browser/incognito | Login works with reset password | |
| 14.5 | Go to "System" page | Service health shows MongoDB, Redis, Postal status | |
| 14.6 | Collection sizes show document counts | Numbers match expected data | |
| 14.7 | Per-User Stats shows campaigns, sent, opened per user | Data accurate for users who have sent campaigns | |
| 14.8 | Recent Activity shows latest campaigns and logins | Ordered by most recent | |

### Member restriction test

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 14.9 | Login as `tester@vedsu.com` (member) | "Users" and "System" links NOT visible | |
| 14.10 | Try accessing `http://localhost:8000/docs` → `GET /auth/users` with member token | Returns 403 "Admin access required" | |
| 14.11 | Try accessing `GET /admin/system-health` with member token | Returns 403 | |

---

## 17. Test 15: A/B Testing

### What it does
Tests two subject lines on a portion of the list, then sends the winner to the rest.

### Test steps (via API — http://localhost:8000/docs)

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 15.1 | Create a campaign in draft status | Campaign created | |
| 15.2 | `POST /ab-test` with campaign_id, subject_a, subject_b, test_percent=20 | A/B test created, status: "pending" | |
| 15.3 | `GET /ab-test/{test_id}` | Shows both subjects, stats (all zeros initially) | |
| 15.4 | `POST /ab-test/{test_id}/pick-winner` | Returns winner (a or b) based on metric, updates campaign subject | |
| 15.5 | Verify campaign subject was updated to winning subject | Campaign now has the winning subject | |

---

## 18. Test 16: Unsubscribe Flow

### What it does
One-click unsubscribe as required by Gmail/Yahoo for bulk senders.

### Test steps

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 16.1 | Open http://localhost:8000/unsubscribe/test1@example.com | Unsubscribe page with button displays | |
| 16.2 | Click the "Unsubscribe" button | Success message: "You've been unsubscribed" | |
| 16.3 | Check Suppressions page | test1@example.com appears with reason "unsubscribe" | |
| 16.4 | Check Contacts page | test1@example.com status changed to "unsubscribed" | |
| 16.5 | Launch a campaign that includes this email | Email is SKIPPED (suppressed) | |

---

## 19. Test 17: Webhook Events

### What it does
Receives delivery events from Postal (bounce, open, click) and updates the system.

### Test steps (via API — http://localhost:8000/docs)

Simulate Postal webhook events by sending POST requests to `/webhooks/postal`:

**Test hard bounce:**
```json
{
  "event": "MessageBounced",
  "payload": {
    "message": {"id": 1, "rcpt_to": "bounced@test.com", "tag": ""},
    "status": "HardFail",
    "details": "550 User not found"
  }
}
```

| # | Action | Expected Result | Pass/Fail |
|---|--------|-----------------|-----------|
| 17.1 | Send hard bounce webhook | Returns: processed, bounced | |
| 17.2 | Check suppressions | bounced@test.com auto-suppressed with reason "hard_bounce" | |
| 17.3 | Send open event webhook (`MessageLoaded`) | Contact engagement updated: total_opened + 1 | |
| 17.4 | Send click event webhook (`MessageLinkClicked`) | Contact engagement updated: total_clicked + 1 | |

---

## 20. Bug Report Template

When you find an issue, report it using this format:

```
**Bug Title:** [Short description]

**Component:** [Auth / Contacts / Campaigns / Templates / etc.]

**Steps to Reproduce:**
1. Go to...
2. Click...
3. Enter...

**Expected Result:** What should happen

**Actual Result:** What actually happened

**Screenshots:** [Attach if applicable]

**Browser:** [Chrome/Firefox/Edge + version]

**Login used:** [Which test account]

**Severity:**
- Critical: Blocks testing / data loss
- High: Feature not working
- Medium: Feature works but UI issue
- Low: Cosmetic / nice-to-have
```

---

## Test Execution Order

For first-time testing, follow this order:

1. **Authentication** (Test 1) — must work before anything else
2. **Contacts** (Test 2) — need contacts for everything
3. **Lists** (Test 3) — group contacts
4. **Templates** (Test 4) — create email content
5. **Campaigns** (Test 5) — create and configure sends
6. **Email Delivery** (Test 6) — **the critical end-to-end test**
7. **Suppressions** (Test 7) — verify protection
8. **Email Cleaning** (Test 8) — validate emails
9. **Reports** (Test 9) — verify data accuracy
10. **CSV Import/Export** (Test 10) — bulk operations
11. **AI Assistant** (Test 11) — Claude integration
12. **Domain Management** (Test 12) — infrastructure config
13. **IP Pools** (Test 13) — infrastructure config
14. **Admin Panel** (Test 14) — admin-only features
15. **A/B Testing** (Test 15) — advanced campaign feature
16. **Unsubscribe** (Test 16) — compliance
17. **Webhooks** (Test 17) — event processing

**Test 6 (Email Delivery) is the most important test.** If this passes, the core system works.

---

*Document prepared for the testing team. Report bugs using the template above.*

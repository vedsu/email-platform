import anthropic
from core.config import settings


def _get_client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Get one at https://console.anthropic.com → API Keys, "
            "then add it to your .env file."
        )
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def generate_dns_config(domain: str, streams: dict) -> str:
    client = _get_client()
    prompt = f"""Generate the complete DNS configuration for an email sending platform.

Domain: {domain}
Streams and subdomains:
{chr(10).join(f'  - {stream}: {subdomain}' for stream, subdomain in streams.items())}

Provide:
1. SPF records for each subdomain
2. DKIM selector naming convention
3. DMARC record for the org domain
4. MX records if needed
5. PTR record guidance

Format as a ready-to-paste DNS zone file with explanations."""

    message = client.messages.create(
        model=settings.claude_model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def draft_warmup_plan(ip_count: int, streams: list[str], daily_target: int) -> str:
    client = _get_client()
    prompt = f"""Create a detailed IP warmup plan for an email sending platform.

Setup:
- {ip_count} IP addresses
- Streams: {', '.join(streams)}
- Target daily volume: {daily_target:,} emails/day
- Provider mix: primarily Gmail, Outlook, Yahoo

Provide a week-by-week ramp schedule (8 weeks) with:
1. Daily volume per IP per stream
2. Bounce rate thresholds to pause
3. Complaint rate thresholds to pause
4. When to increase volume
5. Signs to watch for at each stage

Format as a structured plan with clear numbers."""

    message = client.messages.create(
        model=settings.claude_model,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def draft_email_content(
    purpose: str,
    audience: str,
    tone: str = "professional",
    key_points: list[str] = None,
) -> dict:
    client = _get_client()
    points_text = ""
    if key_points:
        points_text = f"\nKey points to cover:\n" + "\n".join(f"- {p}" for p in key_points)

    prompt = f"""Draft an email for the following:

Purpose: {purpose}
Audience: {audience}
Tone: {tone}{points_text}

Provide:
1. Subject line (compelling, under 60 chars)
2. HTML body (clean, responsive, with {{{{first_name}}}} personalization)
3. Plain text version

Use template variables: {{{{first_name}}}}, {{{{last_name}}}}, {{{{email}}}}

Return as JSON with keys: subject, html_body, text_body"""

    message = client.messages.create(
        model=settings.claude_model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def classify_bounce(bounce_message: str, smtp_code: str = "") -> dict:
    client = _get_client()
    prompt = f"""Classify this email bounce and recommend action.

SMTP code: {smtp_code}
Bounce message: {bounce_message}

Return JSON with:
- type: "hard" or "soft"
- category: one of [mailbox_full, user_unknown, domain_error, policy_block, rate_limit, content_block, temporary, other]
- should_suppress: true/false
- should_retry: true/false
- explanation: one sentence
- recommended_action: one sentence"""

    message = client.messages.create(
        model=settings.claude_model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def analyze_deliverability(stats: dict) -> str:
    client = _get_client()
    prompt = f"""Analyze these email campaign deliverability metrics and provide recommendations.

Campaign stats:
{chr(10).join(f'  {k}: {v}' for k, v in stats.items())}

Provide:
1. Overall health assessment (good / warning / critical)
2. Key issues identified
3. Specific recommendations to improve deliverability
4. Comparison against industry benchmarks

Be specific and actionable."""

    message = client.messages.create(
        model=settings.claude_model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text

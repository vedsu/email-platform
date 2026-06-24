from datetime import date
import redis as redis_lib
from core.config import settings

_redis = None

DOMAIN_LIMITS = {
    "gmail.com": 2000,
    "googlemail.com": 2000,
    "yahoo.com": 1000,
    "yahoo.co.in": 1000,
    "outlook.com": 1500,
    "hotmail.com": 1500,
    "live.com": 1500,
    "aol.com": 1000,
}

DEFAULT_DOMAIN_LIMIT = 5000


def _get_redis():
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.redis_uri, decode_responses=True)
    return _redis


def get_domain_key(recipient_domain: str) -> str:
    return f"ratelimit:{recipient_domain}:{date.today().isoformat()}"


def check_domain_rate_limit(recipient_email: str) -> bool:
    domain = recipient_email.split("@")[1].lower()
    limit = DOMAIN_LIMITS.get(domain, DEFAULT_DOMAIN_LIMIT)

    r = _get_redis()
    key = get_domain_key(domain)
    count = r.get(key)
    current = int(count) if count else 0

    return current < limit


def increment_domain_count(recipient_email: str):
    domain = recipient_email.split("@")[1].lower()
    r = _get_redis()
    key = get_domain_key(domain)
    count = r.incr(key)
    if count == 1:
        r.expire(key, 86400 * 2)

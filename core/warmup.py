from datetime import date
import redis as redis_lib
from core.config import settings

_redis: redis_lib.Redis = None


def _get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.redis_uri, decode_responses=True)
    return _redis


def get_daily_key(stream: str) -> str:
    return f"warmup:{stream}:{date.today().isoformat()}"


def get_daily_count(stream: str) -> int:
    r = _get_redis()
    count = r.get(get_daily_key(stream))
    return int(count) if count else 0


def get_daily_cap(stream: str) -> int:
    caps = {
        "optin": settings.warmup_optin_daily_cap,
        "engaged": settings.warmup_engaged_daily_cap,
        "cold": settings.warmup_cold_daily_cap,
    }
    return caps.get(stream, 100)


def increment_send_count(stream: str) -> int:
    r = _get_redis()
    key = get_daily_key(stream)
    count = r.incr(key)
    if count == 1:
        r.expire(key, 86400 * 2)
    return count


def check_warmup_quota(stream: str) -> bool:
    if not settings.warmup_enabled:
        return True
    return get_daily_count(stream) < get_daily_cap(stream)

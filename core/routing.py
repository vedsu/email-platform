from core.config import settings


STREAM_DOMAINS = {
    "optin": lambda: settings.stream_optin_domain,
    "engaged": lambda: settings.stream_engaged_domain,
    "cold": lambda: settings.stream_cold_domain,
}


def get_sending_domain(stream: str) -> str:
    getter = STREAM_DOMAINS.get(stream)
    if not getter:
        raise ValueError(f"Unknown stream: {stream}")
    return getter()


def route_from_address(from_email: str, stream: str) -> str:
    domain = get_sending_domain(stream)
    local_part = from_email.split("@")[0]
    return f"{local_part}@{domain}"

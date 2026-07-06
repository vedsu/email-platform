import logging
import httpx
from core.config import settings

logger = logging.getLogger(__name__)


def send_message(
    to: str,
    from_addr: str,
    from_name: str,
    subject: str,
    html_body: str,
    text_body: str = None,
    tag: str = None,
) -> dict:
    if not settings.postal_api_key:
        raise RuntimeError("POSTAL_API_KEY is not configured")

    unsub_url = f"http://{settings.app_domain}:{settings.api_port}/unsubscribe/{to}"

    payload = {
        "to": [to],
        "from": f"{from_name} <{from_addr}>",
        "subject": subject,
        "html_body": html_body,
        "track_opens": True,
        "track_clicks": True,
        "headers": {
            "List-Unsubscribe": f"<{unsub_url}>, <mailto:unsubscribe@{from_addr.split('@')[1]}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    }
    if text_body:
        payload["plain_body"] = text_body
    if tag:
        payload["tag"] = tag

    response = httpx.post(
        f"{settings.postal_api_url}/api/v1/send/message",
        headers={"X-Server-API-Key": settings.postal_api_key},
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    result = response.json()
    logger.info(f"Postal response: {result}")
    if result.get("status") != "success":
        logger.error(f"Postal error: {result}")
    return result

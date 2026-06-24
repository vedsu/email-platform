import re
import dns.resolver
from typing import Optional

ROLE_ADDRESSES = {
    "abuse", "admin", "administrator", "billing", "compliance",
    "devnull", "dns", "ftp", "hostmaster", "info", "inoc",
    "ispfeedback", "ispsupport", "list", "maildaemon", "marketing",
    "noc", "noreply", "no-reply", "null", "phish", "phishing",
    "postmaster", "privacy", "registrar", "root", "security",
    "spam", "support", "sysadmin", "tech", "undisclosed-recipients",
    "unsubscribe", "usenet", "uucp", "webmaster", "www",
}

DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "tempmail.com", "throwaway.email",
    "yopmail.com", "sharklasers.com", "guerrillamailblock.com", "grr.la",
    "dispostable.com", "trashmail.com", "10minutemail.com", "temp-mail.org",
    "fakeinbox.com", "mailnesia.com", "maildrop.cc", "discard.email",
}

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def validate_syntax(email: str) -> bool:
    return bool(EMAIL_REGEX.match(email))


def is_role_address(email: str) -> bool:
    local_part = email.split("@")[0].lower()
    return local_part in ROLE_ADDRESSES


def is_disposable_domain(email: str) -> bool:
    domain = email.split("@")[1].lower()
    return domain in DISPOSABLE_DOMAINS


def check_mx_record(email: str) -> Optional[str]:
    domain = email.split("@")[1]
    try:
        answers = dns.resolver.resolve(domain, "MX")
        if answers:
            return str(answers[0].exchange)
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, dns.resolver.Timeout):
        return None
    return None


def clean_email(email: str) -> dict:
    result = {
        "email": email.strip().lower(),
        "valid_syntax": False,
        "is_role": False,
        "is_disposable": False,
        "has_mx": False,
        "mx_record": None,
        "verdict": "invalid",
    }

    if not validate_syntax(result["email"]):
        result["verdict"] = "invalid_syntax"
        return result

    result["valid_syntax"] = True
    result["is_role"] = is_role_address(result["email"])
    result["is_disposable"] = is_disposable_domain(result["email"])

    mx = check_mx_record(result["email"])
    result["has_mx"] = mx is not None
    result["mx_record"] = mx

    if not result["has_mx"]:
        result["verdict"] = "no_mx"
    elif result["is_disposable"]:
        result["verdict"] = "disposable"
    elif result["is_role"]:
        result["verdict"] = "role"
    else:
        result["verdict"] = "valid"

    return result

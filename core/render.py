import re


def render_template(template: str, contact: dict) -> str:
    def replacer(match):
        key = match.group(1).strip()
        if key in contact:
            return str(contact[key])
        if "." in key:
            parts = key.split(".")
            val = contact
            for part in parts:
                if isinstance(val, dict):
                    val = val.get(part)
                else:
                    return match.group(0)
            return str(val) if val is not None else ""
        return ""

    return re.sub(r"\{\{(.+?)\}\}", replacer, template)

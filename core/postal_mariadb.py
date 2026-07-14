import subprocess
from core.config import settings


def postal_sql(sql: str, db: str = "postal") -> list[list[str]]:
    cmd = [
        "docker", "exec", settings.postal_mariadb_container,
        "mariadb", "-u", "root",
        f"-p{settings.postal_mariadb_root_password}",
        db, "--skip-column-names", "--batch", "-e", sql,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300] or "MariaDB error")
    rows = []
    for line in r.stdout.strip().split("\n"):
        if line:
            rows.append(line.split("\t"))
    return rows


def get_sending_ip_for_message(postal_message_id: int) -> str | None:
    """Return the IPv4 that Postal assigned to this message.

    Queries queued_messages while the record still exists (before the worker
    delivers and clears it). Called immediately after the Postal HTTP API
    returns, so the record is almost always present.
    """
    try:
        rows = postal_sql(
            f"SELECT ia.ipv4 FROM queued_messages qm "
            f"JOIN ip_addresses ia ON qm.ip_address_id = ia.id "
            f"WHERE qm.message_id = {int(postal_message_id)} LIMIT 1"
        )
        return rows[0][0] if rows else None
    except Exception:
        return None

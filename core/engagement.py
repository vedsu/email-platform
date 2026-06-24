from datetime import datetime, timedelta


def calculate_engagement_score(engagement: dict) -> float:
    now = datetime.utcnow()
    score = 0.0

    total_sent = engagement.get("total_sent", 0)
    total_opened = engagement.get("total_opened", 0)
    total_clicked = engagement.get("total_clicked", 0)

    if total_sent == 0:
        return 0.0

    open_rate = total_opened / total_sent
    click_rate = total_clicked / total_sent

    score += open_rate * 40
    score += click_rate * 30

    last_opened = engagement.get("last_opened_at")
    if last_opened:
        if isinstance(last_opened, str):
            last_opened = datetime.fromisoformat(last_opened)
        days_since = (now - last_opened).days
        if days_since <= 7:
            score += 20
        elif days_since <= 30:
            score += 10
        elif days_since <= 90:
            score += 5

    last_clicked = engagement.get("last_clicked_at")
    if last_clicked:
        if isinstance(last_clicked, str):
            last_clicked = datetime.fromisoformat(last_clicked)
        days_since = (now - last_clicked).days
        if days_since <= 7:
            score += 10
        elif days_since <= 30:
            score += 5

    return round(min(score, 100.0), 1)

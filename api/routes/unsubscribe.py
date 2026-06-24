from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from models.database import get_db
from core.suppression import add_suppression

router = APIRouter(tags=["unsubscribe"])


@router.get("/unsubscribe/{email}")
async def unsubscribe_page(email: str):
    return HTMLResponse(f"""
    <html>
    <body style="font-family: sans-serif; max-width: 500px; margin: 50px auto; text-align: center;">
        <h2>Unsubscribe</h2>
        <p>Click below to unsubscribe <strong>{email}</strong> from all future emails.</p>
        <form method="POST" action="/unsubscribe/{email}">
            <button type="submit" style="padding: 12px 24px; font-size: 16px; background: #d9534f; color: white; border: none; border-radius: 4px; cursor: pointer;">
                Unsubscribe
            </button>
        </form>
    </body>
    </html>
    """)


@router.post("/unsubscribe/{email}")
async def unsubscribe_confirm(email: str):
    db = get_db()

    add_suppression(email, "unsubscribe", source="one_click")

    await db.contacts.update_one(
        {"email": email},
        {"$set": {"status": "unsubscribed", "updated_at": datetime.utcnow()}},
    )

    return HTMLResponse("""
    <html>
    <body style="font-family: sans-serif; max-width: 500px; margin: 50px auto; text-align: center;">
        <h2>You've been unsubscribed</h2>
        <p>You will no longer receive emails from us.</p>
    </body>
    </html>
    """)


@router.post("/unsubscribe/one-click")
async def one_click_unsubscribe(request: Request):
    """RFC 8058 one-click unsubscribe via POST. Gmail/Yahoo require this."""
    form = await request.form()
    email = form.get("List-Unsubscribe-One-Click", form.get("email", ""))
    if not email:
        return {"status": "error", "detail": "No email provided"}

    add_suppression(email, "unsubscribe", source="one_click_header")

    db = get_db()
    await db.contacts.update_one(
        {"email": email},
        {"$set": {"status": "unsubscribed", "updated_at": datetime.utcnow()}},
    )

    return {"status": "unsubscribed", "email": email}

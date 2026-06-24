from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from core.config import settings
from models.database import connect_db, close_db, get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()


app = FastAPI(
    title="Email Platform API",
    debug=settings.app_debug,
    lifespan=lifespan,
)

from api.routes import contacts, campaigns, lists, events, suppressions, webhooks, unsubscribe, cleaning, dashboard, ai, auth, templates, reports, csv_ops

app.include_router(contacts.router)
app.include_router(campaigns.router)
app.include_router(lists.router)
app.include_router(events.router)
app.include_router(suppressions.router)
app.include_router(webhooks.router)
app.include_router(unsubscribe.router)
app.include_router(cleaning.router)
app.include_router(dashboard.router)
app.include_router(ai.router)
app.include_router(auth.router)
app.include_router(templates.router)
app.include_router(reports.router)
app.include_router(csv_ops.router)


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/")
async def root():
    return RedirectResponse("/static/index.html")


@app.get("/health")
async def health():
    db = get_db()
    mongo_ok = False
    try:
        result = await db.command("ping")
        mongo_ok = result.get("ok") == 1.0
    except Exception:
        pass

    return {
        "status": "ok" if mongo_ok else "degraded",
        "env": settings.app_env,
        "mongodb": "connected" if mongo_ok else "disconnected",
    }
